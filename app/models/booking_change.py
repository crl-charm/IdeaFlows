from datetime import datetime
from decimal import Decimal, ROUND_CEILING

from app import db
from app.utils.dates import manila_date


class BookingChange(db.Model):
    __tablename__ = "booking_changes"

    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey("boardroom_bookings.id"), nullable=False, index=True)
    session_id = db.Column(db.Integer, db.ForeignKey("customer_sessions.id"), nullable=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey("transactions.id"), nullable=True)
    action = db.Column(db.String(20), nullable=False)
    actor = db.Column(db.String(100), nullable=False)
    customer_name = db.Column(db.String(100), nullable=False)
    event_at = db.Column(db.DateTime, nullable=False)
    business_date = db.Column(db.Date, nullable=False)
    amount_before = db.Column(db.Numeric(10, 2), nullable=False)
    amount_after = db.Column(db.Numeric(10, 2), nullable=False)
    payment_method = db.Column(db.String(50), nullable=True)
    before_state = db.Column(db.JSON, nullable=True)
    after_state = db.Column(db.JSON, nullable=False)

    @staticmethod
    def snapshot(booking):
        start = datetime.combine(booking.date, booking.start_time)
        end = booking.expected_end_at or datetime.combine(booking.date, booking.end_time)
        hours = max(1, (Decimal(str((end - start).total_seconds())) / 3600).to_integral_value(rounding=ROUND_CEILING))
        quote = Decimal(str(booking.hourly_rate)) * hours
        return {
            "status": booking.status,
            "date": booking.date.isoformat(),
            "start_time": booking.start_time.strftime("%H:%M"),
            "end_time": booking.end_time.strftime("%H:%M"),
            "hourly_rate": str(booking.hourly_rate),
            "quoted_amount": str(quote if booking.status != "cancelled" else Decimal("0.00")),
            "extended_minutes": booking.extended_minutes or 0,
        }

    @classmethod
    def capture(cls, booking, action: str, actor: str | None, event_at: datetime,
                before_state=None, transaction=None):
        after_state = cls.snapshot(booking)
        return cls(
            booking_id=booking.id,
            session_id=booking.session_id,
            transaction_id=transaction.id if transaction else None,
            action=action,
            actor=actor or "System",
            customer_name=booking.customer_name,
            event_at=event_at,
            business_date=manila_date(event_at),
            amount_before=Decimal(before_state["quoted_amount"]) if before_state else Decimal("0.00"),
            amount_after=transaction.total_bill if transaction else Decimal(after_state["quoted_amount"]),
            payment_method=transaction.payment_method if transaction else None,
            before_state=before_state,
            after_state=after_state,
        )
