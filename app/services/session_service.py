from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any, Optional

from app.utils.billing import calculate_time_bill
from app.core.interfaces import Clock, Notifier
from app.models import CustomerSession, Transaction
from app.repositories.session_repository import SessionRepository
from app.utils.payment import normalize_payment_method, payment_method_label, parse_money_amount


@dataclass(frozen=True)
class SessionService:
    repo: SessionRepository
    clock: Clock
    notifier: Notifier

    def checkin(
        self,
        *,
        customer_name: str,
        school: Optional[str],
        course: Optional[str],
        space_type_id: Optional[int],
        number_of_people: int,
    ) -> dict[str, Any]:
        if number_of_people <= 0:
            return {"error": "Number of people must be at least 1."}, 400

        now = self.clock.now()
        sess = CustomerSession(
            customer_name=customer_name,
            school=school,
            course=course,
            number_of_people=number_of_people,
            space_type_id=space_type_id,
            time_in=now,
            status="active",
        )

        if space_type_id:
            space = self.repo.get_space_type(space_type_id)
            if space and space.capacity:
                occupied = self.repo.sum_active_occupancy(space_type_id)
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

        self.repo.add_session(sess)
        return {"message": "Customer checked in successfully", "session_id": sess.id}, 200

    def get_active_sessions_view(self) -> list[dict[str, Any]]:
        sessions = self.repo.get_active_sessions()
        session_ids = [s.id for s in sessions]
        boardroom_by_session = self.repo.get_active_boardroom_bookings_by_session_ids(session_ids)

        result: list[dict[str, Any]] = []
        now = self.clock.now()

        for sess in sessions:
            time_difference = now - sess.time_in
            minutes_used = time_difference.total_seconds() / 60
            rate = sess.space_type.rate_per_minute
            current_bill = calculate_time_bill(sess.space_type, minutes_used)

            linked = boardroom_by_session.get(sess.id)
            purpose = linked.purpose if linked and sess.space_type.name == "Boardroom" else None

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
                    "seconds_used": int(time_difference.total_seconds()),
                    "current_bill": float(current_bill),
                }
            )

        return result

    def preview_checkout(self, session_id: int) -> dict[str, Any] | tuple[dict[str, Any], int]:
        sess = self.repo.get_session(session_id)
        if not sess:
            return {"error": "Session not found"}, 404

        now = self.clock.now()
        minutes_used = (now - sess.time_in).total_seconds() / 60
        rate = sess.space_type.rate_per_minute
        time_bill = calculate_time_bill(sess.space_type, minutes_used)
        food_total = Decimal(str(self.repo.sum_food_total_for_session(session_id))).quantize(Decimal("0.01"))
        total_bill = (time_bill + food_total).quantize(Decimal("0.01"))

        return {
            "customer_name": sess.customer_name,
            "minutes_used": minutes_used,
            "time_bill": float(time_bill),
            "food_bill": float(food_total),
            "total_bill": float(total_bill),
        }

    def checkout(
        self, session_id: int, payment_method: str = "cash", amount_tendered: Any = None
    ) -> dict[str, Any] | tuple[dict[str, Any], int]:
        # Serialize checkout attempts for this session on databases that support
        # row locks (MySQL in production). This prevents two different browser
        # keys from creating two transactions at the same time.
        sess = self.repo.get_session_for_update(session_id)
        if not sess:
            return {"error": "Session not found"}, 404
        if sess.status == "completed":
            return {"error": "Session already checked out"}, 400

        payment_method = normalize_payment_method(payment_method)

        time_out = self.clock.now()
        minutes_used = (time_out - sess.time_in).total_seconds() / 60
        rate = sess.space_type.rate_per_minute
        time_bill = calculate_time_bill(sess.space_type, minutes_used)
        food_total = Decimal(str(self.repo.sum_food_total_for_session(session_id))).quantize(Decimal("0.01"))
        total_bill = (time_bill + food_total).quantize(Decimal("0.01"))

        sess.payment_method = payment_method
        tx = Transaction(
            session_id=sess.id,
            time_bill=time_bill,
            food_bill=food_total,
            total_bill=total_bill,
            payment_method=payment_method,
        )

        if payment_method == "cash":
            if amount_tendered is None:
                return {"error": "Amount tendered is required for cash payments."}, 400
            try:
                tendered = parse_money_amount(amount_tendered)
            except ValueError as e:
                return {"error": str(e)}, 400
            if tendered < total_bill:
                return {"error": "Amount tendered must be at least the total bill."}, 400
            tx.amount_tendered = tendered
            sess.amount_tendered = tendered
        else:
            tx.amount_tendered = None
            sess.amount_tendered = None

        self.repo.create_transaction(tx)
        self.repo.complete_session(sess, time_out)
        self.repo.link_booking_completion_if_any(sess.id, time_out)
        self.repo.commit()

        self.notifier.session_checked_out(
            {
                "session_id": sess.id,
                "customer_name": sess.customer_name,
                "space_type": sess.space_type.name,
                "total_bill": float(total_bill),
            }
        )

        amount_tendered_val = float(tx.amount_tendered) if tx.amount_tendered is not None else None
        change_given = round(amount_tendered_val - float(total_bill), 2) if amount_tendered_val is not None else None

        return {
            "customer_name": sess.customer_name,
            "minutes_used": round(minutes_used, 2),
            "rate_per_minute": float(rate),
            "time_bill": float(time_bill),
            "food_bill": float(food_total),
            "total_bill": float(total_bill),
            "payment_method": payment_method,
            "payment_label": payment_method_label(payment_method),
            "status": sess.status,
            "amount_tendered": amount_tendered_val,
            "change_given": change_given,
        }

    def checkout_records(self, page: int | None = None, per_page: int | None = None):
        if page and per_page:
            return self.repo.list_transactions_paginated(page=page, per_page=per_page)
        return self.repo.list_transactions()

    def space_availability(self) -> list[dict[str, Any]]:
        spaces = self.repo.list_space_types_for_availability()
        rows: list[dict[str, Any]] = []
        for space in spaces:
            occupied = self.repo.sum_active_occupancy(space.id)
            cap = int(space.capacity) if space.capacity else 0
            left = max(cap - occupied, 0) if cap else None
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

