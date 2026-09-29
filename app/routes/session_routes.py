from flask import Blueprint, jsonify, request, session
from datetime import datetime
from app.utils.auth import login_required, admin_required

from app.core import get_notifier
from app.core.clock import SystemClock
from app.core.idempotency import idempotent_request
from app.dto.serializers import serialize_transaction, serialize_void_request
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
@login_required
@idempotent_request("customer-checkin")
def checkin():

    data = request.get_json()
    payload, status = _service.checkin(
        customer_name=data.get("customer_name"),
        school=data.get("school"),
        course=data.get("course"),
        space_type_id=data.get("space_type_id"),
        number_of_people=int(data.get("number_of_people", 1) or 1),
        void_request_id=data.get("void_request_id"),
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
# FOOD-ONLY ORDERS (CARDS & CREATION)
# -----------------------------
@session_bp.route("/api/food-orders", methods=["GET"])
@login_required
def active_food_orders():
    return jsonify(_service.get_active_food_orders_view())


@session_bp.route("/api/checkout-corrections", methods=["GET"])
@login_required
def available_checkout_corrections():
    return jsonify(_service.available_checkout_corrections())


@session_bp.route("/api/food-orders", methods=["POST"])
@login_required
@idempotent_request("start-food-order")
def start_food_order():
    data = request.get_json(silent=True) or {}
    resp = _service.create_food_order(
        customer_name=data.get("customer_name", ""),
        location=data.get("location", ""),
        void_request_id=data.get("void_request_id"),
    )
    if isinstance(resp, tuple):
        payload, status = resp
        return jsonify(payload), status
    return jsonify(resp)


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
    discount_type = data.get("discount_type") or request.form.get("discount_type")
    discount_item_id = data.get("discount_item_id") or request.form.get("discount_item_id")
    actor_name = session.get("username") or session.get("user") or "Staff"

    resp = _service.checkout(
        session_id,
        payment_method=payment_method,
        amount_tendered=amount_tendered,
        discount_type=discount_type,
        discount_item_id=discount_item_id,
        actor_name=actor_name,
    )
    if isinstance(resp, tuple):
        payload, status = resp
        return jsonify(payload), status
    return jsonify(resp)


@session_bp.route("/api/preview-checkout/<int:session_id>")
@login_required
def preview_checkout(session_id):
    resp = _service.preview_checkout(session_id, request.args.get("discount_type"), request.args.get("discount_item_id"))
    if isinstance(resp, tuple):
        payload, status = resp
        return jsonify(payload), status
    return jsonify(resp)


@session_bp.route("/api/checkout-records")
@login_required
def checkout_records():
    page = max(request.args.get("page", 1, type=int) or 1, 1)
    per_page = min(max(request.args.get("per_page", 50, type=int) or 50, 1), 100)

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

    transactions = _service.checkout_records(
        page=page, per_page=per_page, date_from=date_from, date_to=date_to,
        payment_method=payment_filter,
    )
    return jsonify([serialize_transaction(tx) for tx in transactions.items])


@session_bp.route("/api/checkout-records/<int:tx_id>/void-request", methods=["POST"])
@login_required
@idempotent_request("request-checkout-void")
def request_checkout_void(tx_id: int):
    data = request.get_json() or {}
    reason = data.get("reason", "")
    request_key = request.headers.get("Idempotency-Key") or data.get("request_key")
    actor_id = session.get("user_id")
    if not actor_id:
        return jsonify({"error": "User session not found."}), 401

    payload, status = _service.request_checkout_void(
        transaction_id=tx_id,
        reason=reason,
        actor_id=actor_id,
        request_key=request_key,
    )
    return jsonify(payload), status


@session_bp.route("/api/checkout-records/void-requests", methods=["GET"])
@login_required
def list_checkout_void_requests():
    status = request.args.get("status")
    requests = _service.list_void_requests(status=status)
    return jsonify([serialize_void_request(r) for r in requests])


@session_bp.route("/api/checkout-records/void-requests/<int:req_id>/reject", methods=["POST"])
@admin_required
@idempotent_request("reject-checkout-void")
def reject_checkout_void(req_id: int):
    data = request.get_json() or {}
    reason = data.get("reason", "")
    admin_id = session.get("user_id")
    if not admin_id:
        return jsonify({"error": "Admin session not found."}), 401

    payload, status = _service.reject_checkout_void(
        request_id=req_id,
        reason=reason,
        admin_id=admin_id,
    )
    return jsonify(payload), status


@session_bp.route("/api/checkout-records/void-requests/<int:req_id>/approve", methods=["POST"])
@admin_required
@idempotent_request("approve-checkout-void")
def approve_checkout_void(req_id: int):
    data = request.get_json() or {}
    money_treatment = data.get("money_treatment")
    decision_reason = data.get("decision_reason", "")
    admin_id = session.get("user_id")
    if not admin_id:
        return jsonify({"error": "Admin session not found."}), 401

    payload, status = _service.approve_checkout_void(
        request_id=req_id,
        money_treatment=money_treatment,
        decision_reason=decision_reason,
        admin_id=admin_id,
    )
    return jsonify(payload), status


@session_bp.route("/api/space-availability")
@login_required
def space_availability():
    return jsonify(_service.space_availability())
