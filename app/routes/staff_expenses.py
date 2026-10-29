from __future__ import annotations

from flask import Blueprint, jsonify, request, render_template, session, current_app

from app.repositories.expense_repository import ExpenseRepository
from app.services.expense_service import ExpenseService
from app.utils.auth import staff_or_admin_required
from app.core.socketio_handlers import emit_expenses_update
from app.core.idempotency import idempotent_request
from app.utils.expense_categories import EXPENSE_CATEGORIES, expense_category

staff_expenses_bp = Blueprint("staff_expenses", __name__, url_prefix="/expenses-view")

_service = ExpenseService(repo=ExpenseRepository())

CATEGORIES = {key: label for key, label in EXPENSE_CATEGORIES.items() if key != "salaries"}


@staff_expenses_bp.after_request
def private_expenses(response):
    response.headers["Cache-Control"] = "private, no-store"
    return response


@staff_expenses_bp.route("", methods=["GET"])
@staff_or_admin_required
def view_expenses() -> str:
    expenses = _service.list_history(include_salary=False)
    return render_template("staff/expenses.html", expenses=expenses, categories=CATEGORIES)


@staff_expenses_bp.route("/api/expenses", methods=["GET"])
@staff_or_admin_required
def api_list_expenses() -> tuple:
    expenses = _service.list_history(include_salary=False)
    return jsonify({"success": True, "data": expenses}), 200


@staff_expenses_bp.route("/api/expenses", methods=["POST"])
@staff_or_admin_required
@idempotent_request("staff-create-expense")
def api_create_expense() -> tuple:
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify(error="Enter a valid expense."), 400
    if expense_category(data.get("category")) == "salaries" or any(key.startswith("salary_") for key in data):
        return jsonify(error="Salary records are admin-only. Use an ordinary expense category."), 403
    user_id = session.get("user_id")

    if not user_id:
        return jsonify({"success": False, "error": "User session not found"}), 400

    result = _service.create(
        category=data.get("category"),
        description=data.get("description"),
        amount=data.get("amount"),
        expense_date=data.get("expense_date"),
        logged_by=user_id,
        payment_method=data.get("payment_method"),
        request_key=request.headers.get("Idempotency-Key"),
        cash_box=data.get("cash_box"),
        repay_owner=data.get("repay_owner"),
    )
    if isinstance(result, tuple):
        return jsonify(result[0]), result[1]
    if result.get("success"):
        try:
            emit_expenses_update('create', result.get("data", {}))
        except Exception:
            current_app.logger.exception("Expense saved; live notification failed")
    return jsonify(result), 201
