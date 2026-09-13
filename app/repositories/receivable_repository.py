from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import selectinload

from app import db
from app.models.receivable import Receivable


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
        )
        db.session.add(receivable)
        db.session.flush()
        return receivable

    def mark_paid(self, receivable_id: int) -> bool:
        receivable = self.get_for_update(receivable_id)
        if not receivable:
            return False
        receivable.paid = True
        from datetime import datetime
        receivable.paid_at = datetime.utcnow()
        return True

    def mark_customer_paid(self, customer_name: str) -> bool:
        stripped_name = customer_name.strip()
        unpaid = Receivable.query.filter(
            Receivable.paid == False
        ).with_for_update().all()
        matched_count = 0
        from datetime import datetime
        now = datetime.utcnow()
        for r in unpaid:
            if r.customer_name.strip().lower() == stripped_name.lower():
                r.paid = True
                r.paid_at = now
                matched_count += 1
        return matched_count > 0

    def mark_partial_paid(self, receivable_id: int, amount: float) -> bool:
        receivable = self.get(receivable_id)
        if not receivable:
            return False
        receivable.partial_paid = amount
        return True

    def save(self) -> None:
        db.session.commit()
