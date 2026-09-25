from __future__ import annotations

from decimal import Decimal, InvalidOperation

from sqlalchemy import func

from app.models.finance import FinanceBudget, FinanceTransaction
from app.services.export_service import ExportService
from app.utils.payment import VALID_PAYMENT_METHODS


class FinanceService(ExportService):
    """Handles finance summary, transactions, and reporting."""

    def get_summary(self) -> dict:
        total_budget = self._db.session.query(func.sum(FinanceBudget._total_budget)).scalar() or Decimal("0.00")
        allocated = self._db.session.query(func.sum(FinanceBudget._allocated)).scalar() or Decimal("0.00")
        spent = self._db.session.query(func.sum(FinanceTransaction._amount)).filter(FinanceTransaction._type == "expense").scalar() or Decimal("0.00")
        transactions = (
            FinanceTransaction.query.order_by(FinanceTransaction.created_at.desc()).limit(20).all()
        )
        remaining = Decimal(total_budget) - Decimal(spent)
        return {
            "total_budget": float(total_budget),
            "allocated": float(allocated),
            "spent": float(spent),
            "remaining": float(remaining),
            "transactions": [
                {
                    "id": txn.id,
                    "type": txn._type,
                    "amount": float(txn._amount),
                    "description": txn._description,
                    "created_at": txn.created_at.isoformat(),
                    "payment_method": txn.payment_method or "unclassified",
                    "actor": txn.actor.username if txn.actor else "Unknown",
                }
                for txn in transactions
            ],
        }

    def add_transaction(self, budget_id: int, txn_type: str, amount, description: str | None,
                        payment_method: str, actor_id: int, request_key: str | None = None) -> dict:
        if txn_type not in {"income", "expense"} or not isinstance(payment_method, str) or payment_method not in VALID_PAYMENT_METHODS:
            raise ValueError("Select a valid type and payment method.")
        try:
            money = Decimal(str(amount))
            if not money.is_finite() or money <= 0 or money.as_tuple().exponent < -2:
                raise ValueError
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError("Enter an amount greater than zero with up to two decimal places.")
        if not self._db.session.get(FinanceBudget, budget_id):
            raise ValueError("Budget not found.")
        if not isinstance(description, str) or not description.strip() or len(description.strip()) > 255:
            raise ValueError("Enter a description up to 255 characters.")
        if request_key and FinanceTransaction.query.filter_by(request_key=request_key).first():
            raise ValueError("This adjustment was already recorded.")
        txn = FinanceTransaction(
            _budget_id=budget_id,
            _type=txn_type,
            _amount=money,
            _description=description,
            payment_method=payment_method,
            actor_id=actor_id,
            request_key=request_key,
        )
        self._db.session.add(txn)
        self._db.session.commit()
        return {"id": txn.id}

    def get_report(self) -> dict:
        return self.get_summary()

    def get_dashboard_data(self) -> dict:
        return self.get_summary()
