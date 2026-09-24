from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any, Optional

from app.core.interfaces import Notifier
from app.models import MenuItem
from app.repositories.order_repository import OrderRepository

logger = logging.getLogger(__name__)


def _normalize_item_status(status: str | None) -> str:
    if status in {None, "preparin"}:
        return "preparing"
    return status or "preparing"


def _item_is_ready(status: str | None) -> bool:
    return _normalize_item_status(status) == "done"


@dataclass(frozen=True)
class OrderService:
    repo: OrderRepository
    notifier: Notifier

    def _order_has_preparing_items(self, order) -> bool:
        return any(not _item_is_ready(item.status) for item in order.items)

    def _session_preparing_item_count(self, session_id: int) -> int:
        orders = self.repo.list_orders_for_session(session_id, include_done=False)
        return sum(
            1
            for order in orders
            for item in order.items
            if not _item_is_ready(item.status)
        )

    def list_menu(self) -> list[dict[str, Any]]:
        from app.services.menu_availability import MenuAvailability
        items = self.repo.list_menu_items()
        availability = MenuAvailability([item.id for item in items])
        return [
            dict(id=item.id, name=item.name, price=float(item.price or 0),
                 category=item.category, description=item.description, image_url=item.image_url,
                 **availability.snapshot(item), is_available=availability.snapshot(item)["can_order"])
            for item in items
        ]

    def add_order(self, *, session_id: int, items: list[dict], handled_by: Optional[int]) -> dict[str, Any] | tuple[dict[str, Any], int]:
        from app import db
        from app.models import OrderItem, User
        from app.services.menu_availability import MenuAvailability, StockError, whole_quantity
        from app.core.socketio_handlers import emit_inventory_update

        try:
            if not isinstance(items, list) or not items or len(items) > 200:
                raise StockError("Choose at least one menu item.", "INVALID_ORDER", 400)
            quantities = {}
            for row in items:
                if not isinstance(row, dict):
                    raise StockError("Invalid order item.", "INVALID_ORDER", 400)
                item_id = whole_quantity(row.get("menu_item_id"))
                quantities[item_id] = quantities.get(item_id, 0) + whole_quantity(row.get("quantity", 1))
                whole_quantity(quantities[item_id])
            availability = MenuAvailability(sorted(quantities), lock=True)
            if len(availability.items) != len(quantities):
                raise StockError("An item is no longer on the menu.", "INVALID_ORDER", 400)
            sess = self.repo.get_session(session_id)
            if not sess or sess.status != "active":
                raise StockError("Choose an active customer session.", "INVALID_SESSION", 400)
            for item in availability.items.values():
                snapshot = availability.snapshot(item)
                shortage = (availability.shortage(item, quantities[item.id])
                    if snapshot["availability_state"] in {"sold_out", "low", "available"}
                    and snapshot["available_quantity"] is not None
                    and snapshot["available_quantity"] > 0 else None)
                if not snapshot["can_order"]:
                    error_code = snapshot["availability_error"] or "UNAVAILABLE"
                    error_status = 400 if error_code in {
                        "INVENTORY_CONFIGURATION",
                        "INVENTORY_ROW_NOT_FOUND",
                        "INVALID_UNIT_CONVERSION",
                        "INSUFFICIENT_STOCK",
                    } else 409
                    raise StockError(
                        f"{item.name}: Not enough {shortage} for this order." if shortage else
                        f"{item.name}: {snapshot['availability_message']}",
                        error_code,
                        error_status,
                        item_ids=[item.id],
                    )
                if shortage:
                    raise StockError(f"{item.name}: Not enough {shortage} for this order.",
                        item_ids=[item.id])
            normalized = [dict(menu_item_id=key, quantity=value) for key, value in sorted(quantities.items())]
            actor = handled_by if handled_by and db.session.get(User, handled_by) else None
            order_id = self.repo.add_order_with_items(session_id=session_id, handled_by=actor, items=normalized)
            order_items = OrderItem.query.filter_by(order_id=order_id).order_by(OrderItem.id).all()
            availability.reserve(order_items, actor)
            self.repo.commit()
        except StockError as exc:
            db.session.rollback()
            return {"error": exc.code, "message": str(exc), "affected_item_ids": exc.item_ids}, exc.status
        except Exception:
            db.session.rollback()
            raise
        emit_inventory_update("stock_change", {"order_id": order_id})
        self.notifier.order_status_changed({"order_id": order_id, "status": "preparing", "session_id": session_id})
        return {"message": "Order added successfully", "order_id": order_id}

    def update_order_status(self, *, order_id: int, new_status: str) -> dict[str, Any] | tuple[dict[str, Any], int]:
        if new_status not in {"preparin", "preparing", "serving", "done"}:
            return {"error": "Invalid status"}, 400

        order = self.repo.get_order(order_id)
        if not order:
            return {"error": "Order not found"}, 404

        sess = self.repo.get_session(order.customer_session_id)
        if not sess or sess.status != "active":
            return {"error": "Cannot update inactive session orders"}, 400

        if new_status == "serving":
            if order.status not in {"preparin", "preparing"}:
                return {"error": "Order must be in preparing before serving"}, 400
            if self._order_has_preparing_items(order):
                return {
                    "error": "All items must be marked Done before this order can be served"
                }, 400
        elif new_status == "done":
            if order.status != "serving":
                return {"error": "Order must be in serving before done"}, 400
        else:
            return {"error": "This action is not supported"}, 400

        order.status = new_status
        self.repo.commit()
        self.notifier.order_status_changed(
            {"order_id": order_id, "status": order.status, "session_id": order.customer_session_id}
        )
        return {"message": "Order status updated", "order_id": order_id, "status": order.status}

    def get_session_orders(self, *, session_id: int, include_done: bool) -> dict[str, Any]:
        sess = self.repo.get_session(session_id)
        if not sess or sess.status != "active":
            return {
                "session_id": session_id,
                "customer_name": sess.customer_name if sess else None,
                "space_type": sess.space_type.name if sess and sess.space_type else None,
                "time_in": (sess.time_in + timedelta(hours=8)).strftime("%B %d, %Y %I:%M %p") if sess and sess.time_in else None,
                "orders": [],
                "food_total": 0.0,
                "preparing_count": 0,
                "can_serve": False,
            }

        orders = self.repo.list_orders_for_session(session_id, include_done=include_done)
        order_list: list[dict[str, Any]] = []
        food_total = Decimal("0.00")

        for order in orders:
            for item in order.items:
                total_price = item.quantity * item.price
                food_total += total_price
                order_list.append(
                    {
                        "id": item.id,
                        "order_id": order.id,
                        "order_status": order.status,
                        "item_status": item.status if item.status else "preparing",
                        "handled_by_name": order.handler.full_name if order.handler else "N/A",
                        "item_name": item.menu_item.name,
                        "quantity": item.quantity,
                        "price": float(item.price),
                        "total": float(total_price),
                    }
                )

        preparing_count = sum(
            1 for row in order_list if not _item_is_ready(row.get("item_status"))
        )

        return {
            "session_id": session_id,
            "customer_name": sess.customer_name,
            "space_type": sess.space_type.name if sess.space_type else None,
            "time_in": (sess.time_in + timedelta(hours=8)).strftime("%B %d, %Y %I:%M %p") if sess.time_in else None,
            "orders": order_list,
            "food_total": float(food_total),
            "preparing_count": preparing_count,
            "can_serve": len(order_list) > 0 and preparing_count == 0,
        }

    def pending_count(self) -> dict[str, int]:
        return self.repo.pending_counts()

    def session_orders_list_view(self) -> list[dict[str, Any]]:
        sessions = self.repo.list_active_session_orders_summary()
        result: list[dict[str, Any]] = []
        for sess in sessions:
            orders = [o for o in sess.orders if o.status != "done"]
            if not orders:
                continue
            item_count = 0
            food_total = Decimal("0.00")
            latest_status = "preparing"
            for order in orders:
                latest_status = order.status
                for item in order.items:
                    item_count += 1
                    food_total += item.quantity * item.price
            if latest_status == "preparin":
                latest_status = "preparing"
            result.append(
                {
                    "session_id": sess.id,
                    "customer_name": sess.customer_name,
                    "space_type": sess.space_type.name if sess.space_type else "N/A",
                    "time_in": (sess.time_in + timedelta(hours=8)).strftime("%B %d, %Y %I:%M %p")
                    if sess.time_in
                    else "N/A",
                    "orders_count": item_count,
                    "food_total": float(food_total),
                    "active_order_status": latest_status,
                }
            )
        return result

    def mark_session_served(self, session_id: int) -> dict[str, Any] | tuple[dict[str, Any], int]:
        sess = self.repo.get_session(session_id)
        if not sess:
            return {"error": "Session not found"}, 404
        if sess.status != "active":
            return {"error": "Session is not active"}, 400

        preparing_count = self._session_preparing_item_count(session_id)
        if preparing_count > 0:
            return {
                "error": (
                    f"Cannot mark as served: {preparing_count} item(s) still preparing. "
                    "Mark every item as Done first."
                )
            }, 400

        self.repo.mark_session_served(session_id)
        self.notifier.order_status_changed({"session_id": session_id, "status": "done"})
        return {"message": "Session marked as served", "session_id": session_id}

    def void_item(self, item_id: int, *, actor=None, admin=False, request_key=None, return_stock=True, reason="Cancelled before preparation"):
        from uuid import uuid4
        from app import db
        from app.models import OrderItem, InventoryItem, InventoryLog
        from app.models.inventory import InventoryAction, OrderInventoryAllocation
        from app.services.stock_management import action_key, record_action
        from app.services.menu_availability import StockError
        from app.core.socketio_handlers import emit_inventory_update
        from sqlalchemy import update

        try:
            key = action_key(request_key or str(uuid4()), actor)
            if InventoryAction.query.filter_by(request_key=key).first():
                return {"message": "This cancellation was already recorded.", "duplicate": True}
            item = OrderItem.query.filter_by(id=item_id).populate_existing().with_for_update().first()
            if not item:
                raise StockError("Item not found.", "NOT_FOUND", 404)
            sess = self.repo.get_session(item.order.customer_session_id)
            if not sess or sess.status != "active":
                raise StockError("Paid or closed sessions need an owner billing correction.", "SESSION_CLOSED", 409)
            prepared = _item_is_ready(item.status) or item.order.status in {"serving", "done"}
            if prepared and not admin:
                raise StockError("Ask the owner to cancel food already prepared or served.", "FORBIDDEN", 403)
            if not isinstance(return_stock, bool) or not str(reason or "").strip():
                raise StockError("Choose whether stock can be returned and enter a reason.", "INVALID_VOID", 400)
            allocations = OrderInventoryAllocation.query.filter_by(order_item_id=item_id).order_by(
                OrderInventoryAllocation.inventory_item_id).with_for_update().all()
            if allocations and not request_key:
                raise StockError("Refresh the page before cancelling.", "REQUEST_KEY_REQUIRED", 400)
            if return_stock:
                for allocation in allocations:
                    row = InventoryItem.query.filter_by(id=allocation.inventory_item_id).populate_existing().with_for_update().first()
                    if row is None or row.unit != allocation.unit:
                        raise StockError("Stock units changed. Ask the owner to reconcile this cancellation.", "UNIT_HISTORY_CONFLICT")
                    amount = allocation.quantity_per_unit
                    if allocation.quantity_restored + amount > allocation.quantity_deducted:
                        raise StockError("This stock has already been returned.", "ALREADY_RESTORED")
                    db.session.execute(update(InventoryItem).where(InventoryItem.id == row.id).values(
                        stock_qty=InventoryItem.stock_qty + amount), execution_options={"synchronize_session": False})
                    allocation.quantity_restored += amount
                    db.session.add(InventoryLog(inventory_item_id=row.id, change_qty=amount,
                        reason=("Void return: " + reason)[:100], changed_by=actor))
            order_id, session_id = item.order_id, item.order.customer_session_id
            record_action(item.menu_item, "void_return" if return_stock and allocations else "void_no_return",
                          1, reason, actor, key, item.id)
            if item.quantity > 1:
                item.quantity -= 1
            else:
                db.session.delete(item)
            self.repo.commit()
        except StockError as exc:
            db.session.rollback()
            return {"error": exc.code, "message": str(exc)}, exc.status
        except Exception:
            db.session.rollback()
            raise
        emit_inventory_update("stock_change", {"order_id": order_id})
        self.notifier.order_status_changed({"order_id": order_id, "session_id": session_id, "status": "voided"})
        return {"message": "One item cancelled." + (" Stock returned." if return_stock and allocations else " No stock returned.")}

    def toggle_order_item_status(self, item_id: int) -> dict[str, Any] | tuple[dict[str, Any], int]:
        item = self.repo.get_order_item(item_id)
        if not item:
            return {"error": "Item not found"}, 404
        if _item_is_ready(item.status):
            item.status = "preparing"
        else:
            item.status = "done"
        self.repo.commit()
        self.notifier.order_status_changed(
            {"order_id": item.order_id, "item_id": item.id, "status": item.status}
        )
        return {"message": "Item status updated", "item_id": item_id, "status": item.status}
