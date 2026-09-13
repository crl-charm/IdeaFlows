"""Duplicate-submit protection for state-changing HTTP requests."""

from __future__ import annotations

from functools import wraps
from hashlib import sha256
from threading import Lock
from time import monotonic

from flask import current_app, jsonify, request, session


_local_lock = Lock()
_local_requests: dict[str, tuple[float, str]] = {}


def _request_key(action: str, client_key: str) -> str:
    actor = session.get("user_id") or request.remote_addr or "anonymous"
    raw = f"{actor}:{action}:{request.path}:{client_key}".encode("utf-8")
    return f"idempotency:{sha256(raw).hexdigest()}"


def _reserve_locally(key: str, ttl_seconds: int) -> bool:
    now = monotonic()
    with _local_lock:
        expired = [item for item, (expires, _) in _local_requests.items() if expires <= now]
        for item in expired:
            _local_requests.pop(item, None)
        if key in _local_requests:
            return False
        _local_requests[key] = (now + ttl_seconds, "processing")
        return True


def _finish_locally(key: str, ttl_seconds: int, *, keep: bool) -> None:
    with _local_lock:
        if keep:
            _local_requests[key] = (monotonic() + ttl_seconds, "completed")
        else:
            _local_requests.pop(key, None)


def idempotent_request(action: str, ttl_seconds: int = 180):
    """Reject replayed requests carrying the same ``Idempotency-Key``.

    Redis provides cross-worker coordination in production. If Redis is down,
    the in-process lock still protects a single worker instead of failing the
    business request. Requests without a key remain backward-compatible.
    """

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            client_key = (request.headers.get("Idempotency-Key") or "").strip()
            if not client_key:
                return view(*args, **kwargs)
            if len(client_key) > 200:
                return jsonify({"success": False, "error": "Invalid request key."}), 400

            key = _request_key(action, client_key)
            redis_client = current_app.extensions.get("redis_health")
            using_redis = False

            if redis_client is not None:
                try:
                    acquired = bool(redis_client.set(key, "processing", nx=True, ex=ttl_seconds))
                    using_redis = True
                except Exception:
                    current_app.logger.warning(
                        "Redis idempotency unavailable; using local protection",
                        exc_info=True,
                    )
                    acquired = _reserve_locally(key, ttl_seconds)
            else:
                acquired = _reserve_locally(key, ttl_seconds)

            if not acquired:
                return jsonify({
                    "success": False,
                    "duplicate": True,
                    "error": "This action is already processing or was already completed.",
                }), 409

            try:
                response = current_app.make_response(view(*args, **kwargs))
            except Exception:
                if using_redis:
                    try:
                        redis_client.delete(key)
                    except Exception:
                        pass
                else:
                    _finish_locally(key, ttl_seconds, keep=False)
                raise

            keep = response.status_code < 500
            if using_redis:
                try:
                    if keep:
                        redis_client.set(key, "completed", xx=True, ex=ttl_seconds)
                    else:
                        redis_client.delete(key)
                except Exception:
                    current_app.logger.warning("Unable to finalize Redis idempotency key", exc_info=True)
            else:
                _finish_locally(key, ttl_seconds, keep=keep)
            return response

        wrapped._idempotency_action = action
        return wrapped

    return decorator
