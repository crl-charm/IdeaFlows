from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional

from app import db
from app.utils.billing import billable_microseconds, current_time_bill
from app.core.interfaces import Clock, Notifier
from app.models import (
    BoardroomBooking, BookingChange, CheckoutVoidRequest, CustomerSession,
    Order, Receivable, SessionTimeEvent, Transaction,
)
from app.repositories.session_repository import SessionRepository
from app.repositories.sales_repository import SalesRepository
from app.utils.dates import manila_date
from app.dto.serializers import serialize_void_request
from app.utils.payment import normalize_payment_method, payment_method_label, parse_money_amount

FOOD_LOCATIONS = {"Regular Lounge", "Premium Lounge", "Boardroom", "Take Out"}


@dataclass(frozen=True)
class SessionService:
    repo: SessionRepository
    clock: Clock
    notifier: Notifier
    sales_repo: Optional[SalesRepository] = None

    def _discount(self, session_id: int, discount_type: str | None, discount_item_id: Any,
                  time_bill: Decimal) -> tuple[Decimal, str | None, int | None]:
        discount_type = (discount_type or "").strip().lower()
        if not discount_type and discount_item_id in (None, ""):
            return Decimal("0.00"), None, None
        if discount_type not in {"pwd", "senior"}:
            raise ValueError("Choose PWD or Senior Citizen discount.")
        if discount_item_id in (None, ""):
            if self.repo.get_orders_for_session(session_id):
                raise ValueError("Choose one food item for the discount.")
            amount = (time_bill * Decimal("0.20")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            return amount, discount_type, None
        if isinstance(discount_item_id, bool) or not str(discount_item_id).isdigit():
            raise ValueError("Choose one food item for the discount.")
        item_id = int(discount_item_id)
        item = self.repo.get_order_item_for_session(session_id, item_id)
        if not item or not item.quantity or item.quantity < 1:
            raise ValueError("The selected food item is no longer in this customer's order.")
        amount = (Decimal(str(item.price)) * Decimal("0.20")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return amount, discount_type, item_id

    def checkin(
        self,
        *,
        customer_name: str,
        school: Optional[str],
        course: Optional[str],
        space_type_id: Optional[int],
        number_of_people: Any,
        void_request_id: Any = None,
    ) -> dict[str, Any]:
        name = customer_name.strip() if isinstance(customer_name, str) else ""
        if not name or len(name) > 100:
            return {"error": "Enter a customer name of up to 100 characters."}, 400
        if (isinstance(space_type_id, bool) or not isinstance(space_type_id, (int, str))
                or not str(space_type_id).isdigit() or len(str(space_type_id)) > 10):
            return {"error": "Please select a valid space."}, 400
        space = self.repo.get_space_type(int(space_type_id), lock=True)
        if not space:
            return {"error": "Please select a valid space."}, 400
        if space.name not in {"Regular Lounge", "Premium Lounge", "Boardroom"}:
            return {"error": "Choose a timed lounge or start a Boardroom booking."}, 400
        if space.name in {"Regular Lounge", "Premium Lounge"}:
            if type(number_of_people) is not int or number_of_people != 1:
                return {"error": "Check in one person at a time for Regular or Premium."}, 400
        else:
            if (isinstance(number_of_people, bool) or not isinstance(number_of_people, (int, str))
                    or not str(number_of_people).isdigit() or len(str(number_of_people)) > 9
                    or int(number_of_people) < 1):
                return {"error": "Number of people must be at least 1."}, 400
            number_of_people = int(number_of_people)

        now = self.clock.now()
        sess = CustomerSession(
            customer_name=name,
            school=school,
            course=course,
            number_of_people=number_of_people,
            space_type_id=space.id,
            time_in=now,
            status="active",
            service_mode="timed",
        )
        blocking = self.repo.blocking_booking_at(now + timedelta(hours=8), whole_hub_only=space.name != "Boardroom")
        if blocking:
            return {"error": "This space is reserved for a booking right now."}, 409
        occupied = self.repo.sum_active_occupancy(space.id, lock=True)
        if space.name == "Boardroom" and occupied:
            return {"error": "Boardroom is currently occupied.", "full": True}, 409
        if space.capacity:
            if occupied + number_of_people > space.capacity:
                seats_left = max(int(space.capacity) - int(occupied), 0)
                return (
                    {
                        "error": (
                            f"{space.name} has only {seats_left} seat(s) left. "
                            f"Requested seats: {number_of_people}."
                        ),
                        "full": True,
                    },
                    409,
                )

        correction_error = self._attach_void_correction(sess, void_request_id)
        if correction_error:
            return correction_error
        self.repo.add_session(sess)
        return {"message": "Customer checked in successfully", "session_id": sess.id}, 200

    def _attach_void_correction(self, sess: CustomerSession, request_id: Any) -> tuple[dict[str, Any], int] | None:
        if request_id in (None, ""):
            return None
        if isinstance(request_id, bool) or not str(request_id).isdigit():
            return {"error": "Choose a valid voided checkout."}, 400
        req = CheckoutVoidRequest.query.filter_by(
            id=int(request_id), status="approved",
        ).with_for_update().first()
        if not req or req.replacement_transaction_id:
            return {"error": "This voided checkout is no longer available for correction."}, 409
        if CustomerSession.query.filter_by(voided_transaction_id=req.transaction_id).first():
            return {"error": "This voided checkout is already assigned to a check-in."}, 409
        original_name = req.transaction.customer_name_snapshot or req.transaction.session.customer_name
        if sess.customer_name.strip().casefold() != original_name.strip().casefold():
            return {"error": "Customer name must match the selected voided checkout."}, 400
        if req.money_treatment == "retained_credit":
            if req.credit_remaining <= 0:
                return {"error": "This customer credit is no longer available."}, 409
            sess.credit_balance = req.credit_remaining
            sess.credit_payment_method = req.original_payment_method
        sess.voided_transaction_id = req.transaction_id
        return None

    def available_checkout_corrections(self) -> list[dict[str, Any]]:
        requests = CheckoutVoidRequest.query.filter(
            CheckoutVoidRequest.status == "approved",
            CheckoutVoidRequest.replacement_transaction_id.is_(None),
        ).order_by(CheckoutVoidRequest.decided_at.desc()).all()
        return [
            {
                "request_id": req.id,
                "customer_name": req.transaction.customer_name_snapshot or req.transaction.session.customer_name,
                "amount": float(req.credit_remaining),
                "food_bill": float(req.transaction.food_bill),
                "money_treatment": req.money_treatment,
                "payment_method": req.original_payment_method,
                "original_space": req.transaction.space_name_snapshot or req.transaction.session.space_type.name,
            }
            for req in requests
            if not CustomerSession.query.filter_by(voided_transaction_id=req.transaction_id).first()
        ]

    def create_food_order(self, *, customer_name: str, location: str, void_request_id: Any = None) -> tuple[dict[str, Any], int]:
        name = customer_name.strip() if isinstance(customer_name, str) else ""
        if not name or len(name) > 100:
            return {"error": "Enter a customer name of up to 100 characters."}, 400
        if not isinstance(location, str) or location not in FOOD_LOCATIONS:
            return {"error": "Choose Regular, Premium, Boardroom, or Take Out."}, 400
        space = self.repo.get_space_type_by_name(location)
        if not space:
            return {"error": "Food order locations are not configured."}, 503
        sess = CustomerSession(
            customer_name=name, space_type_id=space.id, service_mode="food_only",
            number_of_people=1, time_in=self.clock.now(), status="active",
        )
        correction_error = self._attach_void_correction(sess, void_request_id)
        if correction_error:
            return correction_error
        self.repo.add_session(sess)
        return {"message": "Food order started", "session_id": sess.id}, 201

    def get_active_food_orders_view(self) -> list[dict[str, Any]]:
        sessions = self.repo.get_active_food_orders()
        totals = self.repo.food_totals_for_sessions([sess.id for sess in sessions])
        return [
            {
                "session_id": sess.id,
                "customer_name": sess.customer_name,
                "space_type": sess.space_type.name,
                "food_total": float(totals.get(sess.id, 0)),
                "service_mode": "food_only",
            }
            for sess in sessions
        ]

    def get_active_sessions_view(self) -> list[dict[str, Any]]:
        sessions = self.repo.get_active_sessions()
        session_ids = [s.id for s in sessions]
        boardroom_by_session = self.repo.get_active_boardroom_bookings_by_session_ids(session_ids)

        result: list[dict[str, Any]] = []
        now = self.clock.now()

        for sess in sessions:
            linked = boardroom_by_session.get(sess.id)
            current_bill = current_time_bill(sess, now, booking=linked)
            purpose = linked.purpose if linked else None

            result.append(
                {
                    "session_id": sess.id,
                    "customer_name": sess.customer_name,
                    "school": sess.school,
                    "course": sess.course,
                    "number_of_people": sess.number_of_people,
                    "purpose": purpose,
                    "space_type": sess.space_type.name,
                    "time_in": (sess.time_in + timedelta(hours=8)).strftime("%B %d, %Y %I:%M %p"),
                    "seconds_used": billable_microseconds(sess, now) // 1_000_000,
                    "paused": sess.paused_at is not None,
                    "has_time_pause": bool(sess.paused_at or sess.paused_microseconds),
                    "current_bill": float(current_bill),
                }
            )

        return result

    @staticmethod
    def _record_time_event(sess: CustomerSession, action: str, when,
                           actor_id: int, actor_name: str, actor_role: str,
                           before_microseconds: int, before_bill: Decimal) -> None:
        db.session.add(SessionTimeEvent(
            session_id=sess.id, action=action, occurred_at=when,
            business_date=manila_date(when), actor_id=actor_id,
            actor_name=actor_name[:100], actor_role=actor_role[:20],
            billable_microseconds_before=before_microseconds,
            billable_microseconds_after=billable_microseconds(sess, when),
            time_bill_before=before_bill,
            time_bill_after=current_time_bill(sess, when),
        ))

    def set_time_paused(self, session_id: int, pause: bool, actor_id: int,
                        actor_name: str, actor_role: str) -> tuple[dict[str, Any], int]:
        sess = self.repo.get_session_for_update(session_id)
        if not sess:
            return {"error": "Customer session not found."}, 404
        if (sess.status != "active" or sess.service_mode != "timed"
                or sess.space_type.name not in {"Regular Lounge", "Premium Lounge"}):
            return {"error": "Only active Regular or Premium time bills can be paused."}, 409
        if bool(sess.paused_at) == pause:
            return {"error": "This time bill is already paused." if pause else "This time bill is already running."}, 409

        now = self.clock.now()
        before_microseconds = billable_microseconds(sess, now)
        before_bill = current_time_bill(sess, now)
        if pause:
            sess.paused_at = now
        else:
            sess.paused_microseconds += max(0, (now - sess.paused_at) // timedelta(microseconds=1))
            sess.paused_at = None
        self._record_time_event(sess, "paused" if pause else "resumed", now,
                                actor_id, actor_name, actor_role, before_microseconds, before_bill)
        self.repo.commit()
        return {
            "message": f"Time bill {'paused' if pause else 'resumed'} for {sess.customer_name}.",
            "paused": pause,
            "billable_seconds": billable_microseconds(sess, now) // 1_000_000,
            "time_bill": float(current_time_bill(sess, now)),
        }, 200

    def time_history(self, session_id: int) -> tuple[dict[str, Any], int]:
        sess = self.repo.get_session(session_id)
        if not sess:
            return {"error": "Customer session not found."}, 404
        events = (SessionTimeEvent.query.filter_by(session_id=session_id)
                  .order_by(SessionTimeEvent.occurred_at, SessionTimeEvent.id).all())
        return {
            "customer_name": sess.customer_name,
            "space_type": sess.space_type.name,
            "events": [{
                "action": event.action,
                "at": (event.occurred_at + timedelta(hours=8)).strftime("%B %d, %Y %I:%M:%S %p"),
                "actor": event.actor_name,
                "role": event.actor_role,
                "billable_seconds_before": event.billable_microseconds_before // 1_000_000,
                "billable_seconds_after": event.billable_microseconds_after // 1_000_000,
                "time_bill_before": float(event.time_bill_before),
                "time_bill_after": float(event.time_bill_after),
            } for event in events],
        }, 200

    def cancel_unused_checkin(self, session_id: int, reason: str, actor_id: int,
                              actor_name: str, actor_role: str) -> tuple[dict[str, Any], int]:
        clean_reason = reason.strip() if isinstance(reason, str) else ""
        if not clean_reason or len(clean_reason) > 500:
            return {"error": "Enter a cancellation reason of up to 500 characters."}, 400

        sess = self.repo.get_session_for_update(session_id)
        if not sess:
            return {"error": "Time In not found."}, 404
        if sess.status != "active":
            return {"error": "This Time In is no longer active."}, 409
        if sess.service_mode != "timed" or sess.space_type.name not in {"Regular Lounge", "Premium Lounge"}:
            return {"error": "Only Regular and Premium Time Ins can be cancelled here."}, 409
        if (sess.voided_transaction_id is not None or sess.retained_time_bill is not None
                or Decimal(str(sess.credit_balance or 0)) != 0):
            return {"error": "This Time In carries an earlier checkout or payment."}, 409
        if db.session.query(Order.id).filter_by(customer_session_id=session_id).first():
            return {"error": "This Time In has a placed order and cannot be cancelled."}, 409
        if (db.session.query(Transaction.id).filter_by(session_id=session_id).first()
                or db.session.query(Receivable.id).filter_by(session_id=session_id).first()):
            return {"error": "This Time In has a payment or customer debt and cannot be cancelled."}, 409
        if (db.session.query(BoardroomBooking.id).filter_by(session_id=session_id).first()
                or db.session.query(BookingChange.id).filter_by(session_id=session_id).first()):
            return {"error": "This Time In is linked to a booking. Use Space Bookings."}, 409

        now = self.clock.now()
        uncollected = current_time_bill(sess, now)
        if sess.paused_at:
            before_microseconds = billable_microseconds(sess, now)
            sess.paused_microseconds += max(0, (now - sess.paused_at) // timedelta(microseconds=1))
            sess.paused_at = None
            self._record_time_event(sess, "cancelled", now, actor_id, actor_name,
                                    actor_role, before_microseconds, uncollected)
        sess.status = "cancelled"
        sess.time_out = now
        sess.cancelled_at = now
        sess.cancelled_by_id = actor_id
        sess.cancelled_by_role = actor_role
        sess.cancelled_by_name = actor_name[:100]
        sess.cancel_reason = clean_reason
        sess.cancelled_space_name = sess.space_type.name
        sess.cancelled_uncollected_amount = uncollected
        try:
            self.repo.commit()
        except Exception:
            db.session.rollback()
            raise
        return {"message": "Mistaken Time In cancelled. The seat is available again.",
                "uncollected_time_charge": float(uncollected)}, 200

    def cancelled_checkins(self, page: int) -> dict[str, Any]:
        history = (CustomerSession.query.filter_by(status="cancelled")
                   .order_by(CustomerSession.cancelled_at.desc(), CustomerSession.id.desc())
                   .paginate(page=page, per_page=25, error_out=False))
        return {
            "data": [{
                "session_id": row.id,
                "customer_name": row.customer_name,
                "space_name": row.cancelled_space_name or row.space_type.name,
                "time_in": (row.time_in + timedelta(hours=8)).strftime("%Y-%m-%d %I:%M %p"),
                "cancelled_at": (row.cancelled_at + timedelta(hours=8)).strftime("%Y-%m-%d %I:%M %p"),
                "business_date": manila_date(row.cancelled_at).isoformat(),
                "actor": row.cancelled_by_name,
                "reason": row.cancel_reason,
                "uncollected_time_charge": float(row.cancelled_uncollected_amount or 0),
                "has_time_pause": bool(row.paused_microseconds),
            } for row in history.items],
            "page": page,
            "pages": history.pages,
        }

    def _food_bill(self, sess: CustomerSession) -> tuple[Decimal, Decimal]:
        current = Decimal(str(self.repo.sum_food_total_for_session(sess.id))).quantize(Decimal("0.01"))
        original = db.session.get(Transaction, sess.voided_transaction_id) if sess.voided_transaction_id else None
        carried = Decimal(str(original.food_bill)) if original and original.is_voided else Decimal("0.00")
        return current + carried, carried

    def preview_checkout(self, session_id: int, discount_type: str | None = None, discount_item_id: Any = None) -> dict[str, Any] | tuple[dict[str, Any], int]:
        sess = self.repo.get_session(session_id)
        if not sess:
            return {"error": "Session not found"}, 404

        if sess.status != "active":
            return {"error": "Session is not active"}, 400

        food_only = sess.service_mode == "food_only"
        now = self.clock.now()
        minutes_used = 0 if food_only else float(Decimal(billable_microseconds(sess, now)) / Decimal(60_000_000))
        linked = None if food_only else self.repo.get_active_boardroom_bookings_by_session_ids([session_id]).get(session_id)

        time_bill = current_time_bill(sess, now, booking=linked)
        food_total, carried_food = self._food_bill(sess)
        try:
            discount_amount, selected_type, selected_item_id = self._discount(session_id, discount_type, discount_item_id, time_bill)
        except ValueError as exc:
            return {"error": str(exc)}, 400
        total_bill = (time_bill + food_total - discount_amount).quantize(Decimal("0.01"))

        credit_balance = Decimal(str(getattr(sess, "credit_balance", 0) or 0)).quantize(Decimal("0.01"))
        credit_applied = min(total_bill, credit_balance)
        shortfall = max(Decimal("0.00"), total_bill - credit_balance)
        overpayment = max(Decimal("0.00"), credit_balance - total_bill)

        return {
            "customer_name": sess.customer_name,
            "space_type": sess.space_type.name,
            "service_mode": sess.service_mode,
            "minutes_used": minutes_used,
            "paused": sess.paused_at is not None,
            "time_bill": float(time_bill),
            "food_bill": float(food_total),
            "carried_food_bill": float(carried_food),
            "discount_amount": float(discount_amount),
            "discount_type": selected_type,
            "discount_item_id": selected_item_id,
            "total_bill": float(total_bill),
            "credit_balance": float(credit_balance),
            "credit_applied": float(credit_applied),
            "shortfall": float(shortfall),
            "overpayment": float(overpayment),
            "credit_payment_method": getattr(sess, "credit_payment_method", None),
        }

    def checkout(
        self, session_id: int, payment_method: str = "cash", amount_tendered: Any = None,
        discount_type: str | None = None, discount_item_id: Any = None,
        actor_name: str | None = None, actor_id: int | None = None,
        actor_role: str = "staff",
    ) -> dict[str, Any] | tuple[dict[str, Any], int]:
        sess = self.repo.get_session_for_update(session_id)
        if not sess:
            return {"error": "Session not found"}, 404
        if sess.status != "active":
            return {"error": "Session is not active"}, 400

        payment_method = normalize_payment_method(payment_method)

        credit_balance = Decimal(str(getattr(sess, "credit_balance", 0) or 0)).quantize(Decimal("0.01"))
        credit_method = getattr(sess, "credit_payment_method", None)
        if credit_balance > 0 and credit_method:
            if normalize_payment_method(payment_method) != normalize_payment_method(credit_method):
                return {
                    "error": (
                        f"Retained credit is tied to {payment_method_label(credit_method)}. "
                        "If a different payment method is required, choose full refund first."
                    )
                }, 400

        time_out = self.clock.now()
        food_only = sess.service_mode == "food_only"
        billable_us = 0 if food_only else billable_microseconds(sess, time_out)
        minutes_used = float(Decimal(billable_us) / Decimal(60_000_000))
        rate = 0 if food_only else sess.space_type.rate_per_minute
        linked = None if food_only else self.repo.get_active_boardroom_bookings_by_session_ids([session_id]).get(session_id)

        time_bill = current_time_bill(sess, time_out, booking=linked)

        food_total, _ = self._food_bill(sess)
        if food_only and food_total <= 0:
            return {"error": "Add food before checking out this order."}, 400
        try:
            discount_amount, selected_type, selected_item_id = self._discount(session_id, discount_type, discount_item_id, time_bill)
        except ValueError as exc:
            return {"error": str(exc)}, 400
        total_bill = (time_bill + food_total - discount_amount).quantize(Decimal("0.01"))
        if food_only and total_bill <= 0:
            return {"error": "A food order must have a positive total."}, 400

        # Retained credit resolution
        credit_applied = min(total_bill, credit_balance)
        shortfall = max(Decimal("0.00"), total_bill - credit_balance)
        overpayment = max(Decimal("0.00"), credit_balance - total_bill)

        tendered = None
        change_given = None

        if payment_method == "cash":
            if shortfall > 0:
                if amount_tendered is None:
                    return {"error": "Amount tendered is required for cash payments."}, 400
                try:
                    tendered = parse_money_amount(amount_tendered)
                except ValueError as e:
                    return {"error": str(e)}, 400
                if tendered < shortfall:
                    if credit_balance > 0:
                        return {"error": f"Amount tendered must be at least the required shortfall of ₱{shortfall:.2f}."}, 400
                    return {"error": f"Amount tendered must be at least the total bill of ₱{total_bill:.2f}."}, 400
                change_given = (tendered - shortfall).quantize(Decimal("0.01"))
            else:
                # Fully covered by credit; cash tendered not needed
                tendered = None
                change_given = None
        else:
            tendered = None
            change_given = None

        if sess.paused_at and actor_id is None:
            return {"error": "Authenticated checkout actor is required for a paused time bill."}, 401

        sess.payment_method = payment_method
        sess.amount_tendered = tendered

        if sess.paused_at:
            sess.paused_microseconds += max(0, (time_out - sess.paused_at) // timedelta(microseconds=1))
            sess.paused_at = None
            self._record_time_event(sess, "checked_out", time_out, actor_id, actor_name or "Staff",
                                    actor_role, billable_us, time_bill)

        tx = Transaction(
            session_id=sess.id,
            time_bill=time_bill,
            food_bill=food_total,
            total_bill=total_bill,
            payment_method=payment_method,
            collected_by=actor_name,
            discount_type=selected_type,
            discount_item_id=selected_item_id,
            discount_amount=discount_amount,
            amount_tendered=tendered,
            change_given=change_given,
            billing_start_at=sess.time_in,
            billing_end_at=time_out,
            billable_microseconds=billable_us if not food_only else None,
            customer_name_snapshot=sess.customer_name,
            space_name_snapshot=sess.space_type.name if sess.space_type else None,
            service_mode_snapshot=sess.service_mode,
            number_of_people_snapshot=sess.number_of_people,
            credit_applied=credit_applied,
            credit_refunded=overpayment,
            is_voided=False,
        )

        self.repo.create_transaction(tx)
        self.repo.complete_session(sess, time_out)
        self.repo.link_booking_completion_if_any(sess.id, time_out, tx)

        # If session had retained credit or voided transaction, link to replacement
        if getattr(sess, "voided_transaction_id", None):
            void_req = CheckoutVoidRequest.query.filter_by(
                transaction_id=sess.voided_transaction_id,
                status="approved",
            ).order_by(CheckoutVoidRequest.id.desc()).first()
            if void_req:
                void_req.replacement_transaction_id = tx.id
                void_req.credit_applied = credit_applied
                void_req.credit_remaining = Decimal("0.00")
                if overpayment > 0:
                    void_req.refund_amount = (void_req.refund_amount or Decimal("0.00")) + overpayment

        sess.credit_balance = Decimal("0.00")
        sess.credit_payment_method = None
        sess.retained_time_bill = None
        sess.voided_transaction_id = None

        self.repo.commit()

        self.notifier.session_checked_out(
            {
                "session_id": sess.id,
                "customer_name": sess.customer_name,
                "space_type": sess.space_type.name if sess.space_type else "N/A",
                "total_bill": float(total_bill),
            }
        )

        amount_tendered_val = float(tx.amount_tendered) if tx.amount_tendered is not None else None
        change_given_val = float(tx.change_given) if tx.change_given is not None else None

        return {
            "customer_name": sess.customer_name,
            "service_mode": sess.service_mode,
            "minutes_used": round(minutes_used, 2),
            "rate_per_minute": float(rate),
            "time_bill": float(time_bill),
            "food_bill": float(food_total),
            "discount_amount": float(discount_amount),
            "total_bill": float(total_bill),
            "payment_method": payment_method,
            "payment_label": payment_method_label(payment_method),
            "status": sess.status,
            "amount_tendered": amount_tendered_val,
            "change_given": change_given_val,
            "credit_applied": float(credit_applied),
            "credit_refunded": float(overpayment),
        }

    def checkout_records(self, page: int | None = None, per_page: int | None = None, *,
                         date_from=None, date_to=None, payment_method: str = "",
                         search: str = "", status: str = ""):
        if page and per_page:
            return self.repo.list_transactions_paginated(
                page=page, per_page=per_page, date_from=date_from, date_to=date_to,
                payment_method=payment_method, search=search, status=status,
            )
        return self.repo.list_transactions()

    def space_availability(self) -> list[dict[str, Any]]:
        spaces = self.repo.list_space_types_for_availability()
        whole_hub_reserved = self.repo.blocking_booking_at(self.clock.now() + timedelta(hours=8), whole_hub_only=True)
        rows: list[dict[str, Any]] = []
        for space in spaces:
            occupied = self.repo.sum_active_occupancy(space.id)
            cap = int(space.capacity) if space.capacity else 0
            left = 0 if whole_hub_reserved else (max(cap - occupied, 0) if cap else None)
            rows.append(
                {
                    "space_id": space.id,
                    "space_name": space.name,
                    "capacity": cap,
                    "occupied": occupied,
                    "seats_left": left,
                }
            )
        return rows

    def request_checkout_void(
        self, transaction_id: int, reason: str, actor_id: int, request_key: str | None = None,
    ) -> tuple[dict[str, Any], int]:
        reason = (reason or "").strip()
        if not reason:
            return {"error": "Reason is required for void request."}, 400

        tx = self.repo.get_transaction_for_update(transaction_id)
        if not tx:
            return {"error": "Transaction not found."}, 404

        if tx.is_voided:
            return {"error": "This transaction has already been voided."}, 400

        existing = CheckoutVoidRequest.query.filter(
            CheckoutVoidRequest.transaction_id == tx.id,
            CheckoutVoidRequest.status.in_(["pending", "approved"]),
        ).first()
        if existing:
            if existing.status == "pending":
                return {"error": "A void request is already pending approval for this transaction."}, 400
            return {"error": "This transaction has already been voided."}, 400

        if request_key:
            dup = CheckoutVoidRequest.query.filter_by(request_key=request_key).first()
            if dup:
                return {
                    "message": "Void request already submitted.",
                    "request_id": dup.id,
                    "status": dup.status,
                }, 200

        now_utc = self.clock.now()
        manila_dt = manila_date(tx.created_at)

        req = CheckoutVoidRequest(
            transaction_id=tx.id,
            status="pending",
            request_reason=reason,
            requested_by_id=actor_id,
            requested_at=now_utc,
            request_key=request_key,
            original_amount=tx.total_bill,
            original_payment_method=tx.payment_method,
            original_business_date=manila_dt,
        )
        db.session.add(req)
        db.session.commit()
        return {
            "message": "Void request submitted for approval.",
            "request_id": req.id,
            "status": req.status,
            "void_request": serialize_void_request(req),
        }, 201

    def list_void_requests(self, status: str | None = None) -> list[CheckoutVoidRequest]:
        query = CheckoutVoidRequest.query
        if status:
            query = query.filter_by(status=status)
        return query.order_by(CheckoutVoidRequest.requested_at.desc()).all()

    def reject_checkout_void(
        self, request_id: int, reason: str, admin_id: int,
    ) -> tuple[dict[str, Any], int]:
        reason = (reason or "").strip()
        req = CheckoutVoidRequest.query.filter_by(id=request_id).with_for_update().first()
        if not req:
            return {"error": "Void request not found."}, 404
        if req.status != "pending":
            return {"error": f"Void request is already {req.status}."}, 400

        now_utc = self.clock.now()
        req.status = "rejected"
        req.decision_reason = reason or "Rejected by admin"
        req.approver_id = admin_id
        req.decided_at = now_utc
        req.decision_business_date = manila_date(now_utc)
        db.session.commit()
        return {
            "message": "Void request rejected.",
            "request_id": req.id,
            "status": "rejected",
            "void_request": serialize_void_request(req),
        }, 200

    def approve_checkout_void(
        self, request_id: int, money_treatment: str, decision_reason: str, admin_id: int,
    ) -> tuple[dict[str, Any], int]:
        if money_treatment not in ("false_entry", "refund", "retained_credit"):
            return {
                "error": "Invalid money treatment. Must be one of: false_entry, refund, retained_credit."
            }, 400

        req = CheckoutVoidRequest.query.filter_by(id=request_id).with_for_update().first()
        if not req:
            return {"error": "Void request not found."}, 404
        if req.status != "pending":
            return {"error": f"Void request is already {req.status}."}, 400

        tx = self.repo.get_transaction_for_update(req.transaction_id)
        if not tx:
            return {"error": "Transaction not found."}, 404
        if tx.is_voided:
            return {"error": "Transaction is already voided."}, 400

        sess = self.repo.get_session_for_update(tx.session_id)
        if not sess:
            return {"error": "Session not found."}, 404

        now_utc = self.clock.now()
        manila_now = manila_date(now_utc)
        decision_reason = (decision_reason or "").strip()

        # Preserve the original receipt even when the customer later checks in elsewhere.
        if tx.billing_start_at is None:
            tx.billing_start_at = sess.time_in
        if tx.billing_end_at is None:
            tx.billing_end_at = sess.time_out
        if tx.customer_name_snapshot is None:
            tx.customer_name_snapshot = sess.customer_name
        if tx.space_name_snapshot is None:
            tx.space_name_snapshot = sess.space_type.name if sess.space_type else None
        if tx.service_mode_snapshot is None:
            tx.service_mode_snapshot = sess.service_mode
        if tx.number_of_people_snapshot is None:
            tx.number_of_people_snapshot = sess.number_of_people
        if tx.change_given is None and tx.amount_tendered is not None:
            tx.change_given = Decimal(str(tx.amount_tendered)) - tx.total_bill

        # Historical funding check for false_entry
        recon_flag = None
        sales_repo = self.sales_repo or SalesRepository()
        if money_treatment == "false_entry":
            orig_ledger = sales_repo.daily_ledger(req.original_business_date, req.original_business_date).get(req.original_business_date)
            if orig_ledger:
                cur_bal = sales_repo.method_balance(orig_ledger, req.original_payment_method)
                if cur_bal - req.original_amount < 0:
                    recon_flag = (
                        f"Historical funding discrepancy: Voiding false entry of ₱{req.original_amount:.2f} ({req.original_payment_method}) "
                        f"leaves {req.original_business_date.isoformat()} method balance negative (₱{cur_bal - req.original_amount:.2f}). "
                        f"Earlier expenses or payables may have been funded by uncollected revenue."
                    )

        # Mark original transaction as voided
        tx.is_voided = True

        # Update void request
        req.status = "approved"
        req.money_treatment = money_treatment
        req.decision_reason = decision_reason
        req.approver_id = admin_id
        req.decided_at = now_utc
        req.decision_business_date = manila_now
        req.reconciliation_flag = recon_flag

        if money_treatment == "false_entry":
            req.sale_delta = -tx.total_bill
            req.cash_delta = -tx.total_bill
            req.refund_amount = Decimal("0.00")
            req.credit_amount = Decimal("0.00")
            req.credit_remaining = Decimal("0.00")
        elif money_treatment == "refund":
            req.sale_delta = -tx.total_bill
            req.cash_delta = -tx.total_bill
            req.refund_amount = tx.total_bill
            req.credit_amount = Decimal("0.00")
            req.credit_remaining = Decimal("0.00")
        elif money_treatment == "retained_credit":
            req.sale_delta = -tx.total_bill
            req.cash_delta = Decimal("0.00")
            req.refund_amount = Decimal("0.00")
            req.credit_amount = tx.total_bill
            req.credit_remaining = tx.total_bill
        db.session.commit()

        return {
            "message": "Void approved. The old checkout remains in records; check the customer in again in the correct space.",
            "request_id": req.id,
            "status": "approved",
            "money_treatment": money_treatment,
            "reconciliation_flag": recon_flag,
            "void_request": serialize_void_request(req),
        }, 200
