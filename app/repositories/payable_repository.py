from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import selectinload

from app import db
from app.models.payable import Payable, PayablePayment


class PayableRepository:
    def get(self, payable_id: int) -> Optional[Payable]:
        return Payable.query.filter_by(id=payable_id).first()

    def get_for_update(self, payable_id: int) -> Optional[Payable]:
        return Payable.query.filter_by(id=payable_id).with_for_update().first()

    def list_all(self) -> list[Payable]:
        return (
            Payable.query.options(selectinload(Payable.payments).selectinload(PayablePayment.paid_by_user))
            .order_by(Payable.incurred_date.desc(), Payable.id.desc())
            .all()
        )

    def create(
        self,
        creditor_name: str,
        items_description: str,
        amount_owed: Decimal,
        due_date: date,
        incurred_date: date,
        created_by: int,
    ) -> Payable:
        payable = Payable(
            creditor_name=creditor_name,
            items_description=items_description,
            amount_owed=amount_owed,
            due_date=due_date,
            incurred_date=incurred_date,
            created_by=created_by,
            status="Unpaid",
            partial_paid=0.00
        )
        db.session.add(payable)
        db.session.flush()
        return payable

    def mark_paid(self, payable_id: int, amount: Decimal | None, payment_method: str, paid_by: int, request_key: str | None = None) -> PayablePayment | None:
        payable = self.get_for_update(payable_id)
        if not payable:
            return None
        if request_key and PayablePayment.query.filter_by(request_key=request_key).first():
            raise ValueError("This payment was already recorded.")
        before = payable.amount_owed - payable.partial_paid
        paid = before if amount is None else amount
        if before <= 0 or paid <= 0 or paid > before:
            raise ValueError(f"Payment must be between ₱0.01 and ₱{before:.2f}.")
        payable.partial_paid += paid
        payable.status = "Paid" if payable.partial_paid == payable.amount_owed else "Partially Paid"
        payment = PayablePayment(
            payable_id=payable.id, amount=paid, payment_method=payment_method,
            paid_by=paid_by, balance_before=before, balance_after=before - paid,
            request_key=request_key,
        )
        db.session.add(payment)
        return payment

    def save(self) -> None:
        db.session.commit()
