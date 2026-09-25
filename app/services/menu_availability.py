"""One availability calculation for ordering, kitchen and owner screens."""
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from sqlalchemy import update

from app import db
from app.models import MenuItem, MenuItemIngredient, InventoryItem, InventoryLog
from app.models.inventory import OrderInventoryAllocation
from app.utils.inventory_helpers import is_ingredient_category

MODES = {"prepared", "direct", "recipe", "untracked"}


class StockError(ValueError):
    def __init__(self, message, code="INSUFFICIENT_STOCK", status=409, item_ids=None):
        super().__init__(message)
        self.code, self.status = code, status
        self.item_ids = item_ids or []


def whole_quantity(value, *, allow_zero=False):
    try:
        number = Decimal(str(value))
        if isinstance(value, bool) or not number.is_finite() or number != number.to_integral_value():
            raise ValueError
        if number < (0 if allow_zero else 1) or number > 999999:
            raise ValueError
        return int(number)
    except (InvalidOperation, TypeError, ValueError):
        raise StockError("Enter a valid whole number.", "INVALID_QUANTITY", 400)


class MenuAvailability:
    def __init__(self, items=None, *, lock=False, preloaded=None):
        if preloaded is not None:
            self.items, self.stock, mappings = preloaded
            self.recipes = defaultdict(list)
            for mapping in mappings:
                self.recipes[mapping.menu_item_id].append(mapping)
            return
        query = MenuItem.query.order_by(MenuItem.id)
        if items is not None:
            query = query.filter(MenuItem.id.in_(items))
        if lock:
            query = query.populate_existing().with_for_update()
        self.items = {item.id: item for item in query.all()}
        self.recipes = defaultdict(list)
        for mapping in MenuItemIngredient.query.filter(MenuItemIngredient.menu_item_id.in_(self.items)).order_by(MenuItemIngredient.id).all():
            self.recipes[mapping.menu_item_id].append(mapping)
        stock_ids = set(self.items)
        stocks = InventoryItem.query.filter(InventoryItem.menu_item_id.in_(stock_ids)).order_by(InventoryItem.id)
        if lock:
            stocks = stocks.populate_existing().with_for_update()
        self.stock = {}
        for row in stocks.all():
            if row.menu_item_id in self.stock:
                raise StockError("Duplicate stock records need owner review.", "INVENTORY_CONFIGURATION", 409)
            self.stock[row.menu_item_id] = row

    def mode(self, item):
        return item.inventory_mode or ("recipe" if self.recipes[item.id] else "direct" if item.id in self.stock else "untracked")

    def requirements(self, item):
        mode = self.mode(item)
        if mode == "untracked":
            return []
        if mode not in MODES:
            raise StockError("The owner needs to review this item's stock setup.", "INVENTORY_CONFIGURATION", 400)
        if mode in {"prepared", "direct", "recipe"}:
            stock = self.stock.get(item.id)
            if stock is None:
                raise StockError(f"{item.name} needs a starting stock count.", "INVENTORY_ROW_NOT_FOUND", 400)
            if stock.unit != ("pieces" if mode == "direct" else "servings"):
                raise StockError(f"Check the stock unit for {item.name}.", "INVENTORY_CONFIGURATION", 400)
            return [(stock, Decimal(1))]
        return []

    def snapshot(self, item):
        mode = self.mode(item)
        error = None
        quantity = None
        low = False
        try:
            needs = self.requirements(item)
            if needs:
                quantity = min(max(0, int(row.stock_qty // per_unit)) for row, per_unit in needs)
                low = quantity > 0 and any(row.stock_qty <= row.low_stock_threshold for row, _ in needs)
        except StockError as exc:
            quantity = 0
            if not (mode == "recipe" and exc.code == "INVENTORY_ROW_NOT_FOUND"):
                error = exc.code
        disabled = not item.is_available or item.status == "deleted" or is_ingredient_category(item.category)
        state = "disabled" if disabled else "configuration_error" if error else "sold_out" if quantity == 0 else "low" if low else "available"
        unit = "servings" if mode in {"prepared", "recipe"} else "pieces" if mode == "direct" else None
        message = (
            "Unavailable" if disabled else
            "Needs stock setup: has no inventory record" if error == "INVENTORY_ROW_NOT_FOUND" else
            "Needs stock setup" if error else
            "Sold out" if quantity == 0 else
            "Available" if quantity is None else
            f"{'Only ' if low else ''}{quantity} {unit} left"
        )
        return dict(inventory_mode=mode, available_quantity=quantity, display_unit=unit,
                    availability_state=state, can_order=state in {"available", "low"},
                    availability_message=message, capacity=quantity, is_low_stock=low,
                    is_out_of_stock=quantity == 0, availability_error=error,
                    setup_review=item.inventory_mode is None)

    def shortage(self, item, quantity):
        for row, per_unit in self.requirements(item):
            if row.stock_qty < per_unit * quantity:
                return row.menu_item.name
        return None

    def reserve(self, order_items, actor):
        plans = []
        total = defaultdict(Decimal)
        for order_item in order_items:
            item = self.items.get(order_item.menu_item_id)
            if item is None or not self.snapshot(item)["can_order"]:
                raise StockError(f"{item.name if item else 'An item'} is unavailable. Your cart has been kept.")
            for row, per_unit in self.requirements(item):
                amount = per_unit * order_item.quantity
                total[row.id] += amount
                plans.append((order_item, item, row, per_unit, amount))
        # Conditional writes also prevent lost updates when SQLite ignores FOR UPDATE.
        for stock_id in sorted(total):
            amount = total[stock_id]
            affected = [item.id for _, item, row, _, _ in plans if row.id == stock_id]
            result = db.session.execute(update(InventoryItem).where(
                InventoryItem.id == stock_id, InventoryItem.stock_qty >= amount
            ).values(stock_qty=InventoryItem.stock_qty - amount), execution_options={"synchronize_session": False})
            if result.rowcount != 1:
                row = next(row for _, _, row, _, _ in plans if row.id == stock_id)
                raise StockError(f"Not enough {row.menu_item.name} for this order. Your cart has been kept.", item_ids=affected)
        for order_item, item, row, per_unit, amount in plans:
            db.session.add(OrderInventoryAllocation(order_id=order_item.order_id, order_item_id=order_item.id,
                menu_item_id=item.id, inventory_item_id=row.id, inventory_mode=self.mode(item), unit=row.unit,
                ordered_units=order_item.quantity, quantity_per_unit=per_unit,
                quantity_deducted=amount, quantity_restored=0))
            db.session.add(InventoryLog(inventory_item_id=row.id, change_qty=-amount,
                reason=f"Sale: {item.name}"[:100], changed_by=actor))
