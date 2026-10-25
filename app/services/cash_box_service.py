from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256

from sqlalchemy.exc import IntegrityError

from app import db
from app.models import CashBoxEvent, Payable, User
from app.repositories.sales_repository import SalesRepository
from app.utils.dates import manila_date

BOXES = ("petty", "customer")
CENT = Decimal("0.01")


def cash_amount(value, *, zero_ok=False):
    try:
        amount = Decimal(str(value))
        if (not amount.is_finite() or amount > Decimal("99999999.99")
                or amount.as_tuple().exponent < -2 or (amount < 0 if zero_ok else amount <= 0)):
            raise ValueError
        return amount.quantize(CENT)
    except (ValueError, TypeError, InvalidOperation):
        raise ValueError("Enter a valid amount with up to two decimal places.") from None


class CashBoxService:
    @staticmethod
    def opening_date():
        openings = CashBoxEvent.query.filter_by(kind="opening").order_by(CashBoxEvent.id).all()
        if len({item.box for item in openings}) != 2:
            return None
        dates = {item.effective_date for item in openings}
        return dates.pop() if len(dates) == 1 else None

    @staticmethod
    def _opening_amounts():
        amounts = {box: Decimal("0") for box in BOXES}
        openings = CashBoxEvent.query.filter_by(kind="opening").all()
        for entry in openings:
            amounts[entry.box] += entry.effect
        for entry in CashBoxEvent.query.filter_by(kind="reversal").all():
            if entry.reversed_entry and entry.reversed_entry.kind == "opening":
                amounts[entry.box] += entry.effect
        return amounts

    @classmethod
    def summaries(cls, end_date: date):
        start = cls.opening_date()
        if not start or end_date < start:
            return {}
        ledger = SalesRepository().daily_ledger(start, end_date)
        # ponytail: one indexed ledger scan from the opening date; add a checkpoint only if that range becomes slow.
        day = start
        while day <= end_date:
            ledger.setdefault(day, SalesRepository.daily_ledger_empty(day))
            day += timedelta(days=1)
        running = cls._opening_amounts()
        summaries = {}
        for day in sorted(ledger):
            daily = ledger[day]
            before = running.copy()
            movement = {box: Decimal(str(daily.get("cash_box_movements", {}).get(box, 0))) for box in BOXES}
            for box in BOXES:
                running[box] += movement[box]
            summaries[day] = {
                "opening": {box: float(before[box]) for box in BOXES},
                "movement": {box: float(movement[box]) for box in BOXES},
                "closing": {box: float(running[box]) for box in BOXES},
                "total_opening": float(sum(before.values())),
                "total_movement": float(sum(movement.values())),
                "total_closing": float(sum(running.values())),
                "receipts": daily.get("cash_box_receipts", {box: 0 for box in BOXES}),
                "spending": daily.get("cash_box_spending", {box: 0 for box in BOXES}),
                "topups": daily.get("cash_box_topups", {box: 0 for box in BOXES}),
                "withdrawals": daily.get("cash_box_withdrawals", {box: 0 for box in BOXES}),
                "unassigned_cash_movement": float(daily.get("cash_box_movements", {}).get("unknown", 0)),
                "unassigned_cash_entries": daily.get("cash_box_unassigned_count", 0),
            }
        return summaries

    @classmethod
    def balance(cls, box: str, day: date):
        summaries = cls.summaries(day)
        if not summaries:
            raise ValueError("Set opening cash counts before recording cash movements.")
        return Decimal(str(summaries[max(summaries)]["closing"][box])).quantize(CENT)

    @staticmethod
    def serialize(entry):
        return {
            "id": entry.id, "kind": entry.kind, "box": entry.box,
            "payment_method": entry.payment_method,
            "amount": float(entry.amount), "effect": float(entry.effect),
            "effective_date": entry.effective_date.isoformat(),
            "recorded_at": entry.recorded_at.isoformat() + "Z",
            "actor": entry.actor_name, "note": entry.note, "recipient": entry.recipient,
            "repay_owner": entry.repay_owner, "reverses_id": entry.reverses_id,
            "replaces_id": entry.replaces_id,
            "balance_before": float(entry.balance_before) if entry.balance_before is not None else None,
            "balance_after": float(entry.balance_after) if entry.balance_after is not None else None,
        }

    @classmethod
    def history(cls, start: date | None = None, end: date | None = None):
        query = CashBoxEvent.query
        if start:
            query = query.filter(CashBoxEvent.effective_date >= start)
        if end:
            query = query.filter(CashBoxEvent.effective_date <= end)
        return [cls.serialize(e) for e in query.order_by(CashBoxEvent.effective_date.desc(), CashBoxEvent.id.desc()).all()]

    @staticmethod
    def owner_payable(amount: Decimal, actor_id: int, day: date, *, event=None, expense=None):
        payable = Payable(
            creditor_name="Owner", items_description=(
                f"Reimburse owner petty cash top-up #{event.id}" if event else
                f"Reimburse owner-paid expense #{expense.id}"
            ),
            amount_owed=amount, partial_paid=Decimal("0"), status="Unpaid",
            incurred_date=day, due_date=day, created_by=actor_id,
            owner_cash_event_id=event.id if event else None,
            owner_expense_id=expense.id if expense else None,
        )
        db.session.add(payable)
        db.session.flush()
        return payable

    @classmethod
    def open_boxes(cls, day_raw, amounts, actor_id, request_key=None):
        if not request_key or len(request_key) > 200:
            return {"error": "A request key is required for cash entries."}, 400
        try:
            day = date.fromisoformat(day_raw)
            initial_topup = amounts.get("initial_topup")
            if initial_topup is not None:
                topup = cash_amount(initial_topup, zero_ok=True)
                note = amounts.get("note")
                if note is not None and (not isinstance(note, str) or len(note.strip()) > 255):
                    raise ValueError("Enter a note of at most 255 characters.")
                if not isinstance(amounts.get("repay_owner"), bool):
                    return {"error": "Choose whether the owner must be repaid."}, 400
                values = {box: Decimal("0.00") for box in BOXES}
            else:
                values = {box: cash_amount(amounts.get(box), zero_ok=True) for box in BOXES}
            if day > manila_date(datetime.utcnow()):
                raise ValueError("Opening date cannot be in the future.")
        except (TypeError, ValueError) as exc:
            return {"error": str(exc) or "Enter a valid opening date and both amounts."}, 400
        today = manila_date(datetime.utcnow())
        try:
            with SalesRepository.method_lock(today, "cash"):
                prefix = sha256(request_key.encode()).hexdigest()
                existing = CashBoxEvent.query.filter_by(request_key=f"{prefix}:petty").first()
                if existing:
                    customer = CashBoxEvent.query.filter_by(request_key=f"{prefix}:customer").first()
                    added = CashBoxEvent.query.filter_by(request_key=f"{prefix}:topup").first()
                    matches = (existing.actor_id == actor_id and existing.effective_date == day
                               and existing.amount == values["petty"] and customer is not None
                               and customer.amount == values["customer"])
                    if initial_topup is not None and topup:
                        matches = matches and added is not None and (
                            added.amount == topup and added.repay_owner == amounts["repay_owner"]
                            and added.note == (note.strip() if note else None))
                    else:
                        matches = matches and added is None
                    if not matches:
                        return {"error": "This request key belongs to a different cash entry."}, 409
                    return {"success": True, "replayed": True}
                if cls.opening_date() or CashBoxEvent.query.filter_by(kind="opening").first():
                    return {"error": "Opening cash counts were already recorded."}, 409
                actor = db.session.get(User, actor_id)
                for box in BOXES:
                    db.session.add(CashBoxEvent(
                        kind="opening", box=box, amount=values[box], effect=values[box],
                        effective_date=day, recorded_at=datetime.utcnow(), actor_id=actor_id,
                        actor_name=actor.full_name or actor.username,
                        balance_before=Decimal("0"), balance_after=values[box],
                        request_key=f"{prefix}:{box}",
                    ))
                if initial_topup is not None and topup:
                    entry = CashBoxEvent(
                        kind="owner_topup", box="petty", amount=topup, effect=topup,
                        effective_date=day, recorded_at=datetime.utcnow(), actor_id=actor_id,
                        actor_name=actor.full_name or actor.username,
                        repay_owner=amounts["repay_owner"],
                        note=note.strip() if note else None,
                        balance_before=Decimal("0.00"), balance_after=topup,
                        request_key=f"{prefix}:topup",
                    )
                    db.session.add(entry)
                    db.session.flush()
                    if entry.repay_owner:
                        cls.owner_payable(topup, actor_id, day, event=entry)
                db.session.commit()
        except (IntegrityError, TimeoutError):
            db.session.rollback()
            return {"error": "Opening counts are already recorded or busy. Please refresh."}, 409
        return {"success": True}

    @classmethod
    def post(cls, kind, box, amount_raw, day_raw, actor_id, *, note=None, recipient=None,
             repay_owner=None, owner_debt_repayment=None, request_key=None):
        if not request_key or len(request_key) > 200:
            return {"error": "A request key is required for cash entries."}, 400
        if kind not in {"owner_topup", "withdrawal"} or (kind == "owner_topup" and box != "petty") or box not in BOXES:
            return {"error": "Invalid cash box action."}, 400
        if kind == "owner_topup" and not isinstance(repay_owner, bool):
            return {"error": "Choose whether the owner must be repaid."}, 400
        if kind == "withdrawal" and (not isinstance(recipient, str) or not recipient.strip()
                                      or not isinstance(note, str) or not note.strip()):
            return {"error": "Enter the recipient and purpose."}, 400
        if kind == "withdrawal" and owner_debt_repayment is not False:
            return {"error": "Confirm this is not an owner debt repayment. Record repayments in Payables."}, 400
        if any(value is not None and (not isinstance(value, str) or len(value.strip()) > limit)
               for value, limit in ((note, 255), (recipient, 100))):
            return {"error": "Note or recipient is too long."}, 400
        try:
            amount = cash_amount(amount_raw)
            day = date.fromisoformat(day_raw)
        except (ValueError, TypeError) as exc:
            return {"error": str(exc) or "Enter a valid date."}, 400
        today = manila_date(datetime.utcnow())
        if day > today:
            return {"error": "Cash date cannot be in the future."}, 400
        try:
            with SalesRepository.method_lock(today, "cash"):
                existing = CashBoxEvent.query.filter_by(request_key=request_key).first()
                if existing:
                    if (existing.actor_id, existing.kind, existing.box, existing.amount,
                        existing.effective_date, existing.note, existing.recipient, existing.repay_owner) != (
                        actor_id, kind, box, amount, day, note.strip() if note else None,
                        recipient.strip() if recipient else None, bool(repay_owner) if kind == "owner_topup" else False):
                        return {"error": "This request key belongs to a different cash entry."}, 409
                    return {"success": True, "data": cls.serialize(existing), "replayed": True}
                start = cls.opening_date()
                if not start or day < start:
                    return {"error": "Set opening cash counts first; cash date must be on or after the opening date."}, 400
                before = cls.balance(box, day)
                effect = amount if kind == "owner_topup" else -amount
                actor = db.session.get(User, actor_id)
                entry = CashBoxEvent(
                    kind=kind, box=box, amount=amount, effect=effect,
                    effective_date=day, recorded_at=datetime.utcnow(), actor_id=actor_id,
                    actor_name=actor.full_name or actor.username, note=note.strip() if note else None,
                    recipient=recipient.strip() if recipient else None,
                    repay_owner=bool(repay_owner) if kind == "owner_topup" else False,
                    request_key=request_key, balance_before=before, balance_after=before + effect,
                )
                db.session.add(entry)
                db.session.flush()
                if entry.repay_owner:
                    cls.owner_payable(amount, actor_id, day, event=entry)
                db.session.commit()
        except (IntegrityError, TimeoutError):
            db.session.rollback()
            return {"error": "This action was already recorded or is busy. Please refresh."}, 409
        return {"success": True, "data": cls.serialize(entry)}

    @classmethod
    def reverse(cls, entry_id, actor_id, reason, request_key=None, replacement_amount=None):
        if not request_key or len(request_key) > 200:
            return {"error": "A request key is required for cash entries."}, 400
        if not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > 255:
            return {"error": "Enter a correction reason (up to 255 characters)."}, 400
        today = manila_date(datetime.utcnow())
        try:
            with SalesRepository.method_lock(today, "cash"):
                original = CashBoxEvent.query.filter_by(id=entry_id).with_for_update().first()
                if not original or original.kind == "reversal":
                    return {"error": "Cash entry not found."}, 404
                replacement = None
                if original.kind == "opening":
                    try:
                        replacement = cash_amount(replacement_amount, zero_ok=True)
                    except ValueError:
                        return {"error": "Enter the corrected opening count, including zero."}, 400
                existing = CashBoxEvent.query.filter_by(request_key=request_key).first()
                if existing:
                    replaced = CashBoxEvent.query.filter_by(replaces_id=entry_id).first()
                    if (existing.actor_id != actor_id or existing.reverses_id != entry_id
                            or existing.note != reason.strip()
                            or (original.kind == "opening" and (not replaced or replaced.amount != replacement))):
                        return {"error": "This request key belongs to a different correction."}, 409
                    return {"success": True, "data": cls.serialize(existing), "replayed": True}
                if CashBoxEvent.query.filter_by(reverses_id=entry_id).first():
                    return {"error": "Cash entry already reversed."}, 409
                linked = Payable.query.filter_by(owner_cash_event_id=entry_id).with_for_update().first()
                if linked and linked.partial_paid:
                    return {"error": "Owner repayment already began. Correct its payments before reversing this top-up."}, 409
                actor = db.session.get(User, actor_id)
                before = cls.balance(original.box, original.effective_date)
                reversal = CashBoxEvent(
                    kind="reversal", box=original.box, amount=original.amount,
                    effect=-original.effect, effective_date=original.effective_date,
                    recorded_at=datetime.utcnow(), actor_id=actor_id,
                    actor_name=actor.full_name or actor.username, note=reason.strip(),
                    reverses_id=entry_id, request_key=request_key,
                    balance_before=before, balance_after=before-original.effect,
                )
                db.session.add(reversal)
                if replacement is not None:
                    db.session.add(CashBoxEvent(
                        kind="opening", box=original.box, amount=replacement, effect=replacement,
                        effective_date=original.effective_date, recorded_at=datetime.utcnow(),
                        actor_id=actor_id, actor_name=actor.full_name or actor.username,
                        note=f"Corrected opening count: {reason.strip()}", replaces_id=entry_id,
                        request_key=f"{sha256(request_key.encode()).hexdigest()}:replacement",
                        balance_before=before-original.effect,
                        balance_after=before-original.effect+replacement,
                    ))
                if linked:
                    linked.cancelled_at = reversal.recorded_at
                    linked.cancelled_by = actor_id
                    linked.cancel_reason = reason.strip()
                db.session.commit()
        except (IntegrityError, TimeoutError):
            db.session.rollback()
            return {"error": "Cash entry was already reversed or is busy. Please refresh."}, 409
        return {"success": True, "data": cls.serialize(reversal)}
