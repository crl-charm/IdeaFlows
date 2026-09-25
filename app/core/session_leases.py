"""Redis-backed one-active-session leases.

The browser keeps the plaintext random token inside Flask's signed session cookie.
Redis stores only its SHA-256 digest.  Compare-and-refresh/delete operations run
inside Lua so a stale browser can never overwrite or release a newer lease.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import secrets
from typing import Any


class SessionLeaseUnavailable(RuntimeError):
    """Raised when the configured Redis registry cannot be reached."""


_ACQUIRE_SCRIPT = """
for slot = 1, #KEYS do
  if redis.call('EXISTS', KEYS[slot]) == 0 then
    redis.call('HSET', KEYS[slot],
  'token_hash', ARGV[2],
  'identity', slot == 1 and ARGV[3] or ARGV[3] .. ':' .. slot,
  'user_id', ARGV[4],
  'username', ARGV[5],
  'role', ARGV[6],
  'ip_address', ARGV[7],
  'user_agent', ARGV[8],
  'issued_at', ARGV[9],
  'last_seen', ARGV[9])
    redis.call('EXPIRE', KEYS[slot], tonumber(ARGV[1]))
    return slot
  end
end
return 0
"""

_REFRESH_SCRIPT = """
local current = redis.call('HGET', KEYS[1], 'token_hash')
if not current or current ~= ARGV[1] then
  return 0
end
redis.call('HSET', KEYS[1], 'last_seen', ARGV[2])
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[3]))
return 1
"""

_RELEASE_SCRIPT = """
local current = redis.call('HGET', KEYS[1], 'token_hash')
if not current or current ~= ARGV[1] then
  return 0
end
return redis.call('DEL', KEYS[1])
"""


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


@dataclass(frozen=True)
class LeaseIdentity:
    account_type: str
    account_id: int

    @property
    def value(self) -> str:
        return f"{self.account_type}:{self.account_id}"


class SessionLeaseService:
    """Manage short-lived, atomic login leases in Redis."""

    def __init__(self, redis_client, *, ttl_seconds: int, key_prefix: str) -> None:
        self._redis = redis_client
        self.ttl_seconds = int(ttl_seconds)
        self.key_prefix = key_prefix.rstrip(":")

    @property
    def available(self) -> bool:
        return self._redis is not None

    def _require_redis(self):
        if self._redis is None:
            raise SessionLeaseUnavailable("The login session registry is unavailable")
        return self._redis

    def _key(self, identity: str) -> str:
        return f"{self.key_prefix}:{identity}"

    def acquire(
        self,
        identity: str,
        *,
        user_id: int,
        username: str,
        role: str,
        ip_address: str,
        user_agent: str,
        max_sessions: int = 1,
    ) -> str | tuple[str, str] | None:
        """Return a token (or identity and token for multiple slots)."""
        redis_client = self._require_redis()
        token = secrets.token_urlsafe(32)
        now = _utc_iso()
        try:
            created = redis_client.eval(
                _ACQUIRE_SCRIPT,
                max_sessions,
                *(self._key(identity if slot == 1 else f"{identity}:{slot}") for slot in range(1, max_sessions + 1)),
                self.ttl_seconds,
                _token_hash(token),
                identity[:100],
                int(user_id),
                username[:100],
                role[:30],
                ip_address[:64],
                user_agent[:200],
                now,
            )
            if not created:
                return None
            claimed_identity = identity if created == 1 else f"{identity}:{created}"
            return (claimed_identity, token) if max_sessions > 1 else token
        except Exception as exc:
            raise SessionLeaseUnavailable("The login session registry is unavailable") from exc

    def validate(self, identity: str, token: str, *, refresh: bool = True) -> bool:
        redis_client = self._require_redis()
        if not identity or not token:
            return False
        try:
            if refresh:
                result = redis_client.eval(
                    _REFRESH_SCRIPT,
                    1,
                    self._key(identity),
                    _token_hash(token),
                    _utc_iso(),
                    self.ttl_seconds,
                )
                return bool(result)
            stored = redis_client.hget(self._key(identity), "token_hash")
            return bool(stored) and secrets.compare_digest(
                _text(stored), _token_hash(token)
            )
        except Exception as exc:
            raise SessionLeaseUnavailable("The login session registry is unavailable") from exc

    def release(self, identity: str, token: str) -> bool:
        redis_client = self._require_redis()
        if not identity or not token:
            return False
        try:
            return bool(
                redis_client.eval(
                    _RELEASE_SCRIPT,
                    1,
                    self._key(identity),
                    _token_hash(token),
                )
            )
        except Exception as exc:
            raise SessionLeaseUnavailable("The login session registry is unavailable") from exc

    def revoke(self, identity: str) -> bool:
        redis_client = self._require_redis()
        try:
            return bool(redis_client.delete(self._key(identity)))
        except Exception as exc:
            raise SessionLeaseUnavailable("The login session registry is unavailable") from exc

    def get(self, identity: str) -> dict[str, Any] | None:
        redis_client = self._require_redis()
        try:
            values = redis_client.hgetall(self._key(identity))
            if not values:
                return None
            data = {_text(key): _text(value) for key, value in values.items()}
            data.pop("token_hash", None)
            data["ttl_seconds"] = max(int(redis_client.ttl(self._key(identity))), 0)
            return data
        except Exception as exc:
            raise SessionLeaseUnavailable("The login session registry is unavailable") from exc

    def list_active(self) -> list[dict[str, Any]]:
        redis_client = self._require_redis()
        sessions: list[dict[str, Any]] = []
        try:
            for raw_key in redis_client.scan_iter(match=f"{self.key_prefix}:*"):
                key = _text(raw_key)
                identity = key[len(self.key_prefix) + 1 :]
                lease = self.get(identity)
                if lease:
                    sessions.append(lease)
        except SessionLeaseUnavailable:
            raise
        except Exception as exc:
            raise SessionLeaseUnavailable("The login session registry is unavailable") from exc
        return sorted(sessions, key=lambda row: row.get("last_seen", ""), reverse=True)


def current_lease_is_valid(*, refresh: bool = True) -> bool:
    """Validate the lease stored in the current Flask session."""
    from flask import current_app, g, session

    if not current_app.config.get("SINGLE_SESSION_ENABLED"):
        return True
    if refresh and getattr(g, "session_lease_validated", False):
        return True
    identity = session.get("login_lease_identity", "")
    token = session.get("login_lease_token", "")
    service: SessionLeaseService = current_app.extensions["session_leases"]
    valid = service.validate(identity, token, refresh=refresh)
    if valid and refresh:
        g.session_lease_validated = True
    return valid
