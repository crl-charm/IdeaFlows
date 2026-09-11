from __future__ import annotations

import pytest

from app import create_app
from app.core.cache import get_or_set_json, invalidate_namespace


@pytest.fixture
def app():
    application = create_app()
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return application


@pytest.fixture
def client(app):
    return app.test_client()


def test_liveness_probe_and_observability_headers(client):
    response = client.get("/health/live", headers={"X-Request-ID": "probe-123"})

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}
    assert response.headers["X-Request-ID"] == "probe-123"
    assert response.headers["Server-Timing"].startswith("app;dur=")


def test_invalid_request_id_is_not_reflected(client):
    response = client.get("/health/live", headers={"X-Request-ID": "bad id value"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] != "bad id value"
    assert len(response.headers["X-Request-ID"]) == 32


def test_readiness_probe_checks_database(client):
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ready"}


def test_static_cache_policy_distinguishes_deployable_and_uploaded_assets(client):
    css_response = client.get("/static/css/style.css")
    upload_response = client.get("/static/uploads/background.jpg")

    assert css_response.status_code == 200
    assert css_response.headers["Cache-Control"] == "public, max-age=3600, must-revalidate"
    assert upload_response.status_code == 200
    assert upload_response.headers["Cache-Control"] == "public, max-age=31536000, immutable"


class FakeRedis:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def setex(self, key, timeout, value):
        self.values[key] = value

    def scan_iter(self, match, count=100):
        prefix = match.removesuffix("*")
        return (key for key in list(self.values) if key.startswith(prefix))

    def unlink(self, *keys):
        for key in keys:
            self.values.pop(key, None)


def test_redis_read_through_cache_and_invalidation(app):
    fake_redis = FakeRedis()
    calls = []
    app.extensions["redis_health"] = fake_redis
    app.config.update(CACHE_ENABLED=True, CACHE_DEFAULT_TIMEOUT=60)

    with app.app_context():
        first = get_or_set_json("menu:all", lambda: calls.append(1) or [{"id": 1}])
        second = get_or_set_json("menu:all", lambda: calls.append(2) or [])

        assert first == second == [{"id": 1}]
        assert calls == [1]

        invalidate_namespace("menu")
        third = get_or_set_json("menu:all", lambda: calls.append(3) or [{"id": 2}])

    assert third == [{"id": 2}]
    assert calls == [1, 3]
