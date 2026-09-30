from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from app.repositories.receivable_repository import ReceivableRepository
from app import db
from app.models.receivable import ReceivableTab
from sqlalchemy.exc import IntegrityError
from app.repositories.sales_repository import SalesRepository
from app.utils.dates import manila_date
from app.utils.payment import VALID_PAYMENT_METHODS


@dataclass(frozen=True)
class ReceivableService:
    repo: ReceivableRepository

    @staticmethod
    def _serialize(receivables) -> list[dict[str, Any]]:
        return [
            {
                "id": r.id,
                "tab_id": r.tab_id,
                "customer_name": r.customer_name,
                "customer_contact": r.customer_contact,
                "items": r.items_description,
                "notes": r.notes or "",
                "amount_owed": float(r.amount_owed),
                "partial_paid": float(r.partial_paid),
                "due_date": r.due_date.strftime("%Y-%m-%d"),
                "incurred_date": (r.incurred_date or manila_date(r.created_at)).strftime("%Y-%m-%d") if (r.incurred_date or r.created_at) else "",
                "paid": r.paid,
                "created_by": r.created_by_user.username if r.created_by_user else "Unknown",
                "approved_by_staff": r.approved_by_staff or "",
            }
            for r in receivables
        ]

    def list_all(self) -> list[dict[str, Any]]:
        return self._serialize(self.repo.list_all())

    def list_paginated(
        self,
        page: int,
        per_page: int,
        status: str | None = None,
        search: str | None = None,
        incurred_date: date | None = None,
    ) -> dict[str, Any]:
        pagination = self.repo.list_paginated(page, per_page, status, search, incurred_date)
        return {
            "data": self._serialize(pagination.items),
            "pagination": {
                "page": pagination.page,
                "per_page": pagination.per_page,
                "pages": pagination.pages,
                "total": pagination.total,
                "has_next": pagination.has_next,
                "has_prev": pagination.has_prev,
            },
        }

    def totals(self, incurred_date: date | None = None) -> dict:
        return self.repo.totals(incurred_date)

    @staticmethod
    def parse_filters(args) -> tuple[int, int, str | None, str, date | None]:
        try:
            page, per_page = int(args.get("page", "1")), int(args.get("per_page", "50"))
            if page < 1 or not 1 <= per_page <= 100:
                raise ValueError
        except (TypeError, ValueError):
            raise ValueError("Page must be positive and per_page must be between 1 and 100.")
        status = args.get("status") or None
        if status not in (None, "paid", "unpaid"):
            raise ValueError("Invalid receivable status.")
        search = (args.get("search") or "").strip()
        if len(search) > 100:
            raise ValueError("Search must be 100 characters or fewer.")
        raw_date = args.get("date") or None
        try:
            chosen = date.fromisoformat(raw_date) if raw_date else None
            if raw_date and chosen.isoformat() != raw_date:
                raise ValueError
        except ValueError:
            raise ValueError("Date Taken must be YYYY-MM-DD.")
        return page, per_page, status, search, chosen

    def tabs(self, chosen: date | None, search: str, page: int = 1, per_page: int = 50) -> dict:
        rows, pagination = self.repo.list_tabs(chosen, search, page, per_page)
        return {"data": rows, "pagination": {"page": pagination.page, "pages": pagination.pages,
                "total": pagination.total, "has_next": pagination.has_next, "has_prev": pagination.has_prev}}

    def tab_detail(self, tab_id: int) -> dict | None:
        tab = db.session.get(ReceivableTab, tab_id)
        if not tab:
            return None
        records = self._serialize(self.repo.tab_records(tab_id))
        return {"id": tab.id, "customer_name": tab.customer_name,
                "customer_contact": tab.customer_contact or "", "open": tab.closed_at is None,
                "records": records, "orders_total": sum(row["amount_owed"] for row in records),
                "paid_total": sum(row["partial_paid"] for row in records),
                "outstanding_balance": sum(row["amount_owed"] - row["partial_paid"] for row in records)}

    def list_unpaid(self) -> list[dict[str, Any]]:
        receivables = self.repo.list_unpaid()
        return [
            {
                "id": r.id,
                "customer_name": r.customer_name,
                "amount_owed": float(r.amount_owed),
                "partial_paid": float(r.partial_paid),
                "due_date": r.due_date.strftime("%Y-%m-%d"),
            }
            for r in receivables
        ]

    def create(
        self,
        customer_name: str,
        customer_contact: str,
        items_description: str,
        amount_owed: float,
        due_date: str,
        created_by: int,
        session_id: Optional[int],
        approved_by_staff: Optional[str] = None,
        incurred_date: Optional[str] = None,
        notes: Optional[str] = None,
        tab_id: Optional[int] = None,
    ) -> dict[str, Any]:
        if not isinstance(customer_name, str) or not customer_name.strip() or len(customer_name.strip()) > 100:
            raise ValueError("Enter a customer name up to 100 characters.")
        if customer_contact is None:
            customer_contact = ""
        if not isinstance(customer_contact, str) or len(customer_contact.strip()) > 100:
            raise ValueError("Contact must be text up to 100 characters.")
        if not isinstance(items_description, str) or not items_description.strip():
            raise ValueError("Items description is required.")
        if tab_id is not None and (isinstance(tab_id, bool) or not str(tab_id).isdigit()):
            raise ValueError("Choose a valid customer tab.")
        try:
            due = date.fromisoformat(due_date)
            incurred = date.fromisoformat(incurred_date) if incurred_date else None
        except (TypeError, ValueError):
            raise ValueError("Enter valid Date Taken and Due Date values.")
        amount_decimal = Decimal(str(amount_owed))
        if not amount_decimal.is_finite() or amount_decimal <= 0 or amount_decimal.as_tuple().exponent < -2:
            raise ValueError("Enter a positive amount with up to two decimal places.")
        if notes is not None and (not isinstance(notes, str) or len(notes) > 2000):
            raise ValueError("Notes must be text up to 2,000 characters.")
        if approved_by_staff is not None and (not isinstance(approved_by_staff, str) or len(approved_by_staff) > 100):
            raise ValueError("Approved by staff must be text up to 100 characters.")
        clean_notes = notes.strip() if notes else ""
        if session_id not in (None, ""):
            from app.models import CustomerSession
            if isinstance(session_id, bool) or not str(session_id).isdigit():
                raise ValueError("Choose a valid customer session.")
            linked = CustomerSession.query.filter_by(id=int(session_id)).with_for_update().first()
            if not linked or linked.status == "cancelled":
                raise ValueError("This customer session cannot receive a debt record.")
            session_id = linked.id
        for attempt in range(2):
            try:
                receivable = self.repo.create(
                    customer_name.strip(), customer_contact.strip(), items_description.strip(), amount_decimal,
                    due, created_by, session_id, approved_by_staff, incurred, clean_notes,
                    int(tab_id) if tab_id is not None else None,
                )
                self.repo.save()
                return {"success": True, "data": {"id": receivable.id, "tab_id": receivable.tab_id}}
            except IntegrityError:
                db.session.rollback()
                if attempt or tab_id is not None:
                    raise ValueError("The customer tab changed. Refresh and try again.")
        raise ValueError("Could not create customer tab.")

    def mark_paid(self, receivable_id: int, amount: Any, received_by: int, payment_method: str, request_key: str | None = None) -> dict[str, Any] | tuple[dict[str, Any], int]:
        if not isinstance(payment_method, str) or payment_method not in VALID_PAYMENT_METHODS:
            return {"error": "Invalid payment method"}, 400
        try:
            payment = None if amount is None else Decimal(str(amount))
            if payment is not None and (not payment.is_finite() or payment.as_tuple().exponent < -2):
                raise ValueError
        except (InvalidOperation, ValueError, TypeError):
            return {"error": "Enter a valid payment amount with up to two decimal places."}, 400
        day = manila_date(datetime.utcnow())
        try:
            with SalesRepository.method_lock(day, payment_method):
                received_at = datetime.utcnow()
                if manila_date(received_at) != day:
                    return {"error": "The business day changed. Please retry."}, 409
                success = self.repo.record_payment(
                    receivable_id, payment, received_by, payment_method, request_key,
                    received_at=received_at,
                )
                if success:
                    self.repo.save()
        except ValueError as exc:
            return {"error": str(exc)}, 400
        except TimeoutError as exc:
            return {"error": str(exc)}, 503
        if not success:
            return {"error": "Receivable not found"}, 404
        from app.core.socketio_handlers import emit_receivable_marked_paid

        emit_receivable_marked_paid(receivable_id)
        return {"success": True}

    def record_customer_payment(self, customer_name: str, amount: Any, received_by: int, payment_method: str, customer_contact: str = "", request_key: str | None = None, tab_id: int | None = None) -> dict[str, Any] | tuple[dict[str, Any], int]:
        if not isinstance(payment_method, str) or payment_method not in VALID_PAYMENT_METHODS:
            return {"error": "Invalid payment method"}, 400
        if tab_id is None and (not isinstance(customer_name, str) or not customer_name.strip()):
            return {"error": "Customer name is required"}, 400
        if not isinstance(customer_contact, str):
            return {"error": "Customer contact must be text"}, 400
        try:
            payment = Decimal(str(amount))
            if not payment.is_finite() or payment.as_tuple().exponent < -2 or payment <= 0:
                raise ValueError
        except (InvalidOperation, ValueError, TypeError):
            return {"error": "Enter a valid payment amount with up to two decimal places."}, 400
        day = manila_date(datetime.utcnow())
        try:
            with SalesRepository.method_lock(day, payment_method):
                received_at = datetime.utcnow()
                if manila_date(received_at) != day:
                    return {"error": "The business day changed. Please retry."}, 409
                if tab_id is not None:
                    remaining = self.repo.record_tab_payment(int(tab_id), payment, received_by,
                                                             payment_method, request_key, received_at)
                else:
                    remaining = self.repo.record_customer_payment(
                        customer_name, payment, received_by, payment_method,
                        customer_contact, request_key, received_at=received_at,
                    )
                self.repo.save()
        except ValueError as exc:
            return {"error": str(exc)}, 400
        except TimeoutError as exc:
            return {"error": str(exc)}, 503
        return {"success": True, "remaining": float(remaining)}

    def list_customer_payments(self, customer_name: str = "", customer_contact: str = "", tab_id: int | None = None) -> list[dict[str, Any]]:
        payments = self.repo.list_tab_payments(tab_id) if tab_id is not None else self.repo.list_customer_payments(customer_name, customer_contact)
        grouped = {}
        for payment in payments:
            key = payment.payment_group_id or f"single-{payment.id}"
            if key not in grouped:
                actor = payment.received_by_user
                grouped[key] = {
                    "amount": Decimal("0"),
                    "received_at": payment.received_at.isoformat() + "Z",
                    "payment_method": payment.payment_method,
                    "received_by": (actor.full_name or actor.username) if actor else "Unknown",
                    "allocations": [],
                }
            grouped[key]["amount"] += payment.amount
            grouped[key]["allocations"].append({
                "receivable_id": payment.receivable_id,
                "item": payment.receivable.items_description if payment.receivable else "Unknown",
                "balance_before": float(payment.balance_before) if payment.balance_before is not None else None,
                "balance_after": float(payment.balance_after) if payment.balance_after is not None else None,
            })
        return [{**entry, "amount": float(entry["amount"])} for entry in grouped.values()]

    def update_notes(self, receivable_id: int, notes: str) -> dict[str, Any] | tuple[dict[str, Any], int]:
        if len(notes) > 2000:
            return {"error": "Notes must be 2,000 characters or fewer."}, 400
        if not self.repo.update_notes(receivable_id, notes.strip()):
            return {"error": "Receivable not found"}, 404
        self.repo.save()
        return {"success": True}

    def emit_due_reminders(self) -> None:
        due_today = self.repo.list_due_today()
        for r in due_today:
            from app.core.socketio_handlers import emit_debt_due_reminder

            emit_debt_due_reminder({
                "receivable_id": r.id,
                "customer_name": r.customer_name,
                "amount_owed": float(r.amount_owed),
            })
