"""Immutable account of an already-paid visit recorded after departure."""
from app import db


class MissedCheckoutCorrection(db.Model):
    __tablename__ = "missed_checkout_corrections"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("customer_sessions.id"), nullable=False, unique=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey("transactions.id"), nullable=False, unique=True)
    departure_at = db.Column(db.DateTime, nullable=False)
    paid_at = db.Column(db.DateTime, nullable=False)
    recorded_at = db.Column(db.DateTime, nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    actor_name = db.Column(db.String(100), nullable=False)
    actor_role = db.Column(db.String(20), nullable=False)
    collector_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    collector_name = db.Column(db.String(100), nullable=False)
    reason = db.Column(db.String(40), nullable=False)
    note = db.Column(db.String(500), nullable=False, default="")
    amount_received = db.Column(db.Numeric(12, 2), nullable=False)
    payment_method = db.Column(db.String(50), nullable=False)
    before_snapshot = db.Column(db.JSON, nullable=False)
    after_snapshot = db.Column(db.JSON, nullable=False)
    preview_revision = db.Column(db.String(64), nullable=False)
    request_key = db.Column(db.String(64), nullable=False, unique=True)
