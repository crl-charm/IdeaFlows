from datetime import datetime, date
from decimal import Decimal
from app import db


class Expense(db.Model):
    __tablename__ = "expenses"

    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    expense_date = db.Column(db.Date, nullable=False)
    payment_method = db.Column(db.String(50), nullable=True)
    # NULL keeps the historical ledger treatment for records made before this upgrade.
    funding_source = db.Column(db.String(20), nullable=True)
    balance_before = db.Column(db.Numeric(12, 2), nullable=True)
    balance_after = db.Column(db.Numeric(12, 2), nullable=True)
    logged_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    voided_at = db.Column(db.DateTime, nullable=True)
    voided_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    void_reason = db.Column(db.String(255), nullable=True)
    void_balance_before = db.Column(db.Numeric(12, 2), nullable=True)
    void_balance_after = db.Column(db.Numeric(12, 2), nullable=True)
    request_key = db.Column(db.String(200), unique=True, nullable=True)

    logged_by_user = db.relationship("User", foreign_keys=[logged_by], backref="expenses")
    voided_by_user = db.relationship("User", foreign_keys=[voided_by])
