"""Customer-only statements. Reading/exporting never posts money or repairs balances."""
from collections import defaultdict
from datetime import datetime, time
from decimal import Decimal

from sqlalchemy import or_
from sqlalchemy.orm import selectinload

from app import db
from app.models import User
from app.models.receivable import (
    Receivable, ReceivableAccount, ReceivableAccountEvent, ReceivablePayment, ReceivableTab,
)
from app.utils.dates import MANILA_OFFSET, manila_date


def local_stamp(value):
    return (value + MANILA_OFFSET).strftime("%Y-%m-%d %I:%M %p") if value else "Not recorded"


class CustomerStatementService:
    @staticmethod
    def accounts(search="", page=1):
        query = ReceivableAccount.query.filter(ReceivableAccount.tabs.any(ReceivableTab.receivables.any()))
        if search:
            name, contact, _ = ReceivableTab.identity(search, search)
            query = query.filter(or_(ReceivableAccount.normalized_name.contains(name, autoescape=True),
                                     ReceivableAccount.normalized_contact.contains(contact, autoescape=True)))
        return query.order_by(ReceivableAccount.customer_name, ReceivableAccount.id).paginate(
            page=page, per_page=20, error_out=False)

    @staticmethod
    def candidates(account, search="", page=1):
        """Deliberate review candidates; a name match never associates financial rows."""
        query = ReceivableTab.query.options(selectinload(ReceivableTab.receivables)).filter(
            or_(ReceivableTab.account_id != account.id, ReceivableTab.account_id.is_(None)))
        if search:
            name, contact, _ = ReceivableTab.identity(search, search)
            query = query.filter(or_(ReceivableTab.normalized_name.contains(name, autoescape=True),
                                     ReceivableTab.normalized_contact.contains(contact, autoescape=True)))
        else:
            query = query.filter(ReceivableTab.normalized_name == account.normalized_name)
        return query.order_by(ReceivableTab.id).paginate(page=page, per_page=10, error_out=False)

    @staticmethod
    def unassigned(search="", page=1):
        query = Receivable.query.filter_by(tab_id=None)
        if search:
            query = query.filter(Receivable.customer_name.contains(search, autoescape=True))
        return query.order_by(Receivable.id).paginate(page=page, per_page=10, error_out=False)

    @staticmethod
    def review(account_id, actor_id, *, tab_id=None, receivable_id=None, confirm=False):
        if not db.session.get(User, actor_id):
            raise ValueError("Your signed-in account could not be found. Log in again.")
        account = ReceivableAccount.query.filter_by(id=account_id).with_for_update().first()
        if not account:
            raise ValueError("Customer account not found.")
        if confirm:
            account.history_reviewed_at = datetime.utcnow()
            account.history_reviewed_by = actor_id
            db.session.add(ReceivableAccountEvent(account_id=account.id, action="confirm_history", actor_id=actor_id))
        else:
            if (tab_id is None) == (receivable_id is None):
                raise ValueError("Select one cycle or one unassigned debt to associate.")
            previous_tab_id = None
            previous = None
            if receivable_id is not None:
                row = Receivable.query.filter_by(id=receivable_id).with_for_update().first()
                if not row:
                    raise ValueError("Debt not found. Refresh before reviewing it.")
                previous_tab_id = row.tab_id
                old_tab = ReceivableTab.query.filter_by(id=row.tab_id).with_for_update().first() if row.tab_id else None
                previous = old_tab.account_id if old_tab else None
                if previous == account.id:
                    raise ValueError("This debt already belongs to the selected account.")
                name, contact, _ = ReceivableTab.identity(row.customer_name, row.customer_contact)
                tab = ReceivableTab(customer_name=row.customer_name, customer_contact=row.customer_contact,
                                    normalized_name=name, normalized_contact=contact,
                                    opened_at=row.created_at or datetime.utcnow(),
                                    closed_at=(row.paid_at or row.created_at or datetime.utcnow()) if row.paid else None)
                db.session.add(tab)
                db.session.flush()
                row.tab_id = tab.id
                db.session.flush()
                if old_tab and not Receivable.query.filter_by(tab_id=old_tab.id).first():
                    old_tab.active_key = None
                    old_tab.closed_at = old_tab.closed_at or datetime.utcnow()
            else:
                tab = ReceivableTab.query.filter_by(id=tab_id).with_for_update().first()
                if not tab:
                    raise ValueError("Customer cycle not found.")
            if tab.account_id == account.id:
                raise ValueError("This cycle already belongs to the selected account.")
            previous = previous if receivable_id is not None else tab.account_id
            tab.account_id = account.id
            account.history_reviewed_at = account.history_reviewed_by = None
            if previous:
                old = db.session.get(ReceivableAccount, previous)
                old.history_reviewed_at = old.history_reviewed_by = None
            db.session.add(ReceivableAccountEvent(account_id=account.id, previous_account_id=previous,
                                                  tab_id=tab.id, previous_tab_id=previous_tab_id,
                                                  receivable_id=receivable_id,
                                                  action="associate_debt" if receivable_id else "associate_cycle", actor_id=actor_id))
        db.session.commit()

    @staticmethod
    def build(account_id, attention=""):
        if not isinstance(attention, str) or len(attention) > 100:
            raise ValueError("Attention / Contact person must be at most 100 characters.")
        account = db.session.get(ReceivableAccount, account_id)
        if account is None:
            return None
        now = datetime.utcnow()
        rows = (Receivable.query.join(ReceivableTab).filter(ReceivableTab.account_id == account_id)
                .options(selectinload(Receivable.items), selectinload(Receivable.created_by_user))
                .order_by(Receivable.id).all())
        payments = (ReceivablePayment.query.join(Receivable).join(ReceivableTab)
                    .filter(ReceivableTab.account_id == account_id)
                    .options(selectinload(ReceivablePayment.received_by_user))
                    .order_by(ReceivablePayment.received_at, ReceivablePayment.id).all())
        by_debt = defaultdict(list)
        groups = defaultdict(list)
        for payment in payments:
            by_debt[payment.receivable_id].append(payment)
            groups[payment.payment_group_id or f"single-{payment.id}"].append(payment)
        issues, notices, charges, ledger, historical = [], [], [], [], []
        # Detect malformed groups that would otherwise produce a partial receipt for this customer.
        group_ids = {p.payment_group_id for p in payments if p.payment_group_id}
        if group_ids and ReceivablePayment.query.filter(
            ReceivablePayment.payment_group_id.in_(group_ids),
            ~ReceivablePayment.receivable_id.in_([r.id for r in rows]),
        ).first():
            issues.append("A payment group includes a different account. Review its allocations before exporting.")
        total_charged = total_paid = Decimal("0.00")
        for row in rows:
            charged, saved_paid = Decimal(row.amount_owed), Decimal(row.partial_paid or 0)
            details_paid = sum((p.amount for p in by_debt[row.id]), Decimal("0.00"))
            if row.paid and saved_paid == 0 and not by_debt[row.id]:
                # Older mark-paid records stored only a flag. Never invent a dated receipt.
                saved_paid = charged
            if charged <= 0 or saved_paid < 0 or saved_paid > charged or bool(row.paid) != (saved_paid == charged):
                issues.append(f"Debt R-{row.id}: saved paid status/amount needs review.")
            if details_paid > saved_paid or any(p.amount <= 0 for p in by_debt[row.id]):
                issues.append(f"Debt R-{row.id}: detailed payments disagree with the saved paid balance.")
            unknown_paid = max(saved_paid - details_paid, Decimal("0.00"))
            if unknown_paid:
                historical.append({"reference": f"H-{row.id}", "receivable_id": row.id, "amount": unknown_paid,
                                   "description": f"R-{row.id}: Previously recorded payment/credit; date/details unavailable"})
            taken = row.incurred_date or (manila_date(row.created_at) if row.created_at else None)
            if taken is None:
                issues.append(f"Debt R-{row.id}: Date Taken is unavailable.")
            lines = [{"name": item.name_snapshot, "quantity": item.quantity, "unit_price": item.unit_price,
                      "line_total": item.unit_price * item.quantity, "no_rice": item.no_rice, "no_egg": item.no_egg}
                     for item in sorted(row.items, key=lambda item: item.id)]
            if lines and (sum((line["line_total"] for line in lines), Decimal("0")) != charged or
                          any(line["quantity"] <= 0 or line["unit_price"] <= 0 for line in lines)):
                issues.append(f"Debt R-{row.id}: item totals disagree with the charge.")
            actor = row.created_by_user
            charges.append({"id": row.id, "reference": f"R-{row.id}", "tab_id": row.tab_id,
                            "taken": taken.isoformat() if taken else "Unknown", "due": row.due_date.isoformat(),
                            "recorded_at": local_stamp(row.created_at), "description": row.items_description,
                            "ordered_by": row.ordered_by or "Not recorded", "lines": lines,
                            "recorded_by": (actor.full_name or actor.username) if actor else "Not recorded",
                            "charged": charged, "paid": saved_paid, "remaining": charged - saved_paid})
            ledger.append({"reference": f"R-{row.id}", "when": taken.isoformat() if taken else "Unknown",
                           "description": "Charge (Date Taken only)", "charge": charged, "payment": Decimal("0"),
                           "_sort": (datetime.combine(taken, time.min) if taken else datetime.min, 0, row.id)})
            total_charged += charged
            total_paid += saved_paid
        receipts = []
        for group in groups.values():
            first = group[0]
            if len({(p.received_at, p.payment_method) for p in group}) != 1:
                issues.append(f"Payment P-{first.id}: its allocations have conflicting dates or methods.")
            amount = sum((p.amount for p in group), Decimal("0.00"))
            allocations = [{"reference": f"R-{p.receivable_id}", "amount": p.amount} for p in group]
            actor = first.received_by_user
            receipt = {"reference": f"P-{first.id}", "when": local_stamp(first.received_at), "amount": amount,
                       "method": first.payment_method.upper(), "allocations": allocations,
                       "recorded_by": (actor.full_name or actor.username) if actor else "Not recorded"}
            receipts.append(receipt)
            ledger.append({"reference": receipt["reference"], "when": receipt["when"],
                           "description": "Payment / " + receipt["method"], "charge": Decimal("0"), "payment": amount,
                           "_sort": ((first.received_at + MANILA_OFFSET) if first.received_at else datetime.min, 1, first.id)})
        ledger.sort(key=lambda event: event["_sort"])
        for entry in historical:
            ledger.append({"reference": entry["reference"], "when": "Date unavailable",
                           "description": entry["description"], "charge": Decimal("0"), "payment": entry["amount"]})
        balance = Decimal("0.00")
        for entry in ledger:
            entry.pop("_sort", None)
            balance += entry["charge"] - entry["payment"]
            entry["balance"] = balance
        if historical:
            notices.append("Some historical payments have no dated receipt. They are listed after the dated history; their timing is unknown.")
        if not account.history_reviewed_at:
            notices.append("History needs review. Confirm cycle membership before downloading a final statement.")
        # ponytail: normally empty after migration; normalize orphan identities in one query, not per debt.
        legacy = db.session.query(Receivable.customer_name, Receivable.customer_contact).filter(Receivable.tab_id.is_(None)).all()
        if any(ReceivableTab.identity(name, contact)[:2] == (account.normalized_name, account.normalized_contact)
               for name, contact in legacy):
            issues.append("Unassigned historical debts match this name/contact. Review and associate them with the correct account before exporting.")
        if not rows:
            issues.append("This account has no associated debts. Select or review the correct customer account.")
        if balance != total_charged - total_paid:
            issues.append("The running balance does not reconcile. Review payment history before exporting.")
        # This explicit projection is also the entire PDF context: no other business data.
        return {"account": {"id": account.id, "reference": f"RA-{account.id:06d}",
                            "name": account.customer_name, "contact": account.customer_contact or "",
                            "reviewed_at": local_stamp(account.history_reviewed_at) if account.history_reviewed_at else None},
                "attention": attention.strip(), "generated_at": local_stamp(now), "generated_day": manila_date(now).isoformat(),
                "total_charged": total_charged, "total_paid": total_paid, "remaining": total_charged - total_paid,
                "charges": sorted(charges, key=lambda row: (row["taken"], row["id"])), "payments": receipts,
                "ledger": ledger, "historical_credits": historical, "issues": issues, "notices": notices,
                "can_export": bool(account.history_reviewed_at and not issues)}
