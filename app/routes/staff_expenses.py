from __future__ import annotations

from flask import Blueprint, jsonify, request, render_template, session

from app import csrf
from app.repositories.expense_repository import ExpenseRepository
from app.services.expense_service import ExpenseService
from app.utils.auth import login_required
from app.core.socketio_handlers import emit_expenses_update
from app.core.idempotency import idempotent_request

staff_expenses_bp = Blueprint("staff_expenses", __name__, url_prefix="/expenses-view")

_service = ExpenseService(repo=ExpenseRepository())

CATEGORIES = ["supplies", "utilities", "food", "transport", "misc"]


@staff_expenses_bp.route("", methods=["GET"])
@login_required
def view_expenses() -> str:
    expenses = _service.list_all()
    return render_template("staff/expenses.html", expenses=expenses, categories=CATEGORIES)


@staff_expenses_bp.route("/api/expenses", methods=["GET"])
@login_required
def api_list_expenses() -> tuple:
    expenses = _service.list_all()
    return jsonify({"success": True, "data": expenses}), 200


@staff_expenses_bp.route("/api/expenses", methods=["POST"])
@login_required
@csrf.exempt
@idempotent_request("staff-create-expense")
def api_create_expense() -> tuple:
    data = request.get_json(silent=True) or {}
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
