from __future__ import annotations

from datetime import timedelta

from app.utils.payment import normalize_payment_method, payment_method_label


def serialize_session(session):
    return {
        "id": session.id,
        "customer_name": session.customer_name,
        "school": session.school,
        "course": session.course,
        "number_of_people": session.number_of_people,
        "space_type_id": session.space_type_id,
        "space_type": session.space_type.name if session.space_type else None,
        "time_in": session.time_in.isoformat() if session.time_in else None,
        "time_out": session.time_out.isoformat() if session.time_out else None,
        "status": session.status,
        "service_mode": session.service_mode,
        "credit_balance": float(session.credit_balance or 0),
        "credit_payment_method": getattr(session, "credit_payment_method", None),
    }


def serialize_order(order):
    return {
        "id": order.id,
        "customer_session_id": order.customer_session_id,
        "status": order.status,
        "handled_by": order.handled_by,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "food_total_before": float(order.food_total_before) if order.food_total_before is not None else None,
        "food_total_after": float(order.food_total_after) if order.food_total_after is not None else None,
        "items": [
            {
                "id": item.id,
                "menu_item_id": item.menu_item_id,
                "item_name": item.display_name,
                "quantity": item.quantity,
                "price": float(item.price),
                "base_price": float(item.base_price if item.base_price is not None else item.price),
                "unit_deduction": float(item.unit_deduction or 0),
                "no_rice": bool(item.no_rice),
                "no_egg": bool(item.no_egg),
                "status": item.status,
            }
            for item in getattr(order, "items", [])
        ],
    }


def serialize_booking(booking):
    return {
        "id": booking.id,
        "customer_name": booking.customer_name,
        "date": str(booking.date),
        "start_time": booking.start_time.strftime("%H:%M") if booking.start_time else None,
        "end_time": booking.end_time.strftime("%H:%M") if booking.end_time else None,
        "number_of_people": booking.number_of_people,
        "course": booking.course,
        "purpose": booking.purpose,
        "booking_type": booking.booking_type or "boardroom",
        "hourly_rate": float(booking.hourly_rate or 0),
        "booked_by": booking.booked_by,
        "status": booking.status,
        "session_id": booking.session_id,
        "started_at": booking.started_at.isoformat() if booking.started_at else None,
        "expected_end_at": booking.expected_end_at.isoformat() if booking.expected_end_at else None,
        "ended_at": booking.ended_at.isoformat() if booking.ended_at else None,
        "extended_minutes": booking.extended_minutes,
    }


def serialize_void_request(req):
    if not req:
        return None
    return {
        "id": req.id,
        "transaction_id": req.transaction_id,
        "status": req.status,
        "request_reason": req.request_reason,
        "requested_by": (
            req.requested_by.username
            if getattr(req, "requested_by", None)
            else "Staff"
        ),
        "requested_at": (
            (req.requested_at + timedelta(hours=8)).strftime("%B %d, %Y %I:%M %p")
            if req.requested_at
            else None
        ),
        "request_key": req.request_key,
        "approver": (
            req.approver.username
            if getattr(req, "approver", None)
            else None
        ),
        "decided_at": (
            (req.decided_at + timedelta(hours=8)).strftime("%B %d, %Y %I:%M %p")
            if req.decided_at
            else None
        ),
        "decision_reason": req.decision_reason,
        "money_treatment": req.money_treatment,
        "original_amount": float(req.original_amount),
        "original_payment_method": req.original_payment_method,
        "original_business_date": str(req.original_business_date) if req.original_business_date else None,
        "decision_business_date": str(req.decision_business_date) if req.decision_business_date else None,
        "sale_delta": float(req.sale_delta or 0),
        "cash_delta": float(req.cash_delta or 0),
        "credit_amount": float(req.credit_amount or 0),
        "credit_remaining": float(req.credit_remaining or 0),
        "credit_applied": float(req.credit_applied or 0),
        "refund_amount": float(req.refund_amount or 0),
        "replacement_transaction_id": req.replacement_transaction_id,
        "reconciliation_flag": req.reconciliation_flag,
    }


def serialize_transaction(transaction):
    session = transaction.session
    time_in_dt = transaction.billing_start_at or (session.time_in if session else None)
    time_out_dt = transaction.billing_end_at or (session.time_out if session else None)
    service_mode = transaction.service_mode_snapshot or (session.service_mode if session else "timed")
    customer_name = transaction.customer_name_snapshot or (session.customer_name if session else "N/A")
    space_type = transaction.space_name_snapshot or (session.space_type.name if session and session.space_type else "N/A")

    seconds_spent = (
        int((time_out_dt - time_in_dt).total_seconds())
        if service_mode != "food_only" and time_in_dt and time_out_dt
        else None
    )
    payment_method = normalize_payment_method(
        getattr(transaction, "payment_method", None)
        or (getattr(session, "payment_method", None) if session else None)
    )

    amount_tendered_db = getattr(transaction, "amount_tendered", None)
    if amount_tendered_db is None and session:
        amount_tendered_db = getattr(session, "amount_tendered", None)

    amount_tendered = float(amount_tendered_db) if amount_tendered_db is not None else None

    if getattr(transaction, "change_given", None) is not None:
        change_given = float(transaction.change_given)
    elif amount_tendered is not None:
        change_given = round(amount_tendered - float(transaction.total_bill), 2)
    else:
        change_given = None

    void_req = transaction.active_void_request or transaction.latest_void_request

    return {
        "transaction_id": transaction.id,
        "customer_name": customer_name,
        "payment_method": payment_method,
        "collected_by": transaction.collected_by,
        "payment_label": payment_method_label(payment_method),
        "space_type": space_type,
        "service_mode": service_mode,
        "time_in": (
            (time_in_dt + timedelta(hours=8)).strftime("%B %d, %Y %I:%M %p")
            if time_in_dt
            else "N/A"
        ),
        "time_out": (
            (time_out_dt + timedelta(hours=8)).strftime("%B %d, %Y %I:%M %p")
            if time_out_dt
            else "N/A"
        ),
        "time_bill": float(transaction.time_bill),
        "food_bill": float(transaction.food_bill),
        "discount_type": transaction.discount_type,
        "discount_item_id": transaction.discount_item_id,
        "discount_amount": float(transaction.discount_amount or 0),
        "total_bill": float(transaction.total_bill),
        "seconds_spent": seconds_spent,
        "minutes_spent": round(seconds_spent / 60, 2) if seconds_spent is not None else None,
        "created_date": (
            (transaction.created_at + timedelta(hours=8)).strftime("%Y-%m-%d")
            if transaction.created_at
            else None
        ),
        "amount_tendered": amount_tendered,
        "change_given": change_given,
        "is_voided": bool(getattr(transaction, "is_voided", False)),
        "credit_applied": float(getattr(transaction, "credit_applied", 0) or 0),
        "credit_refunded": float(getattr(transaction, "credit_refunded", 0) or 0),
        "void_request": serialize_void_request(void_req),
    }


def serialize_user(user):
    return {
        "id": user.id,
        "name": user.full_name,
        "username": user.username,
        "role": user.role,
        "job_role": user.job_role if user.job_role else "general",
        "created_at": str(user.created_at)[:10] if user.created_at else None,
    }
