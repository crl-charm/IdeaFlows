from __future__ import annotations

from datetime import datetime
from typing import Optional

from app import db
from app.models.inventory import InventoryItem, InventoryLog


class InventoryRepository:
    def get_item(self, item_id: int) -> Optional[InventoryItem]:
        return InventoryItem.query.filter_by(id=item_id).first()

    def get_item_for_update(self, item_id: int) -> Optional[InventoryItem]:
        return InventoryItem.query.filter_by(id=item_id).with_for_update().first()

    def get_by_menu_item_id(self, menu_item_id: int) -> Optional[InventoryItem]:
        return InventoryItem.query.filter_by(menu_item_id=menu_item_id).first()

    def get_by_menu_item_id_for_update(self, menu_item_id: int) -> Optional[InventoryItem]:
        return (
            InventoryItem.query.filter_by(menu_item_id=menu_item_id)
            .with_for_update()
            .first()
        )

    def list_by_menu_item_ids(self, menu_item_ids: list[int]) -> dict[int, InventoryItem]:
        if not menu_item_ids:
            return {}
        items = InventoryItem.query.filter(
            InventoryItem.menu_item_id.in_(menu_item_ids)
        ).all()
        return {item.menu_item_id: item for item in items}

    def list_all(self) -> list[InventoryItem]:
        return InventoryItem.query.all()

    def list_low_stock(self) -> list[InventoryItem]:
        return InventoryItem.query.filter(
            InventoryItem.stock_qty > 0,
            InventoryItem.stock_qty <= InventoryItem.low_stock_threshold,
        ).all()

    def create(
        self,
        menu_item_id: int,
        stock_qty: int,
        low_stock_threshold: int,
        unit: str,
    ) -> InventoryItem:
        item = InventoryItem(
            menu_item_id=menu_item_id,
            stock_qty=stock_qty,
            low_stock_threshold=low_stock_threshold,
            unit=unit,
        )
        db.session.add(item)
        db.session.flush()
        return item

    def deduct(self, item_id: int, qty: float | Decimal, reason: str, user_id: Optional[int]) -> bool:
        from decimal import Decimal
        item = self.get_item_for_update(item_id)
        if not item:
            return False
        qty_dec = Decimal(str(qty))
        if Decimal(str(item.stock_qty)) < qty_dec:
            return False
        item.stock_qty = Decimal(str(item.stock_qty)) - qty_dec
        item.updated_at = datetime.utcnow()
        log = InventoryLog(
            inventory_item_id=item_id, change_qty=-qty_dec, reason=reason, changed_by=user_id
        )
        db.session.add(log)
        return True

    def add(self, item_id: int, qty: float | Decimal, reason: str, user_id: Optional[int]) -> bool:
        from decimal import Decimal
        item = self.get_item_for_update(item_id)
        if not item:
            return False
        qty_dec = Decimal(str(qty))
        item.stock_qty = Decimal(str(item.stock_qty or 0)) + qty_dec
        item.updated_at = datetime.utcnow()
        log = InventoryLog(
            inventory_item_id=item_id, change_qty=qty_dec, reason=reason, changed_by=user_id
        )
        db.session.add(log)
        return True

    def get_logs(self, item_id: int) -> list[InventoryLog]:
        return (
            InventoryLog.query.filter_by(inventory_item_id=item_id)
            .order_by(InventoryLog.created_at.desc())
            .all()
        )

    def delete(self, item_id: int) -> bool:
        item = self.get_item(item_id)
        if not item:
            return False
        # Delete all associated logs first
        InventoryLog.query.filter_by(inventory_item_id=item_id).delete()
        # Then delete the item
        db.session.delete(item)
        return True

    def save(self) -> None:
        db.session.commit()
