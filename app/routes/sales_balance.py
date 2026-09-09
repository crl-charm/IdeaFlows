from __future__ import annotations

from datetime import date
from typing import Any

from flask import Blueprint, request, render_template, session

from app.dto.api_response import api_error, api_ok

from app.utils.billing import calculate_time_bill
from app import db, csrf
from app.repositories.sales_repository import SalesRepository
from app.services.daily_balance_export_service import DailyBalanceExportService
from app.services.sales_service import SalesService
from app.utils.auth import admin_required

sales_bp = Blueprint("sales_admin", __name__, url_prefix="/admin/daily-balance")

_service = SalesService(repo=SalesRepository())
_export = DailyBalanceExportService(db)


@sales_bp.route("", methods=["GET"])
@admin_required
def list_reports() -> str:
    reports = _service.list_reports()
    soft_entries = _service.list_soft_balances()
    return render_template("admin/daily_balance.html", reports=reports, soft_entries=soft_entries)


@sales_bp.route("/api/reports", methods=["GET"])
@admin_required
def api_list_reports() -> tuple:
    reports = _service.list_reports()
    return api_ok(reports)


@sales_bp.route("/api/reports", methods=["POST"])
@admin_required
@csrf.exempt
def api_generate_report() -> tuple:
    data = request.get_json()
    report_date = date.fromisoformat(data.get("report_date"))
    user_id = session.get("user_id")
    
    if not user_id:
        return api_error("User session not found", status=400)
    
    result = _service.generate_report(
        report_date=report_date,
        generated_by=user_id,
        notes=data.get("notes"),
    )
    return api_ok(result.get("data"), status=201)


@sales_bp.route("/api/reports/export-csv", methods=["GET"])
@admin_required
def api_export_csv() -> Any:
    start_date_str = request.args.get("start_date")
    end_date_str = request.args.get("end_date")
    reports = _service.list_reports()
    if start_date_str and start_date_str.strip():
        reports = [r for r in reports if r["report_date"] >= start_date_str]
    if end_date_str and end_date_str.strip():
        reports = [r for r in reports if r["report_date"] <= end_date_str]
    return _export.export_csv(reports)


@sales_bp.route("/api/reports/export-pdf", methods=["GET"])
@admin_required
def api_export_pdf() -> Any:
    try:
        start_date_str = request.args.get("start_date")
        end_date_str = request.args.get("end_date")
        reports = _service.list_reports()
        soft_entries = _service.list_soft_balances()
        if start_date_str and start_date_str.strip():
            reports = [r for r in reports if r["report_date"] >= start_date_str]
            soft_entries = [s for s in soft_entries if s["balance_date"] >= start_date_str]
        if end_date_str and end_date_str.strip():
            reports = [r for r in reports if r["report_date"] <= end_date_str]
            soft_entries = [s for s in soft_entries if s["balance_date"] <= end_date_str]
        return _export.export_pdf(reports, soft_entries)
    except Exception as e:
        return api_error(f"Failed to export PDF: {str(e)}", status=500)


@sales_bp.route("/api/reports/export-excel", methods=["GET"])
@admin_required
def api_export_excel() -> Any:
    try:
        start_date_str = request.args.get("start_date")
        end_date_str = request.args.get("end_date")
        reports = _service.list_reports()
        if start_date_str and start_date_str.strip():
            reports = [r for r in reports if r["report_date"] >= start_date_str]
        if end_date_str and end_date_str.strip():
            reports = [r for r in reports if r["report_date"] <= end_date_str]
        return _export.export_excel(reports)
    except Exception as e:
        return api_error(f"Failed to export Excel: {str(e)}", status=500)


@sales_bp.route("/api/soft-balances", methods=["GET"])
@admin_required
def api_list_soft_balances() -> tuple:
    entries = _service.list_soft_balances()
    return api_ok(entries)


@sales_bp.route("/api/soft-balances", methods=["POST"])
@admin_required
@csrf.exempt
def api_create_soft_balance() -> tuple:
    data = request.get_json()
    balance_date = date.fromisoformat(data.get("balance_date"))
    period = (data.get("period") or "AM").upper()
    user_id = session.get("user_id")
    
    if not user_id:
        return api_error("User session not found", status=400)
    
    result = _service.create_soft_balance(
        balance_date=balance_date,
        period=period,
        generated_by=user_id,
        notes=data.get("notes"),
    )
    return api_ok(result.get("data"), status=201)


@sales_bp.route("/api/today-stats", methods=["GET"])
@admin_required
def api_today_stats() -> tuple:
    from app.models import Transaction, CustomerSession, Receivable, Order, OrderItem
    from datetime import datetime, date
    from sqlalchemy import func
    from decimal import Decimal

    today = date.today()

    # 1. Cash on Hand
    transactions_today = Transaction.query.filter(func.date(Transaction.created_at) == today).all()
    cash_on_hand = sum(tx.total_bill for tx in transactions_today)

    # 2. Expected Cash on Hand (Cash on Hand + Sum of pending balances of active sessions)
    pending_balance_sum = Decimal("0.00")
    active_sessions = CustomerSession.query.filter_by(status="active").all()
    now = datetime.utcnow()
    for sess in active_sessions:
        minutes_used = (now - sess.time_in).total_seconds() / 60
        rate = sess.space_type.rate_per_minute if sess.space_type else Decimal("0.00")
        time_bill = calculate_time_bill(sess.space_type, minutes_used)
        
        food_total = (
            db.session.query(func.coalesce(func.sum(OrderItem.quantity * OrderItem.price), 0))
            .select_from(OrderItem)
            .join(Order, OrderItem.order_id == Order.id)
            .filter(Order.customer_session_id == sess.id)
            .scalar()
        ) or Decimal("0.00")
        
        pending_balance_sum += time_bill + Decimal(str(food_total))

    expected_cash_on_hand = cash_on_hand + pending_balance_sum

    # 3. Today's Paid Receivables
    receivables_paid_today = Receivable.query.filter(
        Receivable.paid == True,
        func.date(Receivable.paid_at) == today
    ).all()
    
    debtors_count = len(receivables_paid_today)
    total_collected = sum(r.amount_owed - r.partial_paid for r in receivables_paid_today)

    return api_ok({
        "cash_on_hand": float(cash_on_hand),
        "expected_cash_on_hand": float(expected_cash_on_hand),
        "receivables_paid_today": debtors_count,
        "receivables_collected_today": float(total_collected)
    })

