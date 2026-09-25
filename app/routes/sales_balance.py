from __future__ import annotations

from datetime import date
from typing import Any

from flask import Blueprint, request, render_template, session

from app.dto.api_response import api_error, api_ok

from app.utils.billing import calculate_time_bill
from app import db, csrf
from app.core.idempotency import idempotent_request
from app.repositories.sales_repository import SalesRepository
from app.services.daily_balance_export_service import DailyBalanceExportService
from app.services.sales_service import SalesService
from app.utils.auth import admin_required, login_required

sales_bp = Blueprint("sales_admin", __name__, url_prefix="/admin/daily-balance")

_service = SalesService(repo=SalesRepository())
_export = DailyBalanceExportService(db)


@sales_bp.route("", methods=["GET"])
@login_required
def list_reports() -> str:
    reports = _service.list_reports()
    soft_entries = _service.list_soft_balances()
    return render_template("admin/daily_balance.html", reports=reports, soft_entries=soft_entries)


@sales_bp.route("/api/reports", methods=["GET"])
@login_required
def api_list_reports() -> tuple:
    reports = _service.list_reports()
    return api_ok(reports)


@sales_bp.route("/api/reports", methods=["POST"])
@admin_required
@csrf.exempt
@idempotent_request("admin-generate-sales-report")
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
@login_required
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
@login_required
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
@login_required
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
@login_required
def api_list_soft_balances() -> tuple:
    entries = _service.list_soft_balances()
    return api_ok(entries)


@sales_bp.route("/api/soft-balances", methods=["POST"])
@admin_required
@csrf.exempt
@idempotent_request("admin-create-soft-balance")
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
@login_required
def api_today_stats() -> tuple:
    from app.models import Transaction, CustomerSession, Receivable, ReceivablePayment, Expense, Order, OrderItem
    from datetime import datetime, timedelta
    from sqlalchemy import func
    from sqlalchemy.orm import selectinload
    from decimal import Decimal
    from app.utils.dates import day_bounds

    now = datetime.utcnow()
    today = (now + timedelta(hours=8)).date()
    local_start, local_end = day_bounds(today)
    start_at, end_at = local_start - timedelta(hours=8), local_end - timedelta(hours=8)

    # 1. Cash on Hand
    cash_checkouts = (
        db.session.query(func.coalesce(func.sum(Transaction.total_bill), 0))
        .filter(Transaction.created_at >= start_at, Transaction.created_at < end_at, Transaction.payment_method == "cash")
        .scalar()
    ) or Decimal("0.00")
    cash_collections = (
        db.session.query(func.coalesce(func.sum(ReceivablePayment.amount), 0))
        .filter(ReceivablePayment.received_at >= start_at, ReceivablePayment.received_at < end_at,
                ReceivablePayment.payment_method == "cash")
        .scalar()
    ) or Decimal("0.00")
    expenses_today = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(Expense.expense_date == today)
        .scalar()
    ) or Decimal("0.00")
    cash_on_hand = Decimal(str(cash_checkouts)) + Decimal(str(cash_collections)) - Decimal(str(expenses_today))

    # Money still owed by active sessions and receivable customers.
    pending_balance_sum = Decimal("0.00")
    active_sessions = (
        CustomerSession.query.options(selectinload(CustomerSession.space_type))
        .filter_by(status="active")
        .all()
    )
    session_ids = [active_session.id for active_session in active_sessions]
    from app.repositories.session_repository import SessionRepository
    bookings = SessionRepository().get_active_boardroom_bookings_by_session_ids(session_ids)
    food_totals = {}
    if session_ids:
        food_totals = dict(
            db.session.query(
                Order.customer_session_id,
                func.coalesce(func.sum(OrderItem.quantity * OrderItem.price), 0),
            )
            .join(Order, OrderItem.order_id == Order.id)
            .filter(Order.customer_session_id.in_(session_ids))
            .group_by(Order.customer_session_id)
            .all()
        )
    for sess in active_sessions:
        minutes_used = (now - sess.time_in).total_seconds() / 60
        time_bill = calculate_time_bill(sess.space_type, minutes_used, booking=bookings.get(sess.id), now_utc=now)
        
        food_total = food_totals.get(sess.id, Decimal("0.00"))
        
        pending_balance_sum += time_bill + Decimal(str(food_total))

    unpaid_receivables = sum(
        (r.amount_owed - r.partial_paid for r in Receivable.query.filter(Receivable.paid.is_(False)).all()
         if r.session_id not in session_ids),
        Decimal("0.00"),
    )
    expected_to_collect = pending_balance_sum + unpaid_receivables
    expected_cash_on_hand = cash_on_hand + expected_to_collect

    # 3. Today's Paid Receivables
    payments_today = ReceivablePayment.query.filter(
        ReceivablePayment.received_at >= start_at,
        ReceivablePayment.received_at < end_at,
    ).all()
    total_collected = sum((p.amount for p in payments_today), Decimal("0.00"))

    return api_ok({
        "cash_on_hand": float(cash_on_hand),
        "expected_to_collect": float(expected_to_collect),
        "expected_cash_on_hand": float(expected_cash_on_hand),
        "receivables_paid_today": len({p.payment_group_id or f"single-{p.id}" for p in payments_today}),
        "receivables_collected_today": float(total_collected)
    })

