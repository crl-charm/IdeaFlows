from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from app.repositories.receivable_repository import ReceivableRepository, ReceivableTabConflict
from app import db
from app.models import User, MenuItem
from app.models.receivable import ReceivableTab, ReceivableItem
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

    def suggest_customers(self, search: str) -> list[dict]:
        if not isinstance(search, str) or not 2 <= len(search.strip()) <= 100:
            raise ValueError("Enter 2–100 characters to search customers.")
        return self.repo.suggest_customers(search.strip())

    def tab_detail(self, tab_id: int) -> dict | None:
        tab = db.session.get(ReceivableTab, tab_id)
        if not tab:
            return None
        records = self._serialize(self.repo.tab_records(tab_id))
        return {"id": tab.id, "customer_name": tab.customer_name,
                "account_id": tab.account_id,
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
        incurred_date: Optional[str] = None,
        notes: Optional[str] = None,
        tab_id: Optional[int] = None,
        actor_role: str = "staff",
        account_id: Optional[int] = None,
        items: Optional[list] = None,
        ordered_by: Optional[str] = None,
    ) -> dict[str, Any]:
        if not isinstance(customer_name, str) or not customer_name.strip() or len(customer_name.strip()) > 100:
            raise ValueError("Enter a customer name up to 100 characters.")
        if customer_contact is None:
            customer_contact = ""
        if not isinstance(customer_contact, str) or len(customer_contact.strip()) > 100:
            raise ValueError("Contact must be text up to 100 characters.")
        snapshots = self.menu_snapshots(items) if items is not None else []
        if snapshots:
            items_description = "; ".join(f"{row.quantity} × {row.name_snapshot}" +
                (" (no rice)" if row.no_rice else "") + (" (no egg)" if row.no_egg else "") for row in snapshots)
            amount_owed = sum((row.unit_price * row.quantity for row in snapshots), Decimal("0"))
        if not isinstance(items_description, str) or not items_description.strip() or len(items_description) > 10000:
            raise ValueError("Items description is required.")
        if tab_id is not None and (isinstance(tab_id, bool) or not str(tab_id).isdigit()):
            raise ValueError("Choose a valid customer tab.")
        if account_id is not None and (isinstance(account_id, bool) or not str(account_id).isdigit()):
            raise ValueError("Choose a valid customer account.")
        if ordered_by is not None and (not isinstance(ordered_by, str) or len(ordered_by) > 100):
            raise ValueError("Ordered by must be text up to 100 characters.")
        try:
            due = date.fromisoformat(due_date)
            incurred = date.fromisoformat(incurred_date) if incurred_date else None
        except (TypeError, ValueError):
            raise ValueError("Enter valid Date Taken and Due Date values.")
        try:
            amount_decimal = Decimal(str(amount_owed))
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError("Enter a valid amount.") from None
        if not amount_decimal.is_finite() or not 0 < amount_decimal <= Decimal("99999999.99") or amount_decimal.as_tuple().exponent < -2:
            raise ValueError("Enter a positive amount with up to two decimal places.")
        if notes is not None and (not isinstance(notes, str) or len(notes) > 2000):
            raise ValueError("Notes must be text up to 2,000 characters.")
        if actor_role not in {"admin", "staff"}:
            raise ValueError("Signed-in account not found. Please log in again.")
        actor = db.session.get(User, created_by)
        if not actor:
            raise ValueError("Signed-in account not found. Please log in again.")
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
                    due, created_by, session_id, actor.username, incurred, clean_notes,
                    int(tab_id) if tab_id is not None else None,
                    int(account_id) if account_id is not None else None,
                )
                receivable.ordered_by = (ordered_by or "").strip() or None
                for row in snapshots:
                    row.receivable_id = receivable.id
                    db.session.add(row)
                self.repo.save()
                return {"success": True, "data": {"id": receivable.id, "tab_id": receivable.tab_id,
                        "account_id": receivable.tab.account_id}}
            except IntegrityError:
                db.session.rollback()
                if attempt or tab_id is not None:
                    raise ReceivableTabConflict("The customer tab changed. Refresh and try again.")
        raise ValueError("Could not create customer tab.")

    @staticmethod
    def menu_catalog() -> list[dict]:
        # Recording already-taken items does not reserve or consume stock.
        from app.utils.inventory_helpers import is_ingredient_category
        return [{"id": item.id, "name": item.name, "price": str(item.price),
                 "can_remove_rice": item.can_remove_rice, "can_remove_egg": item.can_remove_egg}
                for item in MenuItem.query.filter_by(status="active").order_by(MenuItem.name, MenuItem.id).all()
                if item.price is not None and item.price > 0 and not is_ingredient_category(item.category)]

    @staticmethod
    def menu_snapshots(items: list) -> list[ReceivableItem]:
        from app.services.menu_availability import whole_quantity
        if not isinstance(items, list) or not 1 <= len(items) <= 100:
            raise ValueError("Choose 1–100 menu lines, or use a manual historical entry.")
        parsed = []
        for row in items:
            if not isinstance(row, dict) or set(row) - {"menu_item_id", "quantity", "no_rice", "no_egg", "expected_base_price"}:
                raise ValueError("Invalid menu line.")
            if not all(isinstance(row.get(key, False), bool) for key in ("no_rice", "no_egg")):
                raise ValueError("Invalid meal option.")
            parsed.append((whole_quantity(row.get("menu_item_id")), whole_quantity(row.get("quantity")), row))
        menu = {item.id: item for item in MenuItem.query.filter(MenuItem.id.in_([row[0] for row in parsed])).with_for_update().all()}
        catalog_ids = {row["id"] for row in ReceivableService.menu_catalog()}
        snapshots = []
        for item_id, quantity, row in parsed:
            item = menu.get(item_id)
            if not item or item_id not in catalog_ids:
                raise ValueError("A selected item is no longer on the menu. Refresh the menu.")
            rice, egg = row.get("no_rice", False), row.get("no_egg", False)
            if (rice and not item.can_remove_rice) or (egg and not item.can_remove_egg):
                raise ValueError("This meal option is unavailable. Refresh the menu.")
            if "expected_base_price" in row and str(row["expected_base_price"]) != str(item.price):
                try:
                    matches = Decimal(str(row["expected_base_price"])) == item.price
                except (InvalidOperation, ValueError, TypeError):
                    matches = False
                if not matches:
                    raise ValueError("Menu price changed. Refresh the menu and review the total before saving.")
            price = item.price - Decimal("18.00") * (rice + egg)
            if not price.is_finite() or price <= 0:
                raise ValueError("Check the menu price and meal options.")
            snapshots.append(ReceivableItem(menu_item_id=item.id, name_snapshot=item.name, quantity=quantity,
                                           base_price=item.price, unit_price=price, no_rice=rice, no_egg=egg))
        return snapshots

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
