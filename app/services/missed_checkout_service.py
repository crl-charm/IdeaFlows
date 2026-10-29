"""Admin recovery for a paid customer whose departure was not recorded."""
from datetime import timedelta
from decimal import Decimal
from hashlib import sha256
import json

from flask import current_app
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import func
from sqlalchemy.orm import selectinload

from app import db
from app.models import (CustomerSession, FinanceTransaction, Order, Receivable,
                        ReceivablePayment, SessionTimeEvent, Transaction, User)
from app.utils.billing import (billable_microseconds, calculate_time_bill,
                               current_time_bill, historical_billable_microseconds)
from app.utils.dates import MANILA_OFFSET, entered_manila_time, manila_date, manila_day_bounds
from app.utils.payment import VALID_PAYMENT_METHODS, parse_money_amount

class MissedCheckoutService:
    def __init__(self, sessions):
        self.sessions = sessions

    @staticmethod
    def signer():
        return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="missed-checkout-preview")

    @staticmethod
    def collectors():
        # Admin login uses admins; its canonical users row is deliberately inactive.
        return [{"id": row.id, "name": row.full_name or row.username, "active": row.role == "admin" or row.is_active}
                for row in User.query.filter(User.role.in_(("staff", "admin")))
                .order_by(User.full_name, User.id).all()]

    def _prepare(self, session_id, data, *, lock=False):
        repo = self.sessions.repo
        sess = repo.get_session_for_update(session_id) if lock else repo.get_session(session_id)
        if not sess:
            raise LookupError("Customer session not found.")
        if sess.status != "active":
            raise RuntimeError("This visit is no longer active. Refresh the customer list.")
        if (sess.service_mode != "timed" or sess.space_type.name not in {"Regular Lounge", "Premium Lounge"}
                or sess.voided_transaction_id or sess.retained_time_bill is not None
                or Decimal(str(sess.credit_balance or 0))):
            raise ValueError("Missed Checkout supports ordinary Regular and Premium visits only.")
        if (Transaction.query.filter_by(session_id=sess.id).first()
                or Receivable.query.filter_by(session_id=sess.id).first() or sess.boardroom_booking):
            raise RuntimeError("This visit already has a checkout, debt, or booking. Review its existing financial records.")
        now = self.sessions.clock.now()
        departure = entered_manila_time(data.get("departure_at"))
        paid_at = entered_manila_time(data.get("paid_at"))
        if not sess.time_in < departure <= now:
            raise ValueError("Departure must be after Time In and no later than now in Manila time.")
        if not sess.time_in <= paid_at <= now:
            raise ValueError("Payment must be between Time In and now in Manila time.")
        amount = parse_money_amount(data.get("amount_received"))
        method = data.get("payment_method")
        if not isinstance(method, str) or method not in VALID_PAYMENT_METHODS:
            raise ValueError("Choose a valid payment method.")
        collector_id = data.get("collector_id")
        if type(collector_id) is not int:
            raise ValueError("Choose the staff or admin who actually received the payment.")
        collector = User.query.filter(User.id == collector_id, User.role.in_(("staff", "admin"))).first()
        if not collector:
            raise ValueError("The selected collector was not found.")
        reason, note = data.get("reason"), data.get("note", "")
        if reason not in ("outage", "forgot_checkout", "other") or not isinstance(note, str) or len(note) > 500:
            raise ValueError("Choose a reason and enter a note of up to 500 characters.")
        note = note.strip()
        if reason == "other" and not note:
            raise ValueError("Add a short note for the Other reason.")
        events = SessionTimeEvent.query.filter_by(session_id=sess.id).order_by(
            SessionTimeEvent.occurred_at, SessionTimeEvent.id).all()
        if any(event.occurred_at > now + timedelta(seconds=1) for event in events):
            raise ValueError("Time history contains a future event; review it first.")
        billable_us = historical_billable_microseconds(sess, departure, events)
        time_bill = calculate_time_bill(sess.space_type, Decimal(billable_us) / 60_000_000)
        food_bill, _ = self.sessions._food_bill(sess)
        if data.get("discount_type") is not None and not isinstance(data.get("discount_type"), str):
            raise ValueError("Choose a valid supported discount.")
        discount, discount_type, discount_item_id = self.sessions._discount(
            sess.id, data.get("discount_type"), data.get("discount_item_id"), time_bill)
        total = (time_bill + food_bill - discount).quantize(Decimal("0.01"))
        if amount <= 0 or total <= 0:
            raise ValueError("The verified bill and payment must be positive.")
        tendered = None
        if method == "cash" and data.get("amount_tendered") not in (None, ""):
            tendered = parse_money_amount(data["amount_tendered"])
            if tendered < total:
                raise ValueError("Original cash tender cannot be less than the corrected bill.")
        orders = Order.query.options(selectinload(Order.items)).filter_by(customer_session_id=sess.id).order_by(Order.id).all()
        # The picker records minutes, so reject orders clearly after that minute.
        if any(order.created_at and order.created_at >= departure + timedelta(minutes=1) for order in orders):
            raise ValueError("Food was ordered after the entered departure. Reconcile the departure and orders first.")
        before_time = current_time_bill(sess, now)
        before_discount, _, _ = self.sessions._discount(sess.id, discount_type, discount_item_id, before_time)
        before = {"billable_microseconds": billable_microseconds(sess, now), "time_bill": str(before_time),
                  "food_bill": str(food_bill), "discount": str(before_discount),
                  "total": str(before_time + food_bill - before_discount), "status": sess.status,
                  "paused_at": sess.paused_at.isoformat() if sess.paused_at else None,
                  "paused_microseconds": int(sess.paused_microseconds or 0)}
        quote = {"departure": departure, "paid_at": paid_at, "amount": amount,
                 "method": method, "collector_id": collector.id, "collector_name": collector.full_name,
                 "reason": reason, "note": note, "billable_us": billable_us, "time_bill": time_bill,
                 "food_bill": food_bill, "discount": discount, "discount_type": discount_type,
                 "discount_item_id": discount_item_id, "total": total, "before": before,
                 "amount_tendered": tendered}
        quote["possible_existing_payments"] = self._possible_payments(sess, quote)
        # Do not sign the increasing current estimate: a few seconds spent reviewing
        # must not invalidate an otherwise unchanged historical quote.
        fingerprint = {
            "session": [sess.id, sess.customer_name, sess.time_in.isoformat(), sess.status,
                        sess.paused_at.isoformat() if sess.paused_at else None, sess.paused_microseconds],
            "quote": {key: str(value) for key, value in quote.items() if key != "before"},
            "events": [(e.id, e.action, e.occurred_at.isoformat(), e.billable_microseconds_before,
                        e.billable_microseconds_after) for e in events],
            "orders": [(o.id, o.created_at.isoformat() if o.created_at else None, o.status,
                        [(i.id, i.quantity, str(i.price), i.name_snapshot, i.no_rice, i.no_egg) for i in sorted(o.items, key=lambda i:i.id)])
                       for o in orders],
        }
        quote["revision"] = sha256(json.dumps(fingerprint, sort_keys=True).encode()).hexdigest()
        return sess, quote

    @staticmethod
    def _error(error):
        status = 404 if isinstance(error, LookupError) else 409 if isinstance(error, RuntimeError) else 400
        return {"error": str(error)}, status

    def preview(self, session_id, data):
        try:
            sess, quote = self._prepare(session_id, data)
        except (ValueError, LookupError, RuntimeError) as error:
            return self._error(error)
        token = self.signer().dumps({"session": sess.id, "revision": quote["revision"]})
        return {"customer_name": sess.customer_name, "space_type": sess.space_type.name,
                "departure_at": (quote["departure"] + MANILA_OFFSET).isoformat(timespec="minutes"),
                "paid_at": (quote["paid_at"] + MANILA_OFFSET).isoformat(timespec="minutes"),
                "billable_seconds": quote["billable_us"] // 1_000_000,
                "before": quote["before"], "time_bill": float(quote["time_bill"]),
                "food_bill": float(quote["food_bill"]), "discount": float(quote["discount"]),
                "total": float(quote["total"]), "amount_received": float(quote["amount"]),
                "difference": float(quote["amount"] - quote["total"]),
                "matches": quote["amount"] == quote["total"], "collector": quote["collector_name"],
                "possible_existing_payments": quote["possible_existing_payments"], "preview_token": token}, 200

    def complete(self, session_id, data, actor_id, actor_name, actor_role, request_key):
        if actor_role != "admin" or type(actor_id) is not int or actor_id < 1:
            return {"error": "Admin account required."}, 403
        if data.get("payment_confirmed") is not True:
            return {"error": "Confirm that payment was received and has not already been recorded."}, 400
        try:
            if not isinstance(data.get("preview_token"), str):
                raise BadSignature("Invalid token")
            signed = self.signer().loads(data["preview_token"], max_age=600)
        except (BadSignature, TypeError):
            return {"error": "Preview expired or invalid. Review a fresh preview before saving."}, 409
        # Authentication may have opened a MySQL repeatable-read snapshot. Start
        # a fresh transaction before the session lock and its billing reads.
        db.session.rollback()
        try:
            sess, quote = self._prepare(session_id, data, lock=True)
            if signed != {"session": sess.id, "revision": quote["revision"]}:
                raise RuntimeError("Visit or form details changed. Review a fresh preview before saving.")
            if quote["amount"] != quote["total"]:
                raise ValueError("The amount received does not match the bill. Reconcile the time, orders, discount, and payment first.")
            quote["request_key"] = sha256(f"{actor_id}:{session_id}:{request_key or data.get('preview_token')}".encode()).hexdigest()
        except (ValueError, LookupError, RuntimeError) as error:
            db.session.rollback()
            return self._error(error)
        try:
            result = self.sessions.checkout(sess.id, payment_method=quote["method"],
                amount_tendered=quote["amount_tendered"], discount_type=quote["discount_type"],
                discount_item_id=quote["discount_item_id"], actor_id=actor_id,
                actor_name=actor_name, actor_role=actor_role, _missed=quote)
            if isinstance(result, tuple):
                db.session.rollback()
                return result
            return {**result, "message": "Payment already received recorded; missed checkout completed.",
                    "receipt_url": f"/receipt/{session_id}"}, 200
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Missed checkout could not be saved")
            return {"error": "Could not save the missed checkout. Refresh and review before retrying."}, 500

    @staticmethod
    def _possible_payments(sess, quote):
        start, end = manila_day_bounds(manila_date(quote["paid_at"]))
        name = sess.customer_name.strip().lower()
        candidates = []
        matches = Transaction.query.join(CustomerSession).filter(
            Transaction.payment_range(start, end), Transaction.total_bill == quote["amount"],
            func.lower(func.coalesce(Transaction.customer_name_snapshot, CustomerSession.customer_name)) == name,
        ).limit(5).all()
        for row in matches:
            candidates.append(f"Checkout #{row.id}: same customer, amount and payment day. Review before confirming.")
        payments = ReceivablePayment.query.join(Receivable).filter(
            ReceivablePayment.received_at >= start, ReceivablePayment.received_at < end,
            ReceivablePayment.amount == quote["amount"], func.lower(Receivable.customer_name) == name,
        ).limit(5).all()
        for row in payments:
            candidates.append(f"Debt collection #{row.id}: same customer, amount and payment day. Review before confirming.")
        income = FinanceTransaction.query.filter(
            FinanceTransaction.created_at >= start, FinanceTransaction.created_at < end,
            FinanceTransaction._type == "income", FinanceTransaction._amount == quote["amount"],
        ).limit(5).all()
        for row in income:
            candidates.append(f"Manual income #{row.id}: same amount and day. It may be unrelated; review its description.")
        return candidates
