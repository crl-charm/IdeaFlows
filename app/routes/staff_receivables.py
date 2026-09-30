from __future__ import annotations

from math import isfinite

from flask import Blueprint, jsonify, render_template, request, session

from app.repositories.receivable_repository import ReceivableRepository
from app.services.receivable_service import ReceivableService
from app.utils.auth import login_required
from app.core.idempotency import idempotent_request
from app.core.socketio_handlers import emit_receivables_update

staff_receivables_bp = Blueprint("staff_receivables", __name__, url_prefix="/receivables-view")

_service = ReceivableService(repo=ReceivableRepository())


@staff_receivables_bp.route("", methods=["GET"])
@login_required
def view_receivables() -> str:
    return render_template("staff/receivables.html")


@staff_receivables_bp.route("/api/receivables", methods=["GET"])
@login_required
def api_list_receivables() -> tuple:
    if any(key in request.args for key in ("page", "date", "search", "status", "per_page")):
        try:
            page, per_page, status, search, chosen = _service.parse_filters(request.args)
        except ValueError as exc:
            return jsonify({"success": False, "error": str(exc)}), 400
        result = _service.list_paginated(
            page, per_page, status=status, search=search, incurred_date=chosen,
        )
        result["totals"] = _service.totals(chosen)
        return jsonify({"success": True, **result}), 200
    return jsonify({"success": True, "data": _service.list_all()}), 200


@staff_receivables_bp.get("/api/receivables/tabs")
@login_required
def api_tabs() -> tuple:
    try:
        page, per_page, _, search, chosen = _service.parse_filters(request.args)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    return jsonify({"success": True, **_service.tabs(chosen, search, page, per_page)}), 200


@staff_receivables_bp.get("/api/receivables/tabs/<int:tab_id>")
@login_required
def api_tab_detail(tab_id: int) -> tuple:
    detail = _service.tab_detail(tab_id)
    return (jsonify({"success": True, "data": detail}), 200) if detail else (jsonify({"error": "Tab not found"}), 404)


@staff_receivables_bp.route("/api/receivables/tabs/<int:tab_id>/payments", methods=["GET", "POST"])
@login_required
@idempotent_request("staff-tab-receivable-payment")
def api_tab_payments(tab_id: int) -> tuple:
    if request.method == "GET":
        if not _service.tab_detail(tab_id):
            return jsonify({"error": "Tab not found"}), 404
        return jsonify({"success": True, "data": _service.list_customer_payments(tab_id=tab_id)}), 200
    data = request.get_json(silent=True) or {}
    result = _service.record_customer_payment("", data.get("amount"), session["user_id"],
                                              data.get("payment_method", "cash"), "",
                                              request.headers.get("Idempotency-Key"), tab_id=tab_id)
    if isinstance(result, tuple):
        return jsonify(result[0]), result[1]
    emit_receivables_update("mark_paid", {"tab_id": tab_id})
    return jsonify(result), 200


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

    try:
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
            notes=data.get("notes"),
            tab_id=data.get("tab_id"),
        )
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    return jsonify(result), 201


@staff_receivables_bp.route("/api/receivables/customer-payment", methods=["POST"])
@login_required
@idempotent_request("staff-record-customer-payment")
def api_record_customer_payment() -> tuple:
    data = request.get_json(silent=True) or {}
    result = _service.record_customer_payment(
        data.get("customer_name"), data.get("amount"), session["user_id"],
        data.get("payment_method", "cash"), data.get("customer_contact", ""), request.headers.get("Idempotency-Key"),
    )
    if isinstance(result, tuple):
        return jsonify(result[0]), result[1]
    emit_receivables_update("mark_paid", {"customer_name": data.get("customer_name")})
    return jsonify(result), 200


@staff_receivables_bp.route("/api/receivables/customer-payments", methods=["GET"])
@login_required
def api_customer_payments() -> tuple:
    customer_name = request.args.get("customer_name", "").strip()
    if not customer_name:
        return jsonify({"success": False, "error": "Customer name is required"}), 400
    return jsonify({"success": True, "data": _service.list_customer_payments(customer_name, request.args.get("customer_contact", ""))}), 200


@staff_receivables_bp.route("/api/receivables/<int:rec_id>/notes", methods=["PATCH"])
@login_required
@idempotent_request("staff-update-receivable-notes")
def api_update_notes(rec_id: int) -> tuple:
    data = request.get_json(silent=True) or {}
    notes = data.get("notes")
    if not isinstance(notes, str):
        return jsonify({"error": "Notes must be text"}), 400
    result = _service.update_notes(rec_id, notes)
    if isinstance(result, tuple):
        return jsonify(result[0]), result[1]
    return jsonify(result), 200
