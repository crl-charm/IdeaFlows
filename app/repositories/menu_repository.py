from __future__ import annotations

from typing import Optional

from sqlalchemy import or_

from app import db
from app.models.menu_item import MenuItem


class MenuRepository:
    def get(self, item_id: int) -> Optional[MenuItem]:
        return MenuItem.query.filter_by(id=item_id).first()

    def list_all(self) -> list[MenuItem]:
        return (
            MenuItem.query.filter(
                or_(MenuItem.status.is_(None), MenuItem.status != "deleted"),
                or_(MenuItem.category.is_(None), db.func.trim(db.func.lower(MenuItem.category)) != "ingredient")
            )
            .order_by(MenuItem.name)
            .all()
        )

    def list_available(self) -> list[MenuItem]:
        return (
            MenuItem.query.filter_by(is_available=True)
            .filter(
                or_(MenuItem.status.is_(None), MenuItem.status != "deleted"),
                or_(MenuItem.category.is_(None), db.func.trim(db.func.lower(MenuItem.category)) != "ingredient")
            )
            .order_by(MenuItem.name)
            .all()
        )

    def list_for_ordering(self) -> list[MenuItem]:
        """Non-deleted items for staff/admin ordering (includes disabled items)."""
        return (
            MenuItem.query.filter(
                or_(MenuItem.status.is_(None), MenuItem.status != "deleted"),
                or_(MenuItem.category.is_(None), db.func.trim(db.func.lower(MenuItem.category)) != "ingredient")
            )
            .order_by(MenuItem.category.asc(), MenuItem.name.asc())
            .all()
        )

    def create(self, name: str, price: float, category: str) -> MenuItem:
        item = MenuItem(name=name, price=price, category=category, is_available=True)
        db.session.add(item)
        db.session.flush()
        return item

    def update(self, item_id: int, name: Optional[str] = None, price: Optional[float] = None, category: Optional[str] = None) -> bool:
        item = self.get(item_id)
        if not item:
            return False
        if name is not None:
            item.name = name
        if price is not None:
            item.price = price
        if category is not None:
            item.category = category
        return True

    def toggle_availability(self, item_id: int) -> bool:
        item = self.get(item_id)
        if not item:
            return False
        item.is_available = not item.is_available
        return True

    def delete(self, item_id: int) -> bool:
        item = self.get(item_id)
        if not item:
            return False

        # Soft-delete preserves order/inventory history and avoids FK violations.
        item.status = "deleted"
        item.is_available = False
        return True

    def save(self) -> None:
        db.session.commit()
