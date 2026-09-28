from __future__ import annotations

from datetime import date, datetime
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

    def get_payment_by_request_key(self, request_key: str) -> Optional[PayablePayment]:
        return PayablePayment.query.filter_by(request_key=request_key).first()

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

    def record_payment(self, payable: Payable, paid: Decimal, payment_method: str, paid_by: int,
                       request_key: str | None, paid_at: datetime, funding_source: str,
                       method_balance_before: Decimal, method_balance_after: Decimal) -> PayablePayment:
        before = payable.amount_owed - payable.partial_paid
        payable.partial_paid += paid
        payable.status = "Paid" if payable.partial_paid == payable.amount_owed else "Partially Paid"
        payment = PayablePayment(
            payable_id=payable.id, amount=paid, payment_method=payment_method,
            paid_by=paid_by, balance_before=before, balance_after=before - paid,
            request_key=request_key, paid_at=paid_at, funding_source=funding_source,
            method_balance_before=method_balance_before, method_balance_after=method_balance_after,
        )
        db.session.add(payment)
        return payment

    def save(self) -> None:
        db.session.commit()
