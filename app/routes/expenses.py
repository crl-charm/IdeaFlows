from __future__ import annotations

from flask import Blueprint, jsonify, request, render_template, session

from app import csrf
from app.repositories.expense_repository import ExpenseRepository
from app.services.expense_service import ExpenseService
from app.utils.auth import admin_required
from app.core.socketio_handlers import emit_expenses_update
from app.core.idempotency import idempotent_request

expenses_bp = Blueprint("expenses", __name__, url_prefix="/admin/expenses")

_service = ExpenseService(repo=ExpenseRepository())

CATEGORIES = ["supplies", "utilities", "food", "transport", "misc"]


@expenses_bp.route("", methods=["GET"])
@admin_required
def list_expenses() -> str:
    expenses = _service.list_all()
    return render_template("admin/expenses.html", expenses=expenses, categories=CATEGORIES)


@expenses_bp.route("/api/expenses", methods=["GET"])
@admin_required
def api_list_expenses() -> tuple:
    expenses = _service.list_all()
    return jsonify({"success": True, "data": expenses}), 200


@expenses_bp.route("/api/expenses", methods=["POST"])
@admin_required
@csrf.exempt
@idempotent_request("admin-create-expense")
def api_create_expense() -> tuple:
    data = request.get_json()
    user_id = session.get("user_id")
    
    if not user_id:
        return jsonify({"success": False, "error": "User session not found"}), 400
    
    try:
        amount = float(data.get("amount"))
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "Invalid amount"}), 400

    result = _service.create(
        category=data.get("category"),
        description=data.get("description"),
        amount=amount,
        expense_date=data.get("expense_date"),
        logged_by=user_id,
    )
    if result.get("success"):
        emit_expenses_update('create', result.get("data", {}))
    return jsonify(result), 201


@expenses_bp.route("/api/expenses/<int:exp_id>", methods=["DELETE"])
@admin_required
def api_delete_expense(exp_id: int) -> tuple:
    result = _service.delete(exp_id)
    if isinstance(result, tuple):
        return jsonify(result[0]), result[1]
    if result.get("success"):
        emit_expenses_update('delete', {'expense_id': exp_id})
    return jsonify(result), 200


@expenses_bp.route("/api/expenses/by-date/<date_str>", methods=["GET"])
@admin_required
def api_by_date(date_str: str) -> tuple:
    expenses = _service.list_by_date(date_str)
    return jsonify({"success": True, "data": expenses}), 200
