from datetime import datetime

from app import db


class SoftBalanceEntry(db.Model):
    """Stores AM/PM soft balancing snapshots with history."""

    __tablename__ = "soft_balance_entries"

    id = db.Column(db.Integer, primary_key=True)
    balance_date = db.Column(db.Date, nullable=False, index=True)
    period = db.Column(db.String(2), nullable=False)  # AM or PM
    total_revenue = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    total_expenses = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    total_collections = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    total_payables_paid = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    total_other_income = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    total_budget_spend = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    net_balance = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    notes = db.Column(db.Text, nullable=True)
    generated_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    generated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    generated_by_user = db.relationship("User", backref="soft_balance_entries")
