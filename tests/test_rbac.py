"""RBAC tests for admin vs staff route access."""

from __future__ import annotations

import pytest

from app import create_app


@pytest.fixture
def app():
    application = create_app()
    application.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
    )
    return application


@pytest.fixture
def client(app):
    return app.test_client()


def _set_session(client, role: str, user_id: int = 1):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["username"] = f"test_{role}"
        sess["role"] = role
        sess["last_activity"] = __import__("datetime").datetime.utcnow().timestamp()


class TestAdminRBAC:
    def test_staff_denied_admin_inventory_page(self, client):
        _set_session(client, "staff")
        response = client.get("/admin/inventory")
        assert response.status_code in (302, 403)
        if response.status_code == 302:
            assert "/dashboard" in response.headers.get("Location", "")

    def test_staff_denied_admin_inventory_api(self, client):
        _set_session(client, "staff")
        response = client.get(
            "/admin/inventory/api/dashboard-items",
            headers={"Accept": "application/json"},
        )
        assert response.status_code == 403
        data = response.get_json()
        assert data is not None
        assert data.get("success") is False

    def test_admin_allowed_admin_inventory_page(self, client):
        _set_session(client, "admin")
        response = client.get("/admin/inventory")
        assert response.status_code == 200

    def test_admin_allowed_admin_inventory_api(self, client):
        _set_session(client, "admin")
        response = client.get(
            "/admin/inventory/api/dashboard-items",
            headers={"Accept": "application/json"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data is not None
        assert data.get("success") is True

    def test_staff_denied_admin_root(self, client):
        _set_session(client, "staff")
        response = client.get("/admin")
        assert response.status_code in (302, 403)

    def test_staff_denied_analytics_api(self, client):
        _set_session(client, "staff")
        response = client.get(
            "/api/analytics/daily-revenue",
            headers={"Accept": "application/json"},
        )
        assert response.status_code == 403

    def test_staff_allowed_dashboard(self, client):
        _set_session(client, "staff")
        response = client.get("/dashboard")
        assert response.status_code == 200

    def test_staff_allowed_staff_inventory(self, client):
        _set_session(client, "staff")
        response = client.get("/inventory")
        assert response.status_code == 200

    def test_staff_receivables_badge_uses_staff_authorized_endpoint(self, client):
        _set_session(client, "staff")
        response = client.get(
            "/receivables-view/api/receivables/unpaid",
            headers={"Accept": "application/json"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data is not None
        assert data.get("success") is True

    def test_staff_remains_denied_from_admin_receivables_badge_endpoint(self, client):
        _set_session(client, "staff")
        response = client.get(
            "/admin/receivables/api/receivables/unpaid",
            headers={"Accept": "application/json"},
        )
        assert response.status_code == 403

    def test_unauthenticated_redirects_from_admin(self, client):
        response = client.get("/admin/inventory")
        assert response.status_code == 302
        assert "/login" in response.headers.get("Location", "")

    def test_staff_daily_sales_redirects_to_dashboard(self, client):
        _set_session(client, "staff")
        response = client.get("/daily-sales")
        assert response.status_code == 302
        assert "/dashboard" in response.headers.get("Location", "")

    def test_admin_daily_sales_redirects_to_admin_balance(self, client):
        _set_session(client, "admin")
        response = client.get("/daily-sales")
        assert response.status_code == 302
        assert "/admin/daily-balance" in response.headers.get("Location", "")

    def test_admin_navigation_does_not_show_staff_operations(self, client):
        _set_session(client, "admin")
        response = client.get("/admin")

        assert response.status_code == 200
        assert b">Operations<" not in response.data
        assert b">Management<" in response.data
        assert b">Finance<" in response.data

    def test_staff_navigation_keeps_operations(self, client):
        _set_session(client, "staff")
        response = client.get("/dashboard")

        assert response.status_code == 200
        assert b">Operations<" in response.data
