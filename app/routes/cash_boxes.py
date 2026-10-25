from datetime import date, datetime

from flask import Blueprint, jsonify, request, session

from app.services.cash_box_service import CashBoxService
from app.utils.auth import staff_or_admin_required
from app.utils.dates import manila_date

bp = Blueprint("cash_boxes", __name__, url_prefix="/api/cash-boxes")


def response(result, success_status=200):
    if isinstance(result, tuple):
        return jsonify(result[0]), result[1]
    return jsonify(result), success_status


@bp.get("")
@staff_or_admin_required
def status():
    today = manila_date(datetime.utcnow())
    start = CashBoxService.opening_date()
    summaries = CashBoxService.summaries(today) if start else {}
    return jsonify({
        "success": True, "opening_date": start.isoformat() if start else None,
        "today": today.isoformat(), "balances": summaries.get(today),
        "recent": CashBoxService.history(today, today),
    })


@bp.get("/history")
@staff_or_admin_required
def history():
    try:
        start = date.fromisoformat(request.args["start_date"]) if request.args.get("start_date") else None
        end = date.fromisoformat(request.args["end_date"]) if request.args.get("end_date") else None
    except ValueError:
        return jsonify({"error": "Enter valid history dates."}), 400
    if start and end and start > end:
        return jsonify({"error": "History From date must be on or before Through date."}), 400
    return jsonify({"success": True, "data": CashBoxService.history(start, end)})


@bp.post("/opening")
@staff_or_admin_required
def opening():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Enter valid opening cash counts."}), 400
    return response(CashBoxService.open_boxes(
        data.get("date"), data, session["user_id"], request.headers.get("Idempotency-Key")
    ), 201)


@bp.post("/entries")
@staff_or_admin_required
def entry():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Enter a valid cash action."}), 400
    return response(CashBoxService.post(
        data.get("kind"), data.get("box"), data.get("amount"), data.get("date"),
        session["user_id"], note=data.get("note"), recipient=data.get("recipient"),
        repay_owner=data.get("repay_owner"), owner_debt_repayment=data.get("owner_debt_repayment"),
        request_key=request.headers.get("Idempotency-Key"),
    ), 201)


@bp.post("/entries/<int:entry_id>/reverse")
@staff_or_admin_required
def reverse(entry_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Enter a valid correction."}), 400
    return response(CashBoxService.reverse(
        entry_id, session["user_id"], data.get("reason"), request.headers.get("Idempotency-Key"),
        data.get("replacement_amount"),
    ), 201)


# Cash records provide durable replay protection, including after a lost response.
opening._idempotency_action = "cash-box-opening"
entry._idempotency_action = "cash-box-entry"
reverse._idempotency_action = "cash-box-reversal"
