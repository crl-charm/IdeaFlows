from __future__ import annotations

from math import isfinite

from flask import Blueprint, jsonify, request, render_template, session
import logging

from app import csrf
from app.core.idempotency import idempotent_request
from app.repositories.payable_repository import PayableRepository
from app.services.payable_service import PayableService
from app.utils.auth import admin_required

payables_bp = Blueprint("payables", __name__, url_prefix="/admin/payables")

_service = PayableService(repo=PayableRepository())
security_logger = logging.getLogger('security')


@payables_bp.route("", methods=["GET"])
@admin_required
def list_payables() -> str:
    return render_template("admin/payables.html")


@payables_bp.route("/api/payables", methods=["GET"])
@admin_required
def api_list_payables() -> tuple:
    payables = _service.list_all()
    return jsonify({"success": True, "data": payables}), 200


@payables_bp.route("/api/payables", methods=["POST"])
@admin_required
@csrf.exempt
@idempotent_request("admin-create-payable")
def api_create_payable() -> tuple:
    data = request.get_json() or {}
    amount_owed = float(data.get("amount_owed") or 0)
    creditor_name = data.get("creditor_name")
    user_id = session.get("user_id")
    
    if not user_id:
        return jsonify({"success": False, "error": "User session not found"}), 400
    if not isfinite(amount_owed) or amount_owed <= 0:
        return jsonify({"success": False, "error": "Amount must be greater than zero"}), 400
    
    result = _service.create(
        creditor_name=creditor_name,
        items_description=data.get("items_description"),
        amount_owed=amount_owed,
        due_date=data.get("due_date"),
        incurred_date=data.get("incurred_date"),
        created_by=user_id,
    )
    if result.get("success"):
        security_logger.info(
            f"Payable created: {creditor_name} - ₱{amount_owed:.2f} by user {session.get('username')} (ID: {session.get('user_id')})"
        )
    return jsonify(result), 201


@payables_bp.route("/api/payables/<int:p_id>/mark-paid", methods=["PATCH"])
@admin_required
@idempotent_request("admin-mark-payable-paid")
def api_mark_paid(p_id: int) -> tuple:
    data = request.get_json() or {}
    amount_val = data.get("amount")
    
    amount = None
    if amount_val is not None:
        try:
            amount = float(amount_val)
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "Invalid payment amount"}), 400
        if not isfinite(amount) or amount <= 0:
            return jsonify({"success": False, "error": "Payment amount must be greater than zero"}), 400
            
    result = _service.mark_paid(p_id, amount)
    if isinstance(result, tuple):
        return jsonify(result[0]), result[1]
        
    if result.get("success"):
        security_logger.info(
            f"Payable marked paid/partially-paid: ID {p_id} with amount {amount} by user {session.get('username')} (ID: {session.get('user_id')})"
        )
    return jsonify(result), 200


@payables_bp.route("/api/due-count", methods=["GET"])
@admin_required
def api_due_count() -> tuple:
    count = _service.get_due_count()
    return jsonify({"success": True, "count": count}), 200
