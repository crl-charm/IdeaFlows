from __future__ import annotations

from flask import Blueprint, jsonify, request, render_template, session, current_app

from app import db
from app.repositories.expense_repository import ExpenseRepository
from app.services.expense_service import ExpenseService
from app.utils.auth import admin_required
from app.core.socketio_handlers import emit_expenses_update
from app.core.idempotency import idempotent_request
from app.utils.expense_categories import EXPENSE_CATEGORIES
from app.utils.dates import manila_date
from datetime import datetime

expenses_bp = Blueprint("expenses", __name__, url_prefix="/admin/expenses")

_service = ExpenseService(repo=ExpenseRepository())

CATEGORIES = EXPENSE_CATEGORIES


@expenses_bp.after_request
def private_expenses(response):
    response.headers["Cache-Control"] = "private, no-store"
    return response


@expenses_bp.route("", methods=["GET"])
@admin_required
def list_expenses() -> str:
    expenses = _service.list_all()
    return render_template("admin/expenses.html", expenses=expenses, categories=CATEGORIES,
                           salary_employees=_service.salary_employees(),
                           current_month=manila_date(datetime.utcnow()).strftime("%Y-%m"))


@expenses_bp.route("/api/expenses", methods=["GET"])
@admin_required
def api_list_expenses() -> tuple:
    expenses = _service.list_history()
    return jsonify({"success": True, "data": expenses}), 200


@expenses_bp.route("/api/expenses", methods=["POST"])
@admin_required
@idempotent_request("admin-create-expense")
def api_create_expense() -> tuple:
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Enter a valid expense."}), 400
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
        actor_role="admin",
        salary_employee_id=data.get("salary_employee_id"),
        salary_month=data.get("salary_month"),
    )
    if isinstance(result, tuple):
        return jsonify(result[0]), result[1]
    if result.get("success"):
        try:
            emit_expenses_update('create', result.get("data", {}))
        except Exception:
            current_app.logger.exception("Expense saved; live notification failed")
    return jsonify(result), 201


@expenses_bp.patch("/api/expenses/<int:exp_id>/salary-metadata")
@admin_required
@idempotent_request("admin-classify-salary-expense")
def classify_salary(exp_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or data.get("confirmed") is not True:
        return jsonify(error="Confirm this existing payment is a salary before assigning its employee/month."), 400
    try:
        result = _service.classify_salary(exp_id, data.get("salary_employee_id"), data.get("salary_month"), session["user_id"])
    except (ValueError, PermissionError) as exc:
        db.session.rollback()
        return jsonify(error=str(exc)), 403 if isinstance(exc, PermissionError) else 400
    try:
        emit_expenses_update("update", {"expense_id": exp_id})
    except Exception:
        current_app.logger.exception("Salary classification saved; live notification failed")
    return jsonify(result), 200


@expenses_bp.route("/api/expenses/<int:exp_id>", methods=["DELETE"])
@admin_required
@idempotent_request("admin-delete-expense")
def api_delete_expense(exp_id: int) -> tuple:
    data = request.get_json(silent=True) or {}
    result = _service.delete(exp_id, session["user_id"], data.get("reason"))
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
