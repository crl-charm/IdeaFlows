from __future__ import annotations

from math import isfinite

from flask import Blueprint, jsonify, render_template, request

from app.repositories.receivable_repository import ReceivableRepository
from app.services.receivable_service import ReceivableService
from app.utils.auth import login_required
from app.core.idempotency import idempotent_request

staff_receivables_bp = Blueprint("staff_receivables", __name__, url_prefix="/receivables-view")

_service = ReceivableService(repo=ReceivableRepository())


@staff_receivables_bp.route("", methods=["GET"])
@login_required
def view_receivables() -> str:
    return render_template("staff/receivables.html")


@staff_receivables_bp.route("/api/receivables", methods=["GET"])
@login_required
def api_list_receivables() -> tuple:
    if "page" in request.args:
        page = max(request.args.get("page", 1, type=int), 1)
        per_page = min(max(request.args.get("per_page", 50, type=int), 1), 100)
        result = _service.list_paginated(
            page,
            per_page,
            status=request.args.get("status"),
            search=request.args.get("search"),
        )
        return jsonify({"success": True, **result}), 200
    return jsonify({"success": True, "data": _service.list_all()}), 200


@staff_receivables_bp.route("/api/receivables/unpaid", methods=["GET"])
@login_required
def api_unpaid_receivables() -> tuple:
    """Return the small overdue/unpaid dataset used by the staff badge."""
    receivables = _service.list_unpaid()
    return jsonify({"success": True, "data": receivables}), 200


@staff_receivables_bp.route("/api/receivables", methods=["POST"])
@login_required
@idempotent_request("staff-create-receivable")
def api_create_receivable() -> tuple:
    from flask import session

    data = request.get_json(silent=True) or {}
    user_id = session.get("user_id")

    if not user_id:
        return jsonify({"success": False, "error": "User session not found"}), 400

    try:
        amount = float(data.get("amount_owed"))
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "Invalid amount"}), 400
    if not isfinite(amount) or amount <= 0:
        return jsonify({"success": False, "error": "Amount must be greater than zero"}), 400

    result = _service.create(
        customer_name=data.get("customer_name"),
        customer_contact=data.get("customer_contact"),
        items_description=data.get("items_description"),
        amount_owed=amount,
        due_date=data.get("due_date"),
        created_by=user_id,
        session_id=session.get("session_id"),
        approved_by_staff=data.get("approved_by_staff"),
        incurred_date=data.get("incurred_date"),
    )
    return jsonify(result), 201
