from __future__ import annotations

from flask import Blueprint, jsonify, request, render_template

from app.repositories.staff_repository import StaffRepository
from app.services.staff_performance_service import StaffPerformanceService
from app.utils.auth import admin_required
from app import csrf
from app.core.idempotency import idempotent_request

staff_performance_bp = Blueprint(
    "staff_performance", __name__, url_prefix="/admin/staff-performance"
)

_service = StaffPerformanceService(repo=StaffRepository())


@staff_performance_bp.route("", methods=["GET"])
@admin_required
def leaderboard() -> str:
    logs = _service.list_all()
    return render_template("admin/staff_performance.html", logs=logs)


@staff_performance_bp.route("/api/logs", methods=["GET"])
@admin_required
def api_list_logs() -> tuple:
    logs = _service.list_all()
    return jsonify({"success": True, "data": logs}), 200


@staff_performance_bp.route("/api/logs", methods=["POST"])
@admin_required
@csrf.exempt
@idempotent_request("admin-create-staff-performance-log")
def api_create_log() -> tuple:
    data = request.get_json()
    result = _service.create(
        user_id=data.get("user_id"),
        shift_date=data.get("shift_date"),
        customers_served=int(data.get("customers_served", 0)),
        admin_note=data.get("admin_note"),
    )
    return jsonify(result), 201


@staff_performance_bp.route("/api/logs/by-date/<date_str>", methods=["GET"])
@admin_required
def api_by_date(date_str: str) -> tuple:
    logs = _service.list_by_date(date_str)
    return jsonify({"success": True, "data": logs}), 200


@staff_performance_bp.route("/api/logs/by-user/<int:user_id>", methods=["GET"])
@admin_required
def api_by_user(user_id: int) -> tuple:
    logs = _service.list_by_user(user_id)
    return jsonify({"success": True, "data": logs}), 200
