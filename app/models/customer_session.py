from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from app import db


class CustomerSession(db.Model):
    __tablename__ = "customer_sessions"

    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(100), nullable=False)
    school = db.Column(db.String(100), nullable=True)
    course = db.Column(db.String(100), nullable=True)
    number_of_people = db.Column(db.Integer, nullable=False, default=1)
    space_type_id = db.Column(db.Integer, db.ForeignKey("space_types.id"), nullable=False)
    service_mode = db.Column(db.String(16), nullable=False, default="timed", server_default="timed")
    time_in = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    time_out = db.Column(db.DateTime, nullable=True)
    paused_at = db.Column(db.DateTime, nullable=True)
    paused_microseconds = db.Column(db.BigInteger, nullable=False, default=0, server_default="0")
    status = db.Column(db.String(20), default="active", nullable=False)
    cancelled_at = db.Column(db.DateTime, nullable=True)
    cancelled_by_id = db.Column(db.Integer, nullable=True)
    cancelled_by_role = db.Column(db.String(20), nullable=True)
    cancelled_by_name = db.Column(db.String(100), nullable=True)
    cancel_reason = db.Column(db.String(500), nullable=True)
    cancelled_space_name = db.Column(db.String(100), nullable=True)
    cancelled_uncollected_amount = db.Column(db.Numeric(10, 2), nullable=True)
    payment_method = db.Column(db.String(50), nullable=False, default="cash")
    amount_tendered = db.Column(db.Numeric(10, 2), nullable=True)

    # Retained credit and booking retention on reopened sessions
    credit_balance = db.Column(db.Numeric(10, 2), nullable=False, default=Decimal("0.00"), server_default="0.00")
    credit_payment_method = db.Column(db.String(50), nullable=True)
    retained_time_bill = db.Column(db.Numeric(10, 2), nullable=True)
    voided_transaction_id = db.Column(db.Integer, nullable=True)

    space_type = db.relationship("SpaceType", backref="sessions")
