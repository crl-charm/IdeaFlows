from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.exc import IntegrityError

from app import db
from app.repositories.payable_repository import PayableRepository
from app.repositories.sales_repository import SalesRepository
from app.models.payable import Payable
from app.utils.dates import manila_date
from app.utils.payment import VALID_PAYMENT_METHODS


@dataclass(frozen=True)
class PayableService:
    repo: PayableRepository

    def list_all(self) -> list[dict[str, Any]]:
        payables = self.repo.list_all()
        return [
            {
                "id": p.id,
                "creditor_name": p.creditor_name,
                "items": p.items_description,
                "amount_owed": float(p.amount_owed),
                "partial_paid": float(p.partial_paid),
                "due_date": p.due_date.strftime("%Y-%m-%d"),
                "incurred_date": p.incurred_date.strftime("%Y-%m-%d"),
                "status": p.status,
                "created_by": p.created_by_user.username if p.created_by_user else "Unknown",
                "payments": [
                    {
                        "id": payment.id,
                        "payable_id": payment.payable_id,
                        "amount": float(payment.amount),
                        "payment_method": payment.payment_method,
                        "paid_at": payment.paid_at.isoformat() + "Z",
                        "paid_by": payment.paid_by_user.username if payment.paid_by_user else "Unknown",
                        "balance_before": float(payment.balance_before),
                        "balance_after": float(payment.balance_after),
                        "funding_source": payment.funding_source or "legacy",
                        "method_balance_before": float(payment.method_balance_before) if payment.method_balance_before is not None else None,
                        "method_balance_after": float(payment.method_balance_after) if payment.method_balance_after is not None else None,
                    }
                    for payment in sorted(p.payments, key=lambda entry: (entry.paid_at, entry.id))
                ],
                "legacy_paid_unattributed": float(max(
                    p.partial_paid - sum((payment.amount for payment in p.payments), Decimal("0")),
                    Decimal("0"),
                )),
            }
            for p in payables
        ]

    def create(
        self,
        creditor_name: str,
        items_description: str,
        amount_owed: float,
        due_date: str,
        incurred_date: str,
        created_by: int,
    ) -> dict[str, Any]:
        due = date.fromisoformat(due_date)
        incurred = date.fromisoformat(incurred_date) if incurred_date else date.today()
        amount_decimal = Decimal(str(amount_owed))
        payable = self.repo.create(
            creditor_name=creditor_name,
            items_description=items_description,
            amount_owed=amount_decimal,
            due_date=due,
            incurred_date=incurred,
            created_by=created_by,
        )
        self.repo.save()
        return {"success": True, "data": {"id": payable.id}}

    def mark_paid(self, payable_id: int, amount: Any, payment_method: str, paid_by: int, request_key: str | None = None) -> dict[str, Any] | tuple[dict[str, Any], int]:
        if not isinstance(payment_method, str) or payment_method not in VALID_PAYMENT_METHODS:
            return {"error": "Invalid payment method"}, 400
        if request_key and len(request_key) > 200:
            return {"error": "Invalid request key."}, 400
        try:
            payment_amount = None if amount is None else Decimal(str(amount))
            if payment_amount is not None and (
                not payment_amount.is_finite() or payment_amount > Decimal("99999999.99")
                or payment_amount.as_tuple().exponent < -2
            ):
                raise ValueError
        except (InvalidOperation, ValueError, TypeError):
            return {"error": "Enter a valid payment amount with up to two decimal places."}, 400

        def replay(payment):
            if (payment.payable_id != payable_id or payment.paid_by != paid_by
                    or payment.payment_method != payment_method
                    or (payment_amount is None and payment.balance_after != 0)
                    or (payment_amount is not None and payment.amount != payment_amount)):
                return {"error": "This request key belongs to a different payment."}, 409
            return {"success": True, "payment_id": payment.id,
                    "funding_source": payment.funding_source or "legacy", "replayed": True}

        day = manila_date(datetime.utcnow())
        try:
            with SalesRepository.method_lock(day, payment_method):
                paid_at = datetime.utcnow()
                if manila_date(paid_at) != day:
                    return {"error": "The business day changed. Please retry."}, 409
                if request_key:
                    existing = self.repo.get_payment_by_request_key(request_key)
                    if existing:
                        return replay(existing)
                payable = self.repo.get_for_update(payable_id)
                if not payable:
                    return {"error": "Payable not found"}, 404
                debt_before = payable.amount_owed - payable.partial_paid
                paid = debt_before if payment_amount is None else payment_amount
                if debt_before <= 0 or paid <= 0 or paid > debt_before:
                    return {"error": f"Payment must be between ₱0.01 and ₱{debt_before:.2f}."}, 400
                sales = SalesRepository()
                daily = sales.daily_ledger(day, day).get(day)
                before = sales.method_balance(daily, payment_method)
                source = "business" if payment_method == "cash" or before >= paid else "external"
                after = before - paid if source == "business" else before
                payment = self.repo.record_payment(
                    payable, paid, payment_method, paid_by, request_key, paid_at,
                    source, before, after,
                )
                self.repo.save()
        except IntegrityError:
            db.session.rollback()
            if request_key:
                existing = self.repo.get_payment_by_request_key(request_key)
                if existing:
                    return replay(existing)
            raise
        except TimeoutError as exc:
            return {"error": str(exc)}, 503
        return {"success": True, "payment_id": payment.id, "funding_source": source}

    def get_due_count(self) -> int:
        today = date.today()
        three_days_later = today + timedelta(days=3)
        count = Payable.query.filter(
            Payable.status != "Paid",
            Payable.due_date <= three_days_later
        ).count()
        return count
