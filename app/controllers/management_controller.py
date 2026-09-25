from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from app.controllers.base_controller import BaseController
from app.services.management_oop_service import ManagementService
from app.utils.auth import admin_required
from app import csrf
from app.core.idempotency import idempotent_request


class ManagementController(BaseController):
    """Serves management pages and user/department APIs."""

    def __init__(self, db) -> None:
        self._service = ManagementService(db)
        self.blueprint = Blueprint("management_page", __name__)
        self._register_routes()

    def _register_routes(self) -> None:
        @self.blueprint.get("/management")
        @admin_required
        def management_home():
            data = self._service.get_summary()
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return render_template("management/_content.html", **data)
            return render_template("management/index.html", **data)

        @self.blueprint.get("/management/users")
        @admin_required
        def management_users():
            page = request.args.get("page", 1, type=int)
            return render_template("management/users.html", users=self._service.get_users(page=page, per_page=20))

        @self.blueprint.get("/management/settings")
        @admin_required
        def management_settings():
            return render_template("management/index.html", **self._service.get_summary())

        @self.blueprint.get("/api/management/users")
        @admin_required
        def management_users_api():
            page = request.args.get("page", 1, type=int)
            return jsonify({"success": True, "data": self._service.get_users(page=page, per_page=20)})

        @self.blueprint.post("/api/management/users/<int:user_id>/role")
        @admin_required
        @csrf.exempt
        @idempotent_request("admin-update-management-role")
        def management_update_role(user_id: int):
            payload = request.get_json(silent=True) or {}
            updated = self._service.update_role(user_id, str(payload.get("role", "")))
            return jsonify({"success": updated})



    def get_dashboard_data(self) -> dict:
        return self._service.get_dashboard_data()
