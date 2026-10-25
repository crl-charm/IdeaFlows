from datetime import datetime

from app import db


class CashBoxEvent(db.Model):
    __tablename__ = "cash_box_events"

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(20), nullable=False)
    box = db.Column(db.String(20), nullable=False, index=True)
    payment_method = db.Column(db.String(20), nullable=False, default="cash")
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    effect = db.Column(db.Numeric(12, 2), nullable=False)
    effective_date = db.Column(db.Date, nullable=False, index=True)
    recorded_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    actor_name = db.Column(db.String(100), nullable=False)
    note = db.Column(db.String(255))
    recipient = db.Column(db.String(100))
    repay_owner = db.Column(db.Boolean, nullable=False, default=False)
    reverses_id = db.Column(db.Integer, db.ForeignKey("cash_box_events.id"), unique=True)
    replaces_id = db.Column(db.Integer, db.ForeignKey("cash_box_events.id"), unique=True)
    request_key = db.Column(db.String(200), unique=True)
    balance_before = db.Column(db.Numeric(12, 2))
    balance_after = db.Column(db.Numeric(12, 2))

    actor = db.relationship("User", foreign_keys=[actor_id])
    reversed_entry = db.relationship("CashBoxEvent", remote_side=[id], foreign_keys=[reverses_id])
