from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from app import db


class Transaction(db.Model):
    __tablename__ = "transactions"

    id = db.Column(db.Integer, primary_key=True)

    session_id = db.Column(
        db.Integer,
        db.ForeignKey("customer_sessions.id"),
        nullable=False,
    )

    time_bill = db.Column(db.Numeric(10, 2), nullable=False)
    food_bill = db.Column(db.Numeric(10, 2), nullable=False)
    total_bill = db.Column(db.Numeric(10, 2), nullable=False)
    payment_method = db.Column(db.String(50), nullable=False, default="cash")
    collected_by = db.Column(db.String(100), nullable=True)
    amount_tendered = db.Column(db.Numeric(10, 2), nullable=True)
    discount_type = db.Column(db.String(20), nullable=True)
    discount_item_id = db.Column(db.Integer, nullable=True)
    discount_amount = db.Column(db.Numeric(10, 2), nullable=False, default=Decimal("0.00"))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Immutable receipt snapshot fields so old receipts do not change when sessions reopen
    billing_start_at = db.Column(db.DateTime, nullable=True)
    billing_end_at = db.Column(db.DateTime, nullable=True)
    customer_name_snapshot = db.Column(db.String(100), nullable=True)
    space_name_snapshot = db.Column(db.String(100), nullable=True)
    service_mode_snapshot = db.Column(db.String(16), nullable=True)
    number_of_people_snapshot = db.Column(db.Integer, nullable=True)
    change_given = db.Column(db.Numeric(10, 2), nullable=True)

    # Void and credit status
    is_voided = db.Column(db.Boolean, default=False, nullable=False, server_default="0")
    credit_applied = db.Column(db.Numeric(10, 2), nullable=False, default=Decimal("0.00"), server_default="0.00")
    credit_refunded = db.Column(db.Numeric(10, 2), nullable=False, default=Decimal("0.00"), server_default="0.00")

    session = db.relationship("CustomerSession")

    @property
    def active_void_request(self):
        for req in getattr(self, "void_requests", []):
            if req.status in ("pending", "approved"):
                return req
        return None

    @property
    def latest_void_request(self):
        requests = getattr(self, "void_requests", [])
        return requests[0] if requests else None
