"""Cloudflare Turnstile login integration tests."""

from __future__ import annotations

import pytest

from app import create_app


@pytest.fixture
def app():
    application = create_app()
    application.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        TURNSTILE_ENABLED=True,
        TURNSTILE_SITE_KEY="test-public-site-key",
        TURNSTILE_SECRET_KEY="test-private-secret-key",
        TURNSTILE_ALLOWED_HOSTNAMES=["localhost"],
    )
    return application


@pytest.fixture
def client(app):
    return app.test_client()


def _credentials(**extra):
    return {
        "username": "test_user",
        "password": "TestPassword123!",
        **extra,
    }


def test_widget_is_rendered_on_both_login_surfaces(client):
    for path in ("/", "/login"):
        response = client.get(path)
        assert response.status_code == 200
        assert b"https://challenges.cloudflare.com/turnstile/v0/api.js" in response.data
        assert b'test-public-site-key' in response.data
        assert b'data-action="login"' in response.data


def test_login_rejects_missing_turnstile_token(client):
    response = client.post("/api/login", json=_credentials())
    assert response.status_code == 400
    assert "human verification" in response.get_json()["error"].lower()


def test_login_rejects_failed_turnstile_verification(client, monkeypatch):
    monkeypatch.setattr(
        "app.routes.auth_routes.verify_turnstile",
        lambda token, remote_ip: (False, "cloudflare-rejected:invalid-input-response"),
    )

    response = client.post(
        "/api/login", json=_credentials(turnstile_token="invalid-token")
    )

    assert response.status_code == 400
    assert "human verification" in response.get_json()["error"].lower()


def test_login_fails_closed_when_siteverify_is_unavailable(client, monkeypatch):
    monkeypatch.setattr(
        "app.routes.auth_routes.verify_turnstile",
        lambda token, remote_ip: (False, "verification-service-unavailable"),
    )

    response = client.post(
        "/api/login", json=_credentials(turnstile_token="valid-looking-token")
    )

    assert response.status_code == 503
    assert "temporarily unavailable" in response.get_json()["error"].lower()


def test_valid_turnstile_token_allows_normal_login(client, monkeypatch):
    monkeypatch.setattr(
        "app.routes.auth_routes.verify_turnstile",
        lambda token, remote_ip: (True, None),
    )

    response = client.post(
        "/api/login", json=_credentials(turnstile_token="valid-token")
    )

    assert response.status_code == 200
    assert response.get_json()["redirect"] == "/dashboard"


def test_disabled_turnstile_preserves_existing_login_flow(app):
    app.config["TURNSTILE_ENABLED"] = False
    client = app.test_client()

    response = client.post("/api/login", json=_credentials())

    assert response.status_code == 200
