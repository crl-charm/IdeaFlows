from datetime import datetime, date
from decimal import Decimal
from app import db


class Payable(db.Model):
    __tablename__ = "payables"

    id = db.Column(db.Integer, primary_key=True)
    creditor_name = db.Column(db.String(100), nullable=False)
    items_description = db.Column(db.Text, nullable=False)
    amount_owed = db.Column(db.Numeric(10, 2), nullable=False)
    due_date = db.Column(db.Date, nullable=False)
    incurred_date = db.Column(db.Date, nullable=False, default=date.today)
    status = db.Column(db.String(30), default="Unpaid", nullable=False)  # Unpaid, Partially Paid, Paid
    partial_paid = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    created_by_user = db.relationship("User", backref="payables")


class PayablePayment(db.Model):
    __tablename__ = "payable_payments"

    id = db.Column(db.Integer, primary_key=True)
    payable_id = db.Column(db.Integer, db.ForeignKey("payables.id"), nullable=False, index=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    payment_method = db.Column(db.String(50), nullable=False)
    paid_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    paid_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    balance_before = db.Column(db.Numeric(10, 2), nullable=False)
    balance_after = db.Column(db.Numeric(10, 2), nullable=False)
    # NULL preserves the original Daily Balance treatment for older payments.
    funding_source = db.Column(db.String(20), nullable=True)
    method_balance_before = db.Column(db.Numeric(12, 2), nullable=True)
    method_balance_after = db.Column(db.Numeric(12, 2), nullable=True)
    request_key = db.Column(db.String(200), unique=True, nullable=True)

    payable = db.relationship("Payable", backref="payments")
    paid_by_user = db.relationship("User", foreign_keys=[paid_by])
