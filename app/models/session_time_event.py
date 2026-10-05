from __future__ import annotations

from app import db


class SessionTimeEvent(db.Model):
    __tablename__ = "session_time_events"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("customer_sessions.id"), nullable=False, index=True)
    action = db.Column(db.String(20), nullable=False)
    occurred_at = db.Column(db.DateTime, nullable=False)
    business_date = db.Column(db.Date, nullable=False)
    actor_id = db.Column(db.Integer, nullable=False)
    actor_name = db.Column(db.String(100), nullable=False)
    actor_role = db.Column(db.String(20), nullable=False)
    billable_microseconds_before = db.Column(db.BigInteger, nullable=False)
    billable_microseconds_after = db.Column(db.BigInteger, nullable=False)
    time_bill_before = db.Column(db.Numeric(10, 2), nullable=False)
    time_bill_after = db.Column(db.Numeric(10, 2), nullable=False)
