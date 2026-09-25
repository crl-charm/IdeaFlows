from __future__ import annotations

from decimal import Decimal

from app import db
from app.models.base_model import BaseModel


class FinanceBudget(db.Model, BaseModel):
    """Represents an allocation bucket for finance tracking."""

    __tablename__ = "finance_budgets"

    _name = db.Column("name", db.String(120), nullable=False, default="Default Budget")
    _total_budget = db.Column("total_budget", db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    _allocated = db.Column("allocated", db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))


class FinanceTransaction(db.Model, BaseModel):
    """Represents a spend or allocation transaction."""

    __tablename__ = "finance_transactions"

    _budget_id = db.Column("budget_id", db.Integer, db.ForeignKey("finance_budgets.id"), nullable=False)
    _type = db.Column("type", db.String(30), nullable=False, default="expense")
    _amount = db.Column("amount", db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    _description = db.Column("description", db.String(255), nullable=True)
    payment_method = db.Column(db.String(50), nullable=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    request_key = db.Column(db.String(200), unique=True, nullable=True)

    budget = db.relationship("FinanceBudget", backref="transactions")
    actor = db.relationship("User", foreign_keys=[actor_id])
