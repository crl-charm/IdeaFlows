from datetime import datetime, date
from decimal import Decimal
from hashlib import sha256
from app import db


class ReceivableTab(db.Model):
    __tablename__ = "receivable_tabs"

    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(100), nullable=False)
    customer_contact = db.Column(db.String(100), nullable=True)
    normalized_name = db.Column(db.String(100), nullable=False)
    normalized_contact = db.Column(db.String(100), nullable=False, default="")
    active_key = db.Column(db.String(64), unique=True, nullable=True)
    opened_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    closed_at = db.Column(db.DateTime, nullable=True)

    @staticmethod
    def identity(name: str, contact: str | None) -> tuple[str, str, str | None]:
        normalized_name = " ".join(name.split()).casefold()
        normalized_contact = "".join((contact or "").split()).casefold()
        key = sha256(f"{normalized_name}\0{normalized_contact}".encode()).hexdigest() if normalized_contact else None
        return normalized_name, normalized_contact, key


class Receivable(db.Model):
    __tablename__ = "receivables"

    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(100), nullable=False)
    customer_contact = db.Column(db.String(100), nullable=True)
    items_description = db.Column(db.Text, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    amount_owed = db.Column(db.Numeric(10, 2), nullable=False)
    due_date = db.Column(db.Date, nullable=False)
    paid = db.Column(db.Boolean, default=False, nullable=False)
    partial_paid = db.Column(db.Numeric(10, 2), default=0, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey("customer_sessions.id"), nullable=True)
    approved_by_staff = db.Column(db.String(100), nullable=True)
    paid_at = db.Column(db.DateTime, nullable=True)
    incurred_date = db.Column(db.Date, nullable=True)
    tab_id = db.Column(db.Integer, db.ForeignKey("receivable_tabs.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    created_by_user = db.relationship("User", backref="receivables")
    session = db.relationship("CustomerSession", backref="receivables")
    tab = db.relationship("ReceivableTab", backref="receivables")


class ReceivablePayment(db.Model):
    __tablename__ = "receivable_payments"

    id = db.Column(db.Integer, primary_key=True)
    receivable_id = db.Column(db.Integer, db.ForeignKey("receivables.id"), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    payment_method = db.Column(db.String(50), nullable=False, default="cash")
    received_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    received_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    payment_group_id = db.Column(db.String(32), nullable=True)
    balance_before = db.Column(db.Numeric(10, 2), nullable=True)
    balance_after = db.Column(db.Numeric(10, 2), nullable=True)
    request_key = db.Column(db.String(200), nullable=True, index=True)

    receivable = db.relationship("Receivable", backref="payments")
    received_by_user = db.relationship("User", foreign_keys=[received_by])
