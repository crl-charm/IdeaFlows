from __future__ import annotations

import pytest
from flask import jsonify

from app import create_app
from app.core.idempotency import idempotent_request
from app.models.expense import Expense


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


def test_every_business_write_route_has_idempotency_protection(app):
    excluded_endpoints = {
        "auth.login_api",
        "honeypot_trap",
        "decoy_wp-login_php",
        "decoy_wp-admin",
        "decoy_phpmyadmin",
        "decoy__env",
        "decoy__git_config",
        "decoy_xmlrpc_php",
        "protected_write",
        "retryable_write",
    }
    write_methods = {"POST", "PUT", "PATCH", "DELETE"}
    unprotected = []
    for rule in app.url_map.iter_rules():
        if not (rule.methods & write_methods) or rule.endpoint in excluded_endpoints:
            continue
        view = app.view_functions[rule.endpoint]
        if not getattr(view, "_idempotency_action", None):
            methods = ",".join(sorted(rule.methods & write_methods))
            unprotected.append(f"{methods} {rule.rule}")

    assert unprotected == []


def test_shared_fetch_keeps_an_uncertain_write_key_for_retry():
    from pathlib import Path

    layout = (
        Path(__file__).resolve().parents[1] / "app" / "templates" / "layout.html"
    ).read_text(encoding="utf-8")
    assert "ideaflow:pending-write:" in layout
    assert "headers.set('Idempotency-Key', automaticRequestKey)" in layout
    assert "response.status < 500" in layout


def test_real_expense_route_commits_only_once_for_duplicate_key(app, client):
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["username"] = "test_admin"
        sess["role"] = "admin"

    payload = {
        "category": "Utilities",
        "description": "Phase 5 duplicate test",
        "amount": 125.50,
        "expense_date": "2026-09-13",
    }
    headers = {"Idempotency-Key": "phase5-real-expense-write"}
    first = client.post("/admin/expenses/api/expenses", json=payload, headers=headers)
    duplicate = client.post("/admin/expenses/api/expenses", json=payload, headers=headers)

    assert first.status_code == 201
    assert duplicate.status_code == 409
    with app.app_context():
        assert Expense.query.filter_by(description=payload["description"]).count() == 1
