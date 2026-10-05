from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal
from typing import Optional
from uuid import uuid4

from sqlalchemy import func, or_, and_, case
from sqlalchemy.orm import selectinload

from app import db
from app.models.receivable import Receivable, ReceivablePayment, ReceivableTab
from app.utils.dates import manila_date, manila_day_bounds


class ReceivableTabConflict(ValueError):
    pass


class ReceivableRepository:
    def suggest_customers(self, search: str, limit: int = 15) -> list[dict]:
        name, contact, _ = ReceivableTab.identity(search, search)
        latest_id = func.max(ReceivableTab.id)
        open_id = func.max(case((ReceivableTab.closed_at.is_(None), ReceivableTab.id)))
        identities = (db.session.query(
            ReceivableTab.normalized_name, ReceivableTab.normalized_contact,
            latest_id.label("latest_id"), open_id.label("open_id"),
        ).filter(or_(ReceivableTab.normalized_name.contains(name, autoescape=True),
                     ReceivableTab.normalized_contact.contains(contact, autoescape=True)))
            .group_by(ReceivableTab.normalized_name, ReceivableTab.normalized_contact)
            .order_by(case((ReceivableTab.normalized_name == name, 0),
                           (ReceivableTab.normalized_contact == contact, 1), else_=2),
                      latest_id.desc()).limit(limit).all())
        ids = {tab_id for row in identities for tab_id in (row.latest_id, row.open_id) if tab_id}
        tabs = {tab.id: tab for tab in ReceivableTab.query.filter(ReceivableTab.id.in_(ids)).all()} if ids else {}
        blank_names = [row.normalized_name for row in identities if not row.normalized_contact and row.open_id]
        blank_open = (ReceivableTab.query.filter(ReceivableTab.normalized_name.in_(blank_names),
                                               ReceivableTab.normalized_contact == "",
                                               ReceivableTab.closed_at.is_(None))
                      .order_by(ReceivableTab.id.desc()).limit(limit).all()) if blank_names else []

        matches = []
        seen = set()
        def add(tab, open_tab_id=None, *, legacy=False):
            identity = ReceivableTab.identity(tab.customer_name, tab.customer_contact)[:2]
            key = (identity, open_tab_id if not identity[1] else None)
            if key in seen:
                return
            seen.add(key)
            matches.append({"customer_name": tab.customer_name,
                            "customer_contact": tab.customer_contact or "",
                            "open_tab_id": open_tab_id,
                            "label": f"Open tab #{open_tab_id}" if open_tab_id else
                                     ("Customer record—new tab" if legacy else "Past customer—new tab"),
                            "_score": 0 if identity[0] == name else 1 if identity[1] == contact else 2,
                            "_seen_at": getattr(tab, "opened_at", None) or getattr(tab, "created_at", None) or datetime.min})

        tab_identities = {(row.normalized_name, row.normalized_contact) for row in identities}
        for row in identities:
            if not row.normalized_contact and row.open_id:
                for tab in blank_open:
                    if tab.normalized_name == row.normalized_name:
                        add(tab, tab.id)
            else:
                add(tabs[row.open_id or row.latest_id], row.open_id)

        # ponytail: legacy rows are normally backfilled; index normalized fields if this scan grows.
        legacy_rows = Receivable.query.filter(Receivable.tab_id.is_(None)).order_by(Receivable.id.desc()).all()
        for row in legacy_rows:
            row_name, row_contact, _ = ReceivableTab.identity(row.customer_name, row.customer_contact)
            if (row_name, row_contact) not in tab_identities and (name in row_name or contact in row_contact):
                add(row, legacy=True)
        matches.sort(key=lambda row: row["_seen_at"], reverse=True)
        matches.sort(key=lambda row: row["_score"])
        return [{key: value for key, value in row.items() if not key.startswith("_")}
                for row in matches[:limit]]

    @staticmethod
    def _search_filter(search: str, *, tabs: bool = False):
        fields = [Receivable.customer_name, Receivable.customer_contact, Receivable.items_description]
        if tabs:
            fields.extend([ReceivableTab.normalized_name, ReceivableTab.normalized_contact])
        terms = []
        for term in search.split():
            pattern = "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            terms.append(or_(*(field.ilike(pattern, escape="\\") for field in fields)))
        return and_(*terms)

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
        incurred_date: date | None = None,
    ):
        query = Receivable.query.options(selectinload(Receivable.created_by_user))
        if incurred_date:
            start, end = manila_day_bounds(incurred_date)
            query = query.filter(or_(Receivable.incurred_date == incurred_date,
                                     (Receivable.incurred_date.is_(None)) &
                                     (Receivable.created_at >= start) & (Receivable.created_at < end)))
        if status == "paid":
            query = query.filter(Receivable.paid.is_(True))
        elif status == "unpaid":
            query = query.filter(Receivable.paid.is_(False))
        if search:
            query = query.filter(self._search_filter(search))
        return query.order_by(
            Receivable.incurred_date.desc(), Receivable.id.desc()
        ).paginate(page=page, per_page=per_page, error_out=False)

    def totals(self, incurred_date: date | None = None) -> dict:
        due_amount = case((Receivable.paid.is_(False), Receivable.amount_owed - Receivable.partial_paid), else_=0)
        all_due = db.session.query(func.coalesce(func.sum(due_amount), 0)).scalar()
        query = Receivable.query
        if incurred_date:
            start, end = manila_day_bounds(incurred_date)
            query = query.filter(or_(Receivable.incurred_date == incurred_date,
                                     (Receivable.incurred_date.is_(None)) &
                                     (Receivable.created_at >= start) & (Receivable.created_at < end)))
        selected = query.with_entities(
            func.coalesce(func.sum(Receivable.amount_owed), 0),
            func.coalesce(func.sum(due_amount), 0),
        ).first()
        return {"all_outstanding": float(all_due), "selected_taken": float(selected[0]),
                "selected_outstanding": float(selected[1])}

    def list_tabs(self, incurred_date: date | None = None, search: str = "", page: int = 1, per_page: int = 50):
        candidates = db.session.query(Receivable.tab_id).join(ReceivableTab, ReceivableTab.id == Receivable.tab_id)
        if incurred_date:
            start, end = manila_day_bounds(incurred_date)
            candidates = candidates.filter(or_(Receivable.incurred_date == incurred_date,
                                               (Receivable.incurred_date.is_(None)) &
                                               (Receivable.created_at >= start) & (Receivable.created_at < end)))
        if search:
            candidates = candidates.filter(self._search_filter(search, tabs=True))
        query = ReceivableTab.query.filter(ReceivableTab.closed_at.is_(None),
                                          ReceivableTab.id.in_(candidates.distinct()))
        page_result = query.order_by(ReceivableTab.id.desc()).paginate(page=page, per_page=per_page, error_out=False)
        ids = [tab.id for tab in page_result.items]
        aggregate = {}
        if ids:
            if incurred_date:
                start, end = manila_day_bounds(incurred_date)
                matches_date = or_(Receivable.incurred_date == incurred_date,
                                   (Receivable.incurred_date.is_(None)) &
                                   (Receivable.created_at >= start) & (Receivable.created_at < end))
                dated = case((matches_date, Receivable.amount_owed), else_=0)
            else:
                dated = Receivable.amount_owed
            for row in db.session.query(
                Receivable.tab_id,
                func.sum(Receivable.amount_owed),
                func.sum(Receivable.partial_paid),
                func.sum(Receivable.amount_owed - Receivable.partial_paid),
                func.sum(dated),
                func.min(case((Receivable.paid.is_(False), Receivable.due_date), else_=None)),
            ).filter(Receivable.tab_id.in_(ids)).group_by(Receivable.tab_id):
                aggregate[row[0]] = row[1:]
        rows = []
        for tab in page_result.items:
            owed, paid, balance, date_taken, soonest = aggregate[tab.id]
            rows.append({"id": tab.id, "customer_name": tab.customer_name,
                         "customer_contact": tab.customer_contact or "",
                         "orders_total": float(owed), "paid_total": float(paid),
                         "outstanding_balance": float(balance), "date_taken_amount": float(date_taken or 0),
                         "soonest_due_date": soonest.isoformat() if soonest else None})
        return rows, page_result

    def tab_records(self, tab_id: int) -> list[Receivable]:
        return (Receivable.query.options(selectinload(Receivable.created_by_user))
                .filter_by(tab_id=tab_id).order_by(Receivable.incurred_date, Receivable.id).all())

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
        tab_id: Optional[int] = None,
    ) -> Receivable:
        normalized_name, normalized_contact, active_key = ReceivableTab.identity(customer_name, customer_contact)
        if tab_id is not None:
            tab = ReceivableTab.query.filter_by(id=tab_id).with_for_update().first()
            if not tab or tab.closed_at is not None:
                raise ReceivableTabConflict("This customer tab is closed. Refresh and choose an open tab.")
            if (tab.normalized_name, tab.normalized_contact) != (normalized_name, normalized_contact):
                raise ValueError("The selected customer tab does not match the name and contact.")
        else:
            tab = ReceivableTab.query.filter_by(active_key=active_key).with_for_update().first() if active_key else None
            if tab is None:
                tab = ReceivableTab(customer_name=customer_name, customer_contact=customer_contact,
                                    normalized_name=normalized_name, normalized_contact=normalized_contact,
                                    active_key=active_key)
                db.session.add(tab)
                db.session.flush()
        receivable = Receivable(
            customer_name=customer_name,
            customer_contact=customer_contact,
            items_description=items_description,
            amount_owed=amount_owed,
            due_date=due_date,
            created_by=created_by,
            session_id=session_id,
            approved_by_staff=approved_by_staff,
            incurred_date=incurred_date or manila_date(datetime.utcnow()),
            notes=notes,
            tab_id=tab.id,
        )
        db.session.add(receivable)
        db.session.flush()
        return receivable

    def record_payment(self, receivable_id: int, amount: Decimal | None, received_by: int, payment_method: str, request_key: str | None = None, received_at: datetime | None = None) -> bool:
        found = self.get(receivable_id)
        tab = (ReceivableTab.query.filter_by(id=found.tab_id).with_for_update().first()
               if found and found.tab_id else None)
        receivable = self.get_for_update(receivable_id)
        if not receivable:
            return False
        if request_key and ReceivablePayment.query.filter_by(request_key=request_key).first():
            raise ValueError("This payment was already recorded.")
        remaining = receivable.amount_owed - receivable.partial_paid
        if receivable.paid or remaining <= 0:
            raise ValueError("This debt has already been paid.")
        collected = remaining if amount is None else amount
        if collected <= 0 or collected > remaining:
            raise ValueError(f"Payment must be between ₱0.01 and ₱{remaining:.2f}.")
        receivable.partial_paid += collected
        receivable.paid = receivable.partial_paid >= receivable.amount_owed
        received_at = received_at or datetime.utcnow()
        if receivable.paid:
            receivable.paid_at = received_at
        db.session.add(ReceivablePayment(
            receivable_id=receivable.id, amount=collected,
            payment_method=payment_method, received_by=received_by,
            balance_before=remaining, balance_after=remaining - collected,
            request_key=request_key, received_at=received_at,
        ))
        if tab and not Receivable.query.filter(Receivable.tab_id == tab.id,
                                              Receivable.paid.is_(False)).first():
            tab.closed_at = received_at
            tab.active_key = None
        return True

    def record_tab_payment(self, tab_id: int, amount: Decimal, received_by: int,
                           payment_method: str, request_key: str | None = None,
                           received_at: datetime | None = None) -> Decimal:
        tab = ReceivableTab.query.filter_by(id=tab_id).with_for_update().first()
        if not tab or tab.closed_at is not None:
            raise ValueError("This customer tab is closed. Refresh before recording a payment.")
        unpaid = Receivable.query.filter(Receivable.tab_id == tab_id, Receivable.paid.is_(False)).with_for_update().all()
        remaining = self._allocate_payment(unpaid, amount, received_by, payment_method, request_key, received_at)
        if remaining == 0:
            tab.closed_at = received_at or datetime.utcnow()
            tab.active_key = None
        return remaining

    def record_customer_payment(self, customer_name: str, amount: Decimal, received_by: int, payment_method: str, customer_contact: str = "", request_key: str | None = None, received_at: datetime | None = None) -> Decimal:
        # Compatibility for existing callers. New UI sends the tab ID.
        name, contact, key = ReceivableTab.identity(customer_name, customer_contact)
        tabs = ReceivableTab.query.filter_by(normalized_name=name, normalized_contact=contact, closed_at=None).all()
        if len(tabs) > 1:
            raise ValueError("Multiple open tabs match; choose the customer tab explicitly.")
        if tabs:
            return self.record_tab_payment(tabs[0].id, amount, received_by, payment_method, request_key, received_at)
        unpaid = Receivable.query.filter(
            Receivable.tab_id.is_(None),
            Receivable.paid.is_(False),
            func.lower(func.trim(Receivable.customer_name)) == customer_name.strip().lower(),
            func.trim(func.coalesce(Receivable.customer_contact, "")) == customer_contact.strip(),
        ).with_for_update().all()
        return self._allocate_payment(unpaid, amount, received_by, payment_method, request_key, received_at)

    def _allocate_payment(self, unpaid, amount, received_by, payment_method, request_key, received_at):
        if request_key and ReceivablePayment.query.filter_by(request_key=request_key).first():
            raise ValueError("This payment was already recorded.")
        unpaid.sort(key=lambda r: (r.incurred_date or (manila_date(r.created_at) if r.created_at else date.min), r.id))
        total_remaining = sum((max(r.amount_owed - r.partial_paid, Decimal("0")) for r in unpaid), Decimal("0"))
        if total_remaining <= 0:
            raise ValueError("This customer has no outstanding balance.")
        if amount <= 0 or amount > total_remaining:
            raise ValueError(f"Payment must be between ₱0.01 and ₱{total_remaining:.2f}.")

        unallocated = amount
        now = received_at or datetime.utcnow()
        payment_group_id = uuid4().hex
        for receivable in unpaid:
            if unallocated <= 0:
                break
            applied = min(unallocated, receivable.amount_owed - receivable.partial_paid)
            if applied <= 0:
                continue
            balance_before = receivable.amount_owed - receivable.partial_paid
            receivable.partial_paid += applied
            receivable.paid = receivable.partial_paid >= receivable.amount_owed
            if receivable.paid:
                receivable.paid_at = now
            db.session.add(ReceivablePayment(
                receivable_id=receivable.id, amount=applied,
                payment_method=payment_method, received_by=received_by,
                received_at=now, payment_group_id=payment_group_id,
                balance_before=balance_before, balance_after=balance_before - applied,
                request_key=request_key,
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

    def list_tab_payments(self, tab_id: int) -> list[ReceivablePayment]:
        return (ReceivablePayment.query.join(Receivable)
                .options(selectinload(ReceivablePayment.received_by_user))
                .filter(Receivable.tab_id == tab_id)
                .order_by(ReceivablePayment.received_at.desc(), ReceivablePayment.id.desc()).all())

    def update_notes(self, receivable_id: int, notes: str) -> bool:
        receivable = self.get(receivable_id)
        if not receivable:
            return False
        receivable.notes = notes
        return True

    def save(self) -> None:
        db.session.commit()
