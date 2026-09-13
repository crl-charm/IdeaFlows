from __future__ import annotations

from flask import Blueprint, render_template
from datetime import timedelta

from app.repositories.session_repository import SessionRepository
from app.utils.auth import login_required
from app.utils.payment import payment_method_label

receipts_bp = Blueprint("receipts", __name__, url_prefix="/receipt")

_repo = SessionRepository()


@receipts_bp.route("/<int:session_id>", methods=["GET"])
@login_required
def view_receipt(session_id: int) -> str:
    sess = _repo.get_session(session_id)
    if not sess:
        return render_template("error.html", message="Session not found"), 404

    time_diff = sess.time_out - sess.time_in if sess.time_out else None
    duration_min = int(time_diff.total_seconds() / 60) if time_diff else 0

    orders = _repo.get_orders_for_session(session_id) or []

    total_food = sum(float(o.total_price) for o in orders if hasattr(o, "total_price")) if orders else 0

    space_rate = sess.space_type.rate_per_minute if sess.space_type else 0
    time_bill = float(duration_min * space_rate) if space_rate else 0

    tx = _repo.get_transaction_for_session(session_id)
    if tx:
        time_bill = float(tx.time_bill)
        total_food = float(tx.food_bill)
    total_bill = float(tx.total_bill) if tx else time_bill + total_food
    payment_method_val = tx.payment_method if tx and tx.payment_method else getattr(sess, "payment_method", "cash")
    amount_tendered_val = tx.amount_tendered if tx and tx.amount_tendered is not None else getattr(sess, "amount_tendered", None)
    amount_tendered = float(amount_tendered_val) if amount_tendered_val is not None else None

    return render_template(
        "receipt.html",
        session_id=session_id,
        customer_name=sess.customer_name,
        space_name=sess.space_type.name if sess.space_type else "Unknown",
        time_in=(sess.time_in + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S"),
        time_out=(sess.time_out + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S") if sess.time_out else "N/A",
        duration_minutes=duration_min,
        time_bill=time_bill,
        food_bill=total_food,
        total_bill=total_bill,
        payment_method=payment_method_label(payment_method_val),
        amount_tendered=amount_tendered,
        receipt_date=(sess.time_in + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S"),
        orders=orders,
    )
