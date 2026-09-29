from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app import db
from app.models.base_model import BaseModel


class CheckoutVoidRequest(db.Model, BaseModel):
    """Tracks staff void requests and admin decisions with full financial audit trail."""

    __tablename__ = "checkout_void_requests"

    transaction_id = db.Column(
        db.Integer,
        db.ForeignKey("transactions.id"),
        nullable=False,
        index=True,
    )
    status = db.Column(db.String(20), nullable=False, default="pending")  # pending, approved, rejected
    request_reason = db.Column(db.Text, nullable=False)
    requested_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    requested_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    request_key = db.Column(db.String(200), unique=True, nullable=True)

    approver_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    decided_at = db.Column(db.DateTime, nullable=True)
    decision_reason = db.Column(db.Text, nullable=True)
    money_treatment = db.Column(db.String(30), nullable=True)  # false_entry, refund, retained_credit

    # Snapshots of the original transaction at time of request
    original_amount = db.Column(db.Numeric(10, 2), nullable=False)
    original_payment_method = db.Column(db.String(50), nullable=False)
    original_business_date = db.Column(db.Date, nullable=False)
    decision_business_date = db.Column(db.Date, nullable=True)

    # Financial deltas and balances
    sale_delta = db.Column(db.Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    cash_delta = db.Column(db.Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    credit_amount = db.Column(db.Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    credit_remaining = db.Column(db.Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    credit_applied = db.Column(db.Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    refund_amount = db.Column(db.Numeric(10, 2), nullable=False, default=Decimal("0.00"))

    # Linked replacement checkout if re-checked out
    replacement_transaction_id = db.Column(db.Integer, db.ForeignKey("transactions.id"), nullable=True)
    reconciliation_flag = db.Column(db.Text, nullable=True)

    transaction = db.relationship(
        "Transaction",
        foreign_keys=[transaction_id],
        backref=db.backref("void_requests", lazy="select", order_by="desc(CheckoutVoidRequest.id)"),
    )
    requested_by = db.relationship("User", foreign_keys=[requested_by_id])
    approver = db.relationship("User", foreign_keys=[approver_id])
    replacement_transaction = db.relationship("Transaction", foreign_keys=[replacement_transaction_id])
