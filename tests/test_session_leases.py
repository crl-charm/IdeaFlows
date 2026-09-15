"""Atomic one-active-session lease tests without an external Redis server."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import fnmatch
from threading import Lock

import pytest

from app import create_app
from app.core.session_leases import SessionLeaseService, SessionLeaseUnavailable


@pytest.fixture
def app():
    application = create_app()
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return application


class FakeRedis:
    def __init__(self):
        self.rows = {}
        self.expires = {}
        self.now = 1_000.0
        self.lock = Lock()

    def _purge(self, key):
        if key in self.expires and self.expires[key] <= self.now:
            self.rows.pop(key, None)
            self.expires.pop(key, None)

    def eval(self, script, _key_count, key, *args):
        with self.lock:
            self._purge(key)
            if "'issued_at'" in script:
                if key in self.rows:
                    return 0
                ttl, token_hash, identity, user_id, username, role, ip, agent, now = args
                self.rows[key] = {
                    "token_hash": str(token_hash),
                    "identity": str(identity),
                    "user_id": str(user_id),
                    "username": str(username),
                    "role": str(role),
                    "ip_address": str(ip),
                    "user_agent": str(agent),
                    "issued_at": str(now),
                    "last_seen": str(now),
                }
                self.expires[key] = self.now + int(ttl)
                return 1
            if key not in self.rows or self.rows[key]["token_hash"] != str(args[0]):
                return 0
            if "'last_seen'" in script:
                self.rows[key]["last_seen"] = str(args[1])
                self.expires[key] = self.now + int(args[2])
                return 1
            self.rows.pop(key, None)
            self.expires.pop(key, None)
            return 1

    def hget(self, key, field):
        with self.lock:
            self._purge(key)
            return self.rows.get(key, {}).get(field)

    def hgetall(self, key):
        with self.lock:
            self._purge(key)
            return dict(self.rows.get(key, {}))

    def ttl(self, key):
        with self.lock:
            self._purge(key)
            return int(self.expires[key] - self.now) if key in self.rows else -2

    def scan_iter(self, match):
        with self.lock:
            keys = list(self.rows)
        for key in keys:
            with self.lock:
                self._purge(key)
                exists = key in self.rows
            if exists and fnmatch.fnmatch(key, match):
                yield key

    def delete(self, key):
        with self.lock:
            existed = key in self.rows
            self.rows.pop(key, None)
            self.expires.pop(key, None)
            return int(existed)

    def advance(self, seconds):
        self.now += seconds


def _service(redis_client=None):
    return SessionLeaseService(
        redis_client if redis_client is not None else FakeRedis(),
        ttl_seconds=120,
        key_prefix="test:active-login",
    )


def _acquire(service, identity="staff:1"):
    return service.acquire(
        identity,
        user_id=1,
        username="test_user",
        role="staff",
        ip_address="127.0.0.1",
        user_agent="pytest",
    )


def test_only_one_concurrent_acquire_wins():
    service = _service()
    with ThreadPoolExecutor(max_workers=8) as pool:
        tokens = list(pool.map(lambda _: _acquire(service), range(8)))
    assert sum(token is not None for token in tokens) == 1


def test_owner_can_refresh_and_release_but_stale_token_cannot():
    redis_client = FakeRedis()
    service = _service(redis_client)
    token = _acquire(service)
    assert token
    assert service.validate("staff:1", token) is True
    assert service.validate("staff:1", "wrong-token") is False
    assert service.release("staff:1", "wrong-token") is False
    assert service.get("staff:1") is not None
    assert service.release("staff:1", token) is True
    assert service.get("staff:1") is None


def test_expired_lease_allows_a_new_browser():
    redis_client = FakeRedis()
    service = _service(redis_client)
    first = _acquire(service)
    assert first
    redis_client.advance(121)
    second = _acquire(service)
    assert second and second != first
    assert service.validate("staff:1", first, refresh=False) is False
    assert service.validate("staff:1", second, refresh=False) is True


def test_listing_redacts_token_hash_and_revoke_works():
    service = _service()
    assert _acquire(service)
    rows = service.list_active()
    assert len(rows) == 1
    assert rows[0]["identity"] == "staff:1"
    assert "token_hash" not in rows[0]
    assert service.revoke("staff:1") is True
    assert service.list_active() == []


def test_missing_redis_fails_closed():
    service = SessionLeaseService(
        None, ttl_seconds=120, key_prefix="test:active-login"
    )
    with pytest.raises(SessionLeaseUnavailable):
        _acquire(service)


def _enable_single_session(app):
    app.config.update(
        SINGLE_SESSION_ENABLED=True,
        TURNSTILE_ENABLED=False,
        WTF_CSRF_ENABLED=False,
    )
    app.extensions["session_leases"] = _service()


def _login(client):
    return client.post(
        "/api/login",
        json={"username": "test_user", "password": "TestPassword123!"},
    )


def test_second_browser_is_blocked_and_logout_releases_account(app):
    _enable_single_session(app)
    first_browser = app.test_client()
    second_browser = app.test_client()

    assert _login(first_browser).status_code == 200
    blocked = _login(second_browser)
    assert blocked.status_code == 409
    assert blocked.get_json()["code"] == "account_already_active"
    assert first_browser.get("/dashboard").status_code == 200

    assert first_browser.get("/logout").status_code == 302
    assert _login(second_browser).status_code == 200


def test_multiple_tabs_sharing_cookie_keep_the_same_lease(app):
    _enable_single_session(app)
    browser = app.test_client()
    assert _login(browser).status_code == 200
    assert browser.get("/dashboard").status_code == 200
    assert browser.get("/profile").status_code == 200
    assert len(app.extensions["session_leases"].list_active()) == 1


def test_stale_cookie_is_rejected_after_admin_revocation(app):
    _enable_single_session(app)
    browser = app.test_client()
    assert _login(browser).status_code == 200
    with browser.session_transaction() as flask_session:
        identity = flask_session["login_lease_identity"]
    assert app.extensions["session_leases"].revoke(identity) is True

    response = browser.get("/api/users", headers={"Accept": "application/json"})
    assert response.status_code == 401
    assert response.get_json()["code"] == "session_revoked"


def test_login_fails_closed_when_registry_is_missing(app):
    app.config.update(
        SINGLE_SESSION_ENABLED=True,
        TURNSTILE_ENABLED=False,
        WTF_CSRF_ENABLED=False,
    )
    app.extensions["session_leases"] = SessionLeaseService(
        None, ttl_seconds=120, key_prefix="test:active-login"
    )
    response = _login(app.test_client())
    assert response.status_code == 503
    assert "temporarily unavailable" in response.get_json()["error"].lower()


def test_admin_can_list_and_revoke_other_session_but_not_own(app, monkeypatch):
    _enable_single_session(app)
    lease_service = app.extensions["session_leases"]
    admin_token = lease_service.acquire(
        "admin:7",
        user_id=1,
        username="admin",
        role="admin",
        ip_address="127.0.0.1",
        user_agent="admin-browser",
    )
    staff_token = lease_service.acquire(
        "staff:8",
        user_id=8,
        username="staffer",
        role="staff",
        ip_address="127.0.0.2",
        user_agent="staff-browser",
    )
    assert admin_token and staff_token
    monkeypatch.setattr(
        "app.routes.admin_routes.emit_session_revoked", lambda _user_id: None
    )

    admin_browser = app.test_client()
    with admin_browser.session_transaction() as flask_session:
        flask_session.update({
            "user_id": 1,
            "username": "admin",
            "role": "admin",
            "account_type": "admin",
            "last_activity": 1_000_000_000_000,
            "login_lease_identity": "admin:7",
            "login_lease_token": admin_token,
        })

    listing = admin_browser.get("/api/admin/active-sessions")
    assert listing.status_code == 200
    assert len(listing.get_json()["sessions"]) == 2

    self_revoke = admin_browser.delete("/api/admin/active-sessions/admin:7")
    assert self_revoke.status_code == 400
    revoked = admin_browser.delete("/api/admin/active-sessions/staff:8")
    assert revoked.status_code == 200
    assert lease_service.get("staff:8") is None
