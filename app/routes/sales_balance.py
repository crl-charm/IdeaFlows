from __future__ import annotations

from datetime import date
from typing import Any

from flask import Blueprint, request, render_template, session

from app.dto.api_response import api_error, api_ok

from app.utils.billing import current_time_bill
from app import db
from app.core.idempotency import idempotent_request
from app.repositories.sales_repository import SalesRepository
from app.services.daily_balance_export_service import DailyBalanceExportService
from app.services.sales_service import SalesService
from app.utils.auth import login_required, staff_or_admin_required

sales_bp = Blueprint("sales_admin", __name__, url_prefix="/admin/daily-balance")

_service = SalesService(repo=SalesRepository())
_export = DailyBalanceExportService(db)


@sales_bp.route("", methods=["GET"])
@login_required
def list_reports() -> str:
    return render_template("admin/daily_balance.html")


@sales_bp.route("/api/reports", methods=["GET"])
@login_required
def api_list_reports() -> tuple:
    start = request.args.get("start_date")
    end = request.args.get("end_date")
    try:
        start_date = date.fromisoformat(start) if start else None
        end_date = date.fromisoformat(end) if end else None
    except ValueError:
        return api_error("Invalid date filter", status=400)
    if start_date and end_date and start_date > end_date:
        return api_error("Start date must be on or before end date", status=400)
    reports = _service.list_reports(start_date, end_date)
    return api_ok(reports)


@sales_bp.route("/api/reports", methods=["POST"])
@staff_or_admin_required
@idempotent_request("admin-generate-sales-report")
def api_generate_report() -> tuple:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return api_error("Enter a valid daily report.", status=400)
    try:
        report_date = date.fromisoformat(data.get("report_date"))
    except (TypeError, ValueError):
        return api_error("Choose a valid report date.", status=400)
    notes = data.get("notes")
    if notes is not None and (not isinstance(notes, str) or len(notes) > 2000):
        return api_error("Enter valid notes up to 2000 characters.", status=400)
    user_id = session.get("user_id")
    
    if not user_id:
        return api_error("User session not found", status=400)
    
    result = _service.generate_report(
        report_date=report_date,
        generated_by=user_id,
        notes=notes,
    )
    return api_ok(result.get("data"), status=201)


@sales_bp.route("/api/reports/export-csv", methods=["GET"])
@login_required
def api_export_csv() -> Any:
    try:
        return _export.export_csv(*_filtered_export_data())
    except ValueError as exc:
        return api_error(str(exc), status=400)


def _filtered_export_data():
    start = request.args.get("start_date")
    end = request.args.get("end_date")
    start_date = date.fromisoformat(start) if start else None
    end_date = date.fromisoformat(end) if end else None
    if start_date and end_date and start_date > end_date:
        raise ValueError("Start date must be on or before end date")
    reports = _service.list_reports(start_date, end_date)
    soft = [s for s in _service.list_soft_balances()
            if (not start or s["balance_date"] >= start) and (not end or s["balance_date"] <= end)]
    return reports, soft


@sales_bp.route("/api/reports/export-pdf", methods=["GET"])
@login_required
def api_export_pdf() -> Any:
    try:
        return _export.export_pdf(*_filtered_export_data())
    except ValueError as exc:
        return api_error(str(exc), status=400)
    except Exception as e:
        return api_error(f"Failed to export PDF: {str(e)}", status=500)


@sales_bp.route("/api/reports/export-excel", methods=["GET"])
@login_required
def api_export_excel() -> Any:
    try:
        return _export.export_excel(*_filtered_export_data())
    except ValueError as exc:
        return api_error(str(exc), status=400)
    except Exception as e:
        return api_error(f"Failed to export Excel: {str(e)}", status=500)


@sales_bp.route("/api/soft-balances", methods=["GET"])
@login_required
def api_list_soft_balances() -> tuple:
    entries = _service.list_soft_balances()
    return api_ok(entries)


@sales_bp.route("/api/soft-balances", methods=["POST"])
@staff_or_admin_required
@idempotent_request("admin-create-soft-balance")
def api_create_soft_balance() -> tuple:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return api_error("Enter a valid soft balance.", status=400)
    try:
        balance_date = date.fromisoformat(data.get("balance_date"))
    except (TypeError, ValueError):
        return api_error("Choose a valid balance date.", status=400)
    period_value = data.get("period") or "AM"
    if not isinstance(period_value, str):
        return api_error("Choose AM or PM.", status=400)
    period = period_value.upper()
    if period not in {"AM", "PM"}:
        return api_error("Choose AM or PM.", status=400)
    notes = data.get("notes")
    if notes is not None and (not isinstance(notes, str) or len(notes) > 2000):
        return api_error("Enter valid notes up to 2000 characters.", status=400)
    user_id = session.get("user_id")
    
    if not user_id:
        return api_error("User session not found", status=400)
    
    result = _service.create_soft_balance(
        balance_date=balance_date,
        period=period,
        generated_by=user_id,
        notes=notes,
    )
    return api_ok(result.get("data"), status=201)


@sales_bp.route("/api/today-stats", methods=["GET"])
@login_required
def api_today_stats() -> tuple:
    from app.models import CustomerSession, Order, OrderItem
    from datetime import datetime
    from sqlalchemy import func
    from sqlalchemy.orm import selectinload
    from decimal import Decimal
    from app.utils.dates import manila_date
    from app.services.cash_box_service import CashBoxService

    now = datetime.utcnow()
    today = manila_date(now)
    live = _service.repo.daily_ledger(today, today).get(today) or _service.repo.daily_ledger_empty(today)
    cash_on_hand = Decimal(str(live["cash_on_hand"]))
    cash_boxes = CashBoxService.summaries(today).get(today)
    cash_received = (live["checkout_methods"]["cash"] - live["credit_applied_methods"]["cash"]
                     + live["credit_received_methods"]["cash"] + live["collection_methods"]["cash"]
                     + live["adjustment_income_methods"]["cash"])
    cash_spent = (live["expense_methods"]["cash"] + live["payable_methods"]["cash"]
                  + live["adjustment_expense_methods"]["cash"] + live["refund_methods"]["cash"])

    # Still to collect here is limited to customers currently checked in.
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
        time_bill = current_time_bill(sess, now, booking=bookings.get(sess.id))
        
        food_total = food_totals.get(sess.id, Decimal("0.00"))
        
        pending_balance_sum += time_bill + Decimal(str(food_total))

    expected_to_collect = pending_balance_sum
    expected_cash_on_hand = cash_on_hand + expected_to_collect

    return api_ok({
        "cash_on_hand": float(cash_on_hand),
        "cash_flow_parts": {
            "received": cash_received,
            "owner_added": live["owner_topup_methods"]["cash"],
            "spent_refunded": cash_spent,
            "taken_out": live["cash_withdrawal_methods"]["cash"],
        },
        "cash_boxes": cash_boxes,
        "expected_to_collect": float(expected_to_collect),
        "expected_cash_on_hand": float(expected_cash_on_hand),
        "receivables_paid_today": live["collection_count"],
        "receivables_collected_today": live["total_collections"],
    })

