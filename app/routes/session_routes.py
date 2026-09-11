from flask import Blueprint, jsonify, request
from datetime import datetime
from app.utils.auth import login_required

from app.core import get_notifier
from app.core.clock import SystemClock
from app.core.idempotency import idempotent_request
from app.dto.serializers import serialize_transaction
from app.repositories.session_repository import SessionRepository
from app.services.session_service import SessionService


# Blueprint groups related routes together
session_bp = Blueprint("session_routes", __name__)

_service = SessionService(
    repo=SessionRepository(),
    clock=SystemClock(),
    notifier=get_notifier(),
)


# -----------------------------
# CHECK-IN CUSTOMER
# -----------------------------
@session_bp.route("/api/checkin", methods=["POST"])
#@login_required
@idempotent_request("customer-checkin")
def checkin():

    data = request.get_json()
    payload, status = _service.checkin(
        customer_name=data.get("customer_name"),
        school=data.get("school"),
        course=data.get("course"),
        space_type_id=data.get("space_type_id"),
        number_of_people=int(data.get("number_of_people", 1) or 1),
    )
    return jsonify(payload), status


# -----------------------------
# GET ACTIVE SESSIONS
# (LIVE RUNNING BILL)
# -----------------------------
@session_bp.route("/api/active-sessions")
@login_required
def get_active_sessions():
    return jsonify(_service.get_active_sessions_view())


# -----------------------------
# CHECKOUT CUSTOMER
# -----------------------------
@session_bp.route("/api/checkout/<int:session_id>", methods=["POST"])
@login_required
@idempotent_request("customer-checkout")
def checkout(session_id):
    data = request.get_json(silent=True) or {}
    payment_method = (
        data.get("payment_method")
        or request.form.get("payment_method")
        or request.args.get("payment_method")
        or "cash"
    )
    amount_tendered = (
        data.get("amount_tendered")
        or request.form.get("amount_tendered")
        or request.args.get("amount_tendered")
    )
    resp = _service.checkout(session_id, payment_method=payment_method, amount_tendered=amount_tendered)
    if isinstance(resp, tuple):
        payload, status = resp
        return jsonify(payload), status
    return jsonify(resp)

@session_bp.route("/api/preview-checkout/<int:session_id>")
def preview_checkout(session_id):
    resp = _service.preview_checkout(session_id)
    if isinstance(resp, tuple):
        payload, status = resp
        return jsonify(payload), status
    return jsonify(resp)


@session_bp.route("/api/checkout-records")
@login_required
def checkout_records():
    page = request.args.get("page", 1, type=int) or 1
    per_page = request.args.get("per_page", 50, type=int) or 50
    per_page = min(per_page, 100)
    transactions = _service.checkout_records(page=page, per_page=per_page)
    tx_items = transactions.items if hasattr(transactions, "items") else transactions

    # Optional date-range filter (YYYY-MM-DD strings from the frontend)
    date_from_str = request.args.get("date_from", "").strip()
    date_to_str   = request.args.get("date_to",   "").strip()
    payment_filter = request.args.get("payment_method", "").strip().lower()

    date_from = None
    date_to   = None
    try:
        if date_from_str:
            date_from = datetime.strptime(date_from_str, "%Y-%m-%d").date()
        if date_to_str:
            date_to = datetime.strptime(date_to_str, "%Y-%m-%d").date()
    except ValueError:
        pass  # Ignore bad dates — return unfiltered

    result = []
    for tx in tx_items:
        if date_from and tx.created_at.date() < date_from:
            continue
        if date_to and tx.created_at.date() > date_to:
            continue
        serialized = serialize_transaction(tx)
        if payment_filter and serialized.get("payment_method") != payment_filter:
            continue
        result.append(serialized)

    return jsonify(result)


@session_bp.route("/api/space-availability")
@login_required
def space_availability():
    return jsonify(_service.space_availability())
