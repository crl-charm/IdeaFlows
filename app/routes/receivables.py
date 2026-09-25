from __future__ import annotations

from math import isfinite

from flask import Blueprint, jsonify, request, render_template, session

from app import csrf
from app.repositories.receivable_repository import ReceivableRepository
from app.services.receivable_service import ReceivableService
from app.utils.auth import admin_required
from app.core.socketio_handlers import emit_receivables_update
from app.core.idempotency import idempotent_request

receivables_bp = Blueprint("receivables", __name__, url_prefix="/admin/receivables")

_service = ReceivableService(repo=ReceivableRepository())


@receivables_bp.route("", methods=["GET"])
@admin_required
def list_receivables() -> str:
    return render_template("admin/receivables.html")


@receivables_bp.route("/api/receivables", methods=["GET"])
@admin_required
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


@receivables_bp.route("/api/receivables", methods=["POST"])
@admin_required
@csrf.exempt
@idempotent_request("admin-create-receivable")
def api_create_receivable() -> tuple:
    data = request.get_json(silent=True) or {}
    user_id = session.get("user_id")
    
    if not user_id:
        return jsonify({"success": False, "error": "User session not found"}), 400
    
    try:
        amount_owed = float(data.get("amount_owed"))
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "Invalid amount"}), 400
    if not isfinite(amount_owed) or amount_owed <= 0:
        return jsonify({"success": False, "error": "Amount must be greater than zero"}), 400

    try:
        result = _service.create(
            customer_name=data.get("customer_name"),
            customer_contact=data.get("customer_contact"),
            items_description=data.get("items_description"),
            amount_owed=amount_owed,
            due_date=data.get("due_date"),
            created_by=user_id,
            session_id=data.get("session_id"),
            approved_by_staff=data.get("approved_by_staff"),
            incurred_date=data.get("incurred_date"),
            notes=data.get("notes"),
        )
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    if result.get("success"):
        emit_receivables_update('create', result.get("data", {}))
    return jsonify(result), 201


@receivables_bp.route("/api/receivables/<int:rec_id>/mark-paid", methods=["PATCH"])
@admin_required
@idempotent_request("admin-mark-receivable-paid")
def api_mark_paid(rec_id: int) -> tuple:
    data = request.get_json(silent=True) or {}
    result = _service.mark_paid(rec_id, data.get("amount"), session["user_id"], data.get("payment_method", "cash"))
    if isinstance(result, tuple):
        return jsonify(result[0]), result[1]
    if result.get("success"):
        emit_receivables_update('mark_paid', {'receivable_id': rec_id})
    return jsonify(result), 200


@receivables_bp.route("/api/receivables/customer-payment", methods=["POST"])
@admin_required
@idempotent_request("admin-record-customer-payment")
def api_record_customer_payment() -> tuple:
    data = request.get_json(silent=True) or {}
    result = _service.record_customer_payment(
        data.get("customer_name"), data.get("amount"), session["user_id"],
        data.get("payment_method", "cash"), data.get("customer_contact", ""),
    )
    if isinstance(result, tuple):
        return jsonify(result[0]), result[1]
    if result.get("success"):
        emit_receivables_update('mark_paid', {'customer_name': data.get("customer_name")})
    return jsonify(result), 200


@receivables_bp.route("/api/receivables/customer-payments", methods=["GET"])
@admin_required
def api_customer_payments() -> tuple:
    customer_name = request.args.get("customer_name", "").strip()
    if not customer_name:
        return jsonify({"success": False, "error": "Customer name is required"}), 400
    return jsonify({"success": True, "data": _service.list_customer_payments(customer_name, request.args.get("customer_contact", ""))}), 200


@receivables_bp.route("/api/receivables/<int:rec_id>/notes", methods=["PATCH"])
@admin_required
@idempotent_request("admin-update-receivable-notes")
def api_update_notes(rec_id: int) -> tuple:
    data = request.get_json(silent=True) or {}
    notes = data.get("notes")
    if not isinstance(notes, str):
        return jsonify({"error": "Notes must be text"}), 400
    result = _service.update_notes(rec_id, notes)
    if isinstance(result, tuple):
        return jsonify(result[0]), result[1]
    emit_receivables_update('update', {'receivable_id': rec_id})
    return jsonify(result), 200


@receivables_bp.route("/api/receivables/unpaid", methods=["GET"])
@admin_required
def api_unpaid() -> tuple:
    receivables = _service.list_unpaid()
    return jsonify({"success": True, "data": receivables}), 200
