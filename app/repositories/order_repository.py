from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import selectinload

from app import db
from app.models import CustomerSession, MenuItem, Order, OrderItem
from app.repositories.menu_repository import MenuRepository


@dataclass(frozen=True)
class OrderRepository:
    def list_menu_items(self) -> list[MenuItem]:
        return MenuRepository().list_for_ordering()

    def get_session(self, session_id: int) -> Optional[CustomerSession]:
        return (
            CustomerSession.query.options(selectinload(CustomerSession.space_type))
            .filter_by(id=session_id)
            .first()
        )

    def get_order(self, order_id: int) -> Optional[Order]:
        return (
            Order.query.options(selectinload(Order.items).selectinload(OrderItem.menu_item))
            .filter_by(id=order_id)
            .first()
        )

    def get_order_item(self, item_id: int) -> Optional[OrderItem]:
        return OrderItem.query.get(item_id)

    def add_order_with_items(self, session_id: int, handled_by: Optional[int], items: list[dict]) -> int:
        new_order = Order(customer_session_id=session_id, status="preparing", handled_by=handled_by)
        db.session.add(new_order)
        db.session.flush()

        for item in items:
            menu_item_id = item.get("menu_item_id")
            if not menu_item_id:
                continue
            menu_item = MenuItem.query.get(menu_item_id)
            if not menu_item:
                continue

            order_item = OrderItem(
                order_id=new_order.id,
                menu_item_id=menu_item.id,
                quantity=item.get("quantity", 1),
                price=menu_item.price,
            )
            db.session.add(order_item)

        db.session.flush()
        return int(new_order.id)

    def list_orders_for_session(self, session_id: int, include_done: bool) -> list[Order]:
        q = (
            Order.query.options(
                selectinload(Order.items).selectinload(OrderItem.menu_item),
                selectinload(Order.handler),
            )
            .filter_by(customer_session_id=session_id)
            .order_by(Order.id.desc())
        )
        if not include_done:
            q = q.filter(Order.status != "done")
        return q.all()

    def list_active_session_orders_summary(self):
        return (
            CustomerSession.query.options(
                selectinload(CustomerSession.space_type),
                selectinload(CustomerSession.orders)
                .selectinload(Order.items)
                .selectinload(OrderItem.menu_item),
            )
            .filter(CustomerSession.status == "active")
            .order_by(CustomerSession.time_in.desc())
            .all()
        )

    def pending_counts(self) -> dict[str, int]:
        pending_sessions = (
            db.session.query(func.count(func.distinct(Order.customer_session_id)))
            .join(CustomerSession, CustomerSession.id == Order.customer_session_id)
            .filter(CustomerSession.status == "active")
            .filter(Order.status != "done")
            .scalar()
        ) or 0

        pending_items = (
            db.session.query(func.coalesce(func.sum(OrderItem.quantity), 0))
            .select_from(OrderItem)
            .join(Order, OrderItem.order_id == Order.id)
            .join(CustomerSession, CustomerSession.id == Order.customer_session_id)
            .filter(CustomerSession.status == "active")
            .filter(Order.status != "done")
            .scalar()
        ) or 0

        return {"pending_sessions": int(pending_sessions), "pending_items": int(pending_items)}

    def commit(self) -> None:
        db.session.commit()

    def mark_session_served(self, session_id: int) -> int:
        session_order_ids = [
            row.id for row in Order.query.with_entities(Order.id).filter(Order.customer_session_id == session_id).all()
        ]
        updated_orders = (
            Order.query.filter(Order.id.in_(session_order_ids), Order.status != "done")
            .update({"status": "done"}, synchronize_session=False)
        ) if session_order_ids else 0
        if session_order_ids:
            (
                OrderItem.query.filter(OrderItem.order_id.in_(session_order_ids))
                .update({"status": "done"}, synchronize_session=False)
            )
        db.session.commit()
        return int(updated_orders or 0)

