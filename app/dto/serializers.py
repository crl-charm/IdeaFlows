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
    }


def serialize_order(order):
    return {
        "id": order.id,
        "customer_session_id": order.customer_session_id,
        "status": order.status,
        "handled_by": order.handled_by,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "items": [
            {
                "id": item.id,
                "menu_item_id": item.menu_item_id,
                "item_name": item.menu_item.name if item.menu_item else None,
                "quantity": item.quantity,
                "price": float(item.price),
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
        "status": booking.status,
        "session_id": booking.session_id,
        "started_at": booking.started_at.isoformat() if booking.started_at else None,
        "expected_end_at": booking.expected_end_at.isoformat() if booking.expected_end_at else None,
        "ended_at": booking.ended_at.isoformat() if booking.ended_at else None,
        "extended_minutes": booking.extended_minutes,
    }


def serialize_transaction(transaction):
    session = transaction.session
    seconds_spent = (
        int((session.time_out - session.time_in).total_seconds())
        if session and session.time_in and session.time_out
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
    change_given = round(amount_tendered - float(transaction.total_bill), 2) if amount_tendered is not None else None

    return {
        "transaction_id": transaction.id,
        "customer_name": session.customer_name if session else "N/A",
        "payment_method": payment_method,
        "payment_label": payment_method_label(payment_method),
        "space_type": session.space_type.name if session and session.space_type else "N/A",
        "time_in": (session.time_in + timedelta(hours=8)).strftime("%B %d, %Y %I:%M %p")
        if session and session.time_in
        else "N/A",
        "time_out": (session.time_out + timedelta(hours=8)).strftime("%B %d, %Y %I:%M %p")
        if session and session.time_out
        else "N/A",
        "time_bill": float(transaction.time_bill),
        "food_bill": float(transaction.food_bill),
        "total_bill": float(transaction.total_bill),
        "seconds_spent": seconds_spent,
        "minutes_spent": round(seconds_spent / 60, 2) if seconds_spent is not None else None,
        "created_date": (transaction.created_at + timedelta(hours=8)).strftime("%Y-%m-%d") if transaction.created_at else None,
        "amount_tendered": amount_tendered,
        "change_given": change_given,
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
