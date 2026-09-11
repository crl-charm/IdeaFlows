from __future__ import annotations

import pytest
from flask import jsonify

from app import create_app
from app.core.idempotency import idempotent_request


@pytest.fixture
def app():
    application = create_app()
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    calls = {"protected": 0, "retryable": 0}

    @application.post("/_test/idempotent-write")
    @idempotent_request("test-write")
    def protected_write():
        calls["protected"] += 1
        return jsonify({"success": True, "calls": calls["protected"]})

    @application.post("/_test/retryable-write")
    @idempotent_request("test-retry")
    def retryable_write():
        calls["retryable"] += 1
        status = 503 if calls["retryable"] == 1 else 200
        return jsonify({"success": status == 200}), status

    application.extensions["idempotency_test_calls"] = calls
    return application


@pytest.fixture
def client(app):
    return app.test_client()


def test_same_idempotency_key_runs_write_only_once(app, client):
    headers = {"Idempotency-Key": "one-browser-action"}

    first = client.post("/_test/idempotent-write", headers=headers)
    duplicate = client.post("/_test/idempotent-write", headers=headers)

    assert first.status_code == 200
    assert duplicate.status_code == 409
    assert duplicate.get_json()["duplicate"] is True
    assert app.extensions["idempotency_test_calls"]["protected"] == 1


def test_different_or_missing_keys_remain_independent(app, client):
    assert client.post("/_test/idempotent-write").status_code == 200
    assert client.post("/_test/idempotent-write").status_code == 200
    assert client.post(
        "/_test/idempotent-write", headers={"Idempotency-Key": "key-a"}
    ).status_code == 200
    assert client.post(
        "/_test/idempotent-write", headers={"Idempotency-Key": "key-b"}
    ).status_code == 200

    assert app.extensions["idempotency_test_calls"]["protected"] == 4


def test_server_failure_releases_key_for_safe_retry(app, client):
    headers = {"Idempotency-Key": "retry-after-server-error"}

    failed = client.post("/_test/retryable-write", headers=headers)
    retried = client.post("/_test/retryable-write", headers=headers)

    assert failed.status_code == 503
    assert retried.status_code == 200
    assert app.extensions["idempotency_test_calls"]["retryable"] == 2
