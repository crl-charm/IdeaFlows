"""Small stock actions, audited in the same transaction as the quantity change."""
from decimal import Decimal

from sqlalchemy import update

from app import db
from app.models import MenuItem, InventoryItem, InventoryLog, User
from app.models.inventory import InventoryAction, OrderInventoryAllocation
from app.services.menu_availability import MODES, MenuAvailability, StockError, whole_quantity
from app.utils.inventory_helpers import is_ingredient_category


def kitchen_access(user_id):
    user = db.session.get(User, user_id) if user_id else None
    return bool(user and (user.role == "admin" or (user.is_active and user.job_role == "cook")))


def action_key(key, actor):
    if not isinstance(key, str) or not 8 <= len(key) <= 120:
        raise StockError("A request key is required. Refresh and try again.", "INVALID_REQUEST", 400)
    return f"{actor}:{key}"


def record_action(item, action, quantity, reason, actor, key, order_item_id=None):
    db.session.add(InventoryAction(request_key=key, menu_item_id=item.id,
        item_name=item.name, action=action, quantity=quantity, reason=reason[:200],
        changed_by=actor, order_item_id=order_item_id))


def change_stock(menu_id, data, actor, key, *, admin=False, commit=True):
    key = action_key(key, actor)
    availability = MenuAvailability([menu_id], lock=True)
    item = availability.items.get(menu_id)
    if not item or item.status == "deleted" or is_ingredient_category(item.category):
        raise StockError("Menu item not found.", "NOT_FOUND", 404)
    if InventoryAction.query.filter_by(request_key=key).first():
        return {"success": True, "duplicate": True}
    action = data.get("action")
    reason = str(data.get("reason") or "").strip()
    row = availability.stock.get(menu_id)
    if action == "servings":
        mode = availability.mode(item)
        if mode not in {"prepared", "recipe", "untracked"}:
            raise StockError("This item is counted in pieces, not servings.", "INVALID_MODE", 400)
        quantity = whole_quantity(data.get("quantity"), allow_zero=True)
        if row is None:
            row = InventoryItem(menu_item_id=menu_id, stock_qty=0, unit="servings")
            db.session.add(row)
            db.session.flush()
        if row.unit != "servings" and OrderInventoryAllocation.query.filter_by(inventory_item_id=row.id).first():
            raise StockError("This stock has previous sales in another unit. Ask the owner to reconcile it.", "UNIT_HISTORY_CONFLICT")
        previous = row.stock_qty
        result = db.session.execute(update(InventoryItem).where(
            InventoryItem.id == row.id, InventoryItem.stock_qty == previous
        ).values(stock_qty=quantity, unit="servings"), execution_options={"synchronize_session": False})
        if result.rowcount != 1:
            raise StockError("The serving count changed. Refresh and try again.")
        if mode == "untracked":
            item.inventory_mode = "prepared"
        elif item.inventory_mode is None:
            item.inventory_mode = mode
        db.session.add(InventoryLog(inventory_item_id=row.id, change_qty=Decimal(quantity) - previous,
            reason="Manual serving estimate", changed_by=actor))
        record_action(item, "servings", quantity, "Manual serving estimate", actor, key)
    elif action == "setup":
        if not admin:
            raise StockError("Only the owner can change stock setup.", "FORBIDDEN", 403)
        mode = data.get("inventory_mode")
        if mode not in MODES:
            raise StockError("Choose how to count this item.", "INVALID_MODE", 400)
        if not reason:
            raise StockError("Enter a reason for the setup change.", "REASON_REQUIRED", 400)
        if mode in {"prepared", "direct", "recipe"}:
            quantity = whole_quantity(data.get("quantity"), allow_zero=True)
            threshold = whole_quantity(data.get("threshold", 3), allow_zero=True)
            unit = "pieces" if mode == "direct" else "servings"
            if row is None:
                row = InventoryItem(menu_item_id=menu_id, stock_qty=0, unit=unit)
                db.session.add(row)
                db.session.flush()
            if row.unit != unit and OrderInventoryAllocation.query.filter_by(inventory_item_id=row.id).first():
                raise StockError("This stock has previous sales in another unit. Keep its current unit and ask the owner to reconcile it before switching.", "UNIT_HISTORY_CONFLICT")
            delta = Decimal(quantity) - row.stock_qty
            row.stock_qty, row.unit, row.low_stock_threshold = quantity, unit, threshold
            db.session.add(InventoryLog(inventory_item_id=row.id, change_qty=delta, reason=("Setup: " + reason)[:100], changed_by=actor))
        else:
            quantity = 0
        previous = availability.mode(item)
        item.inventory_mode = mode
        record_action(item, "setup", quantity, f"{previous} → {mode}: {reason}", actor, key)
    else:
        mode = availability.mode(item)
        if mode not in {"prepared", "direct"} or (not admin and mode != "prepared"):
            raise StockError("This action is only available for counted stock.", "INVALID_MODE", 400)
        if row is None:
            raise StockError("Ask the owner to set the starting stock first.", "INVENTORY_CONFIGURATION")
        if action not in {"add", "waste", "sold_out", "count"}:
            raise StockError("Choose a valid stock action.", "INVALID_ACTION", 400)
        if action == "count" and not admin:
            raise StockError("Only the owner can correct a stock count.", "FORBIDDEN", 403)
        if action in {"waste", "sold_out", "count"} and not reason:
            raise StockError("Enter a short reason for this change.", "REASON_REQUIRED", 400)
        quantity = 0 if action == "sold_out" else whole_quantity(data.get("quantity"), allow_zero=action == "count")
        delta = Decimal(quantity) if action == "add" else -Decimal(quantity) if action == "waste" else Decimal(quantity) - row.stock_qty
        result = db.session.execute(update(InventoryItem).where(
            InventoryItem.id == row.id, InventoryItem.stock_qty + delta >= 0
        ).values(stock_qty=InventoryItem.stock_qty + delta), execution_options={"synchronize_session": False})
        if result.rowcount != 1:
            raise StockError("There is not enough stock for that change.")
        db.session.add(InventoryLog(inventory_item_id=row.id, change_qty=delta,
            reason=(f"{action.replace('_', ' ').title()}: {reason or 'New stock'}")[:100], changed_by=actor))
        record_action(item, action, delta, reason or "New stock", actor, key)
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return {"success": True}
