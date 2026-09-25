from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal
from typing import Optional
from uuid import uuid4

from sqlalchemy import func, or_
from sqlalchemy.orm import selectinload

from app import db
from app.models.receivable import Receivable, ReceivablePayment


class ReceivableRepository:
    def get(self, receivable_id: int) -> Optional[Receivable]:
        return Receivable.query.filter_by(id=receivable_id).first()

    def get_for_update(self, receivable_id: int) -> Optional[Receivable]:
        return Receivable.query.filter_by(id=receivable_id).with_for_update().first()

    def list_all(self) -> list[Receivable]:
        return (
            Receivable.query.options(selectinload(Receivable.created_by_user))
            .order_by(Receivable.incurred_date.desc(), Receivable.id.desc())
            .all()
        )

    def list_paginated(
        self,
        page: int,
        per_page: int,
        status: str | None = None,
        search: str | None = None,
    ):
        query = Receivable.query.options(selectinload(Receivable.created_by_user))
        if status == "paid":
            query = query.filter(Receivable.paid.is_(True))
        elif status == "unpaid":
            query = query.filter(Receivable.paid.is_(False))
        if search:
            pattern = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    Receivable.customer_name.ilike(pattern),
                    Receivable.customer_contact.ilike(pattern),
                    Receivable.items_description.ilike(pattern),
                )
            )
        return query.order_by(
            Receivable.incurred_date.desc(), Receivable.id.desc()
        ).paginate(page=page, per_page=per_page, error_out=False)

    def list_unpaid(self) -> list[Receivable]:
        return Receivable.query.filter(
            Receivable.paid == False,
            Receivable.due_date <= date.today(),
        ).order_by(Receivable.due_date).all()

    def list_due_today(self) -> list[Receivable]:
        return Receivable.query.filter(
            Receivable.due_date == date.today(),
            Receivable.paid == False,
        ).all()

    def create(
        self,
        customer_name: str,
        customer_contact: str,
        items_description: str,
        amount_owed: Decimal,
        due_date: date,
        created_by: int,
        session_id: Optional[int],
        approved_by_staff: Optional[str] = None,
        incurred_date: Optional[date] = None,
        notes: Optional[str] = None,
    ) -> Receivable:
        receivable = Receivable(
            customer_name=customer_name,
            customer_contact=customer_contact,
            items_description=items_description,
            amount_owed=amount_owed,
            due_date=due_date,
            created_by=created_by,
            session_id=session_id,
            approved_by_staff=approved_by_staff,
            incurred_date=incurred_date or date.today(),
            notes=notes,
        )
        db.session.add(receivable)
        db.session.flush()
        return receivable

    def record_payment(self, receivable_id: int, amount: Decimal | None, received_by: int, payment_method: str) -> bool:
        receivable = self.get_for_update(receivable_id)
        if not receivable:
            return False
        remaining = receivable.amount_owed - receivable.partial_paid
        if receivable.paid or remaining <= 0:
            raise ValueError("This debt has already been paid.")
        collected = remaining if amount is None else amount
        if collected <= 0 or collected > remaining:
            raise ValueError(f"Payment must be between ₱0.01 and ₱{remaining:.2f}.")
        receivable.partial_paid += collected
        receivable.paid = receivable.partial_paid >= receivable.amount_owed
        if receivable.paid:
            receivable.paid_at = datetime.utcnow()
        db.session.add(ReceivablePayment(
            receivable_id=receivable.id, amount=collected,
            payment_method=payment_method, received_by=received_by,
        ))
        return True

    def record_customer_payment(self, customer_name: str, amount: Decimal, received_by: int, payment_method: str, customer_contact: str = "") -> Decimal:
        # Lock the customer's open orders, then apply one tab payment in a
        # stable order. The allocation is bookkeeping; the customer pays one total.
        unpaid = Receivable.query.filter(
            Receivable.paid.is_(False),
            func.lower(func.trim(Receivable.customer_name)) == customer_name.strip().lower(),
            func.trim(func.coalesce(Receivable.customer_contact, "")) == customer_contact.strip(),
        ).with_for_update().all()
        unpaid.sort(key=lambda r: (r.incurred_date or (r.created_at.date() if r.created_at else date.min), r.id))
        total_remaining = sum((max(r.amount_owed - r.partial_paid, Decimal("0")) for r in unpaid), Decimal("0"))
        if total_remaining <= 0:
            raise ValueError("This customer has no outstanding balance.")
        if amount <= 0 or amount > total_remaining:
            raise ValueError(f"Payment must be between ₱0.01 and ₱{total_remaining:.2f}.")

        unallocated = amount
        now = datetime.utcnow()
        payment_group_id = uuid4().hex
        for receivable in unpaid:
            if unallocated <= 0:
                break
            applied = min(unallocated, receivable.amount_owed - receivable.partial_paid)
            if applied <= 0:
                continue
            receivable.partial_paid += applied
            receivable.paid = receivable.partial_paid >= receivable.amount_owed
            if receivable.paid:
                receivable.paid_at = now
            db.session.add(ReceivablePayment(
                receivable_id=receivable.id, amount=applied,
                payment_method=payment_method, received_by=received_by,
                received_at=now, payment_group_id=payment_group_id,
            ))
            unallocated -= applied
        return total_remaining - amount

    def list_customer_payments(self, customer_name: str, customer_contact: str = "") -> list[ReceivablePayment]:
        return (
            ReceivablePayment.query.join(Receivable)
            .options(selectinload(ReceivablePayment.received_by_user))
            .filter(
                func.lower(func.trim(Receivable.customer_name)) == customer_name.strip().lower(),
                func.trim(func.coalesce(Receivable.customer_contact, "")) == customer_contact.strip(),
            )
            .order_by(ReceivablePayment.received_at.desc(), ReceivablePayment.id.desc())
            .all()
        )

    def update_notes(self, receivable_id: int, notes: str) -> bool:
        receivable = self.get(receivable_id)
        if not receivable:
            return False
        receivable.notes = notes
        return True

    def save(self) -> None:
        db.session.commit()
