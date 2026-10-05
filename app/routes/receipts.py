from __future__ import annotations

from flask import Blueprint, render_template
from datetime import timedelta

from app.repositories.session_repository import SessionRepository
from app.models import CheckoutVoidRequest
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

    tx = _repo.get_latest_transaction_for_session(session_id, include_voided=True)
    food_only = (tx.service_mode_snapshot if tx else sess.service_mode) == "food_only"
    time_in_dt = (tx.billing_start_at if tx else None) or sess.time_in
    time_out_dt = (tx.billing_end_at if tx else None) or sess.time_out
    time_diff = time_out_dt - time_in_dt if time_out_dt and not food_only else None
    duration_min = (tx.billable_microseconds // 60_000_000
                    if tx and tx.billable_microseconds is not None
                    else int(time_diff.total_seconds() / 60) if time_diff else 0)

    orders = _repo.get_orders_for_session(session_id) or []

    total_food = sum(float(o.total_price) for o in orders if hasattr(o, "total_price")) if orders else 0

    space_rate = sess.space_type.rate_per_minute if sess.space_type else 0
    time_bill = float(duration_min * space_rate) if space_rate and not food_only else 0

    if tx:
        time_bill = float(tx.time_bill)
        total_food = float(tx.food_bill)
        correction = CheckoutVoidRequest.query.filter_by(replacement_transaction_id=tx.id).first()
        if correction:
            orders = _repo.get_orders_for_session(correction.transaction.session_id) + orders
    total_bill = float(tx.total_bill) if tx else time_bill + total_food
    payment_method_val = tx.payment_method if tx and tx.payment_method else getattr(sess, "payment_method", "cash")
    amount_tendered_val = tx.amount_tendered if tx and tx.amount_tendered is not None else getattr(sess, "amount_tendered", None)
    amount_tendered = float(amount_tendered_val) if amount_tendered_val is not None else None

    return render_template(
        "receipt.html",
        session_id=session_id,
        customer_name=sess.customer_name,
        space_name=sess.space_type.name if sess.space_type else "Unknown",
        food_only=food_only,
        time_in=(time_in_dt + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S"),
        time_out=(time_out_dt + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S") if time_out_dt else "N/A",
        duration_minutes=duration_min,
        time_bill=time_bill,
        food_bill=total_food,
        discount_type=tx.discount_type if tx else None,
        discount_item_id=tx.discount_item_id if tx else None,
        discount_amount=float(tx.discount_amount or 0) if tx else 0,
        total_bill=total_bill,
        payment_method=payment_method_label(payment_method_val),
        amount_tendered=amount_tendered,
        credit_applied=float(tx.credit_applied or 0) if tx else 0,
        change_given=(float(tx.change_given) if tx and tx.change_given is not None else
                      max(0, amount_tendered - total_bill + float(tx.credit_applied or 0))
                      if amount_tendered is not None and tx else 0),
        is_voided=bool(tx.is_voided) if tx else False,
        receipt_date=((tx.created_at if food_only and tx else sess.time_in) + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S"),
        orders=orders,
    )
