from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from app import db
from app.models.payable import Payable


class PayableRepository:
    def get(self, payable_id: int) -> Optional[Payable]:
        return Payable.query.filter_by(id=payable_id).first()

    def get_for_update(self, payable_id: int) -> Optional[Payable]:
        return Payable.query.filter_by(id=payable_id).with_for_update().first()

    def list_all(self) -> list[Payable]:
        return Payable.query.order_by(Payable.incurred_date.desc(), Payable.id.desc()).all()

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

    def mark_paid(self, payable_id: int, amount: Optional[float] = None) -> bool:
        payable = self.get_for_update(payable_id)
        if not payable:
            return False
        
        from decimal import Decimal
        if amount is None:
            payable.partial_paid = payable.amount_owed
            payable.status = "Paid"
        else:
            payment_decimal = Decimal(str(amount))
            new_partial = payable.partial_paid + payment_decimal
            
            if new_partial >= payable.amount_owed:
                payable.partial_paid = payable.amount_owed
                payable.status = "Paid"
            else:
                payable.partial_paid = new_partial
                if new_partial > 0:
                    payable.status = "Partially Paid"
                else:
                    payable.status = "Unpaid"
        return True

    def save(self) -> None:
        db.session.commit()
