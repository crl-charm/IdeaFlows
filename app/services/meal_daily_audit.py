"""Daily serving reconciliation from durable stock and order history."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import and_, case, func, or_

from app import db
from app.models import CustomerSession, InventoryItem, InventoryLog, MenuItem, Order, OrderItem, Transaction, User
from app.models.inventory import InventoryAction, OrderInventoryAllocation
from app.utils.dates import manila_day_bounds
from app.utils.inventory_helpers import is_ingredient_category


ZERO = Decimal("0")
SERVING_MODES = {"prepared", "recipe"}


def _qty(value):
    return int(value or 0)


def _stock_number(value):
    number = Decimal(str(value or 0))
    return int(number) if number == number.to_integral_value() else float(number)


def _actor_names(ids):
    if not ids:
        return {}
    return {user.id: user.full_name or user.username for user in User.query.filter(User.id.in_(ids)).all()}


def _actor_label(names, user_id):
    return names.get(user_id, f"Account #{user_id}" if user_id else "System")


def _stock_rows(meal_ids=None):
    query = db.session.query(MenuItem, InventoryItem).outerjoin(
        InventoryItem, InventoryItem.menu_item_id == MenuItem.id
    ).filter(or_(MenuItem.status.is_(None), MenuItem.status != "deleted"))
    if meal_ids is not None:
        query = query.filter(MenuItem.id.in_(meal_ids))
    return [(meal, stock) for meal, stock in query.all()
            if not is_ingredient_category(meal.category)
            and (meal.inventory_mode in SERVING_MODES or meal.inventory_mode == "untracked"
                 or (meal.inventory_mode is None and (stock is None or stock.unit == "servings")))]


def meal_day_summaries(day: date, meal_ids=None):
    """One bounded set of aggregate queries for all meal cards."""
    start, end = manila_day_bounds(day)
    rows = _stock_rows(meal_ids)
    stock_counts = Counter(meal.id for meal, stock in rows if stock)
    duplicate_stock = {meal_id for meal_id, count in stock_counts.items() if count > 1}
    tracked = {meal.id: stock for meal, stock in rows if stock and stock.unit == "servings"}
    result = {meal.id: dict(meal_id=meal.id, configured=False,
        opening=0, added=0, placed=0, cancelled=0, ordered=0, available=0,
        remaining=0, other_change=0, not_returned=0, later_cancellations=0,
        untracked_orders=False,
        history_complete=False)
        for meal, _ in rows}
    if not tracked:
        return result
    ids = list(tracked)
    stock_ids = [row.id for row in tracked.values()]
    lifetime_logs = {stock_id: (total, first_at) for stock_id, total, first_at in db.session.query(
        InventoryLog.inventory_item_id, func.sum(InventoryLog.change_qty),
        func.min(InventoryLog.created_at)).filter(
        InventoryLog.inventory_item_id.in_(stock_ids)).group_by(
        InventoryLog.inventory_item_id).all()}

    # Reverse durable deltas from today's actual stock. This also reconstructs
    # the closing stock of an older Manila day without a midnight reset job.
    logs = db.session.query(
        InventoryLog.inventory_item_id,
        func.sum(InventoryLog.change_qty),
        func.sum(case((InventoryLog.created_at >= end, InventoryLog.change_qty), else_=0)),
        func.sum(case((and_(InventoryLog.created_at < end,
                            InventoryLog.reason.like("Sale:%")), -InventoryLog.change_qty), else_=0)),
        func.sum(case((and_(InventoryLog.created_at < end,
                            InventoryLog.reason.like("Void return:%")), InventoryLog.change_qty), else_=0)),
        func.sum(case((and_(InventoryLog.created_at < end,
                            InventoryLog.reason.like("Add:%")), InventoryLog.change_qty), else_=0)),
        func.sum(case((and_(InventoryLog.created_at < end,
                            InventoryLog.reason == "Setup: Menu item created"), InventoryLog.change_qty), else_=0)),
    ).filter(InventoryLog.inventory_item_id.in_(stock_ids), InventoryLog.created_at >= start
    ).group_by(InventoryLog.inventory_item_id).all()
    log_totals = {stock_id: tuple(Decimal(str(value or 0)) for value in values)
                  for stock_id, *values in logs}

    additions = dict(db.session.query(InventoryAction.menu_item_id, func.sum(InventoryAction.quantity)).filter(
        InventoryAction.menu_item_id.in_(ids), InventoryAction.action == "add",
        InventoryAction.created_at >= start, InventoryAction.created_at < end,
    ).group_by(InventoryAction.menu_item_id).all())
    placed = dict(db.session.query(OrderInventoryAllocation.menu_item_id,
        func.sum(OrderInventoryAllocation.ordered_units)).join(
        Order, Order.id == OrderInventoryAllocation.order_id
    ).filter(OrderInventoryAllocation.menu_item_id.in_(ids),
        OrderInventoryAllocation.unit == "servings", Order.created_at >= start,
        Order.created_at < end).group_by(OrderInventoryAllocation.menu_item_id).all())
    cancelled = dict(db.session.query(InventoryAction.menu_item_id,
        func.sum(InventoryAction.quantity)).join(
        OrderInventoryAllocation, and_(
            OrderInventoryAllocation.order_item_id == InventoryAction.order_item_id,
            OrderInventoryAllocation.menu_item_id == InventoryAction.menu_item_id,
        )).join(Order, Order.id == OrderInventoryAllocation.order_id).filter(
        InventoryAction.menu_item_id.in_(ids),
        InventoryAction.action.in_(("void_return", "void_no_return")),
        OrderInventoryAllocation.unit == "servings",
        Order.created_at >= start, Order.created_at < end,
    ).group_by(InventoryAction.menu_item_id).all())
    later_cancelled = dict(db.session.query(InventoryAction.menu_item_id,
        func.sum(InventoryAction.quantity)).join(
        OrderInventoryAllocation, and_(
            OrderInventoryAllocation.order_item_id == InventoryAction.order_item_id,
            OrderInventoryAllocation.menu_item_id == InventoryAction.menu_item_id,
        )).join(Order, Order.id == OrderInventoryAllocation.order_id).filter(
        InventoryAction.menu_item_id.in_(ids),
        InventoryAction.action.in_(("void_return", "void_no_return")),
        OrderInventoryAllocation.unit == "servings",
        Order.created_at >= start, Order.created_at < end,
        InventoryAction.created_at >= end,
    ).group_by(InventoryAction.menu_item_id).all())
    no_return = dict(db.session.query(InventoryAction.menu_item_id,
        func.sum(InventoryAction.quantity)).filter(
        InventoryAction.menu_item_id.in_(ids), InventoryAction.action == "void_no_return",
        InventoryAction.created_at >= start, InventoryAction.created_at < end,
    ).group_by(InventoryAction.menu_item_id).all())
    returned = dict(db.session.query(InventoryAction.menu_item_id,
        func.sum(InventoryAction.quantity)).filter(
        InventoryAction.menu_item_id.in_(ids), InventoryAction.action == "void_return",
        InventoryAction.created_at >= start, InventoryAction.created_at < end,
    ).group_by(InventoryAction.menu_item_id).all())
    untracked_orders = {meal_id for (meal_id,) in db.session.query(OrderItem.menu_item_id).join(
        Order, Order.id == OrderItem.order_id
    ).outerjoin(OrderInventoryAllocation, and_(
        OrderInventoryAllocation.order_item_id == OrderItem.id,
        OrderInventoryAllocation.menu_item_id == OrderItem.menu_item_id,
        OrderInventoryAllocation.unit == "servings",
    )).filter(OrderItem.menu_item_id.in_(ids), Order.created_at >= start,
        Order.created_at < end, OrderInventoryAllocation.id.is_(None)
    ).distinct().all()}

    for meal_id, stock in tracked.items():
        after_start, after_end, sale_logs, return_logs, add_logs, setup_logs = log_totals.get(
            stock.id, (ZERO,) * 6)
        current = Decimal(str(stock.stock_qty))
        opening = current - after_start
        closing = current - after_end
        day_delta = after_start - after_end
        added = Decimal(str(additions.get(meal_id) or 0)) + setup_logs
        ordered = _qty(placed.get(meal_id))
        voided = _qty(cancelled.get(meal_id))
        other_change = day_delta - added + sale_logs - return_logs
        stock_existed = stock.created_at is None or stock.created_at < end
        complete = (opening >= 0 and closing >= 0 and voided <= ordered
            and sale_logs == ordered and return_logs == _qty(returned.get(meal_id))
            and add_logs == Decimal(str(additions.get(meal_id) or 0))
            and current == Decimal(str(lifetime_logs.get(stock.id, (0, None))[0] or 0))
            and opening + added >= ordered and other_change <= 0
            and meal_id not in duplicate_stock and meal_id not in untracked_orders
            and all(value == value.to_integral_value() for value in
                (opening, closing, added, other_change))
            and stock.created_at is not None and stock_existed)
        first_log = lifetime_logs.get(stock.id, (0, None))[1]
        configured = (stock_existed and meal_id not in duplicate_stock
            and ((first_log is not None and first_log < end) or opening > 0))
        result[meal_id].update(configured=configured,
            opening=_stock_number(opening), added=_stock_number(added),
            placed=ordered, cancelled=voided, ordered=ordered - voided,
            available=_stock_number(opening + added), remaining=_stock_number(closing),
            other_change=_stock_number(other_change), not_returned=_qty(no_return.get(meal_id)),
            later_cancellations=_qty(later_cancelled.get(meal_id)),
            untracked_orders=meal_id in untracked_orders, history_complete=complete)
    return result


def meal_day_detail(meal_id: int, day: date, page: int):
    summary = meal_day_summaries(day, [meal_id]).get(meal_id)
    if summary is None:
        return None
    start, end = manila_day_bounds(day)
    meal = db.session.get(MenuItem, meal_id)
    allocations = db.session.query(OrderInventoryAllocation, Order, CustomerSession).join(
        Order, Order.id == OrderInventoryAllocation.order_id
    ).join(CustomerSession, CustomerSession.id == Order.customer_session_id).filter(
        OrderInventoryAllocation.menu_item_id == meal_id,
        OrderInventoryAllocation.unit == "servings", Order.created_at >= start,
        Order.created_at < end,
    ).order_by(Order.created_at.desc(), OrderInventoryAllocation.id.desc()
    ).offset((page - 1) * 50).limit(51).all()
    shown = allocations[:50]
    order_item_ids = [allocation.order_item_id for allocation, _, _ in shown]
    voids = defaultdict(lambda: {"returned": 0, "not_returned": 0, "events": []})
    if order_item_ids:
        for action in InventoryAction.query.filter(
            InventoryAction.order_item_id.in_(order_item_ids),
            InventoryAction.action.in_(("void_return", "void_no_return"))).all():
            voids[action.order_item_id]["returned" if action.action == "void_return" else "not_returned"] += _qty(action.quantity)
            voids[action.order_item_id]["events"].append(action)
    handler_ids = {order.handled_by for _, order, _ in shown if order.handled_by}
    actors = _actor_names(handler_ids | {action.changed_by for entry in voids.values()
        for action in entry["events"] if action.changed_by})
    session_ids = {customer.id for _, _, customer in shown}
    paid_sessions = {tx.session_id for tx in Transaction.query.filter(
        Transaction.session_id.in_(session_ids), Transaction.is_voided.is_(False)).all()} if session_ids else set()
    orders = []
    for allocation, order, customer in shown:
        cancelled = (voids[allocation.order_item_id]["returned"]
            + voids[allocation.order_item_id]["not_returned"])
        orders.append(dict(order_id=order.id, order_item_id=allocation.order_item_id,
            at=order.created_at.isoformat() + "Z", customer=customer.customer_name,
            location=customer.space_type.name if customer.space_type else "Unknown",
            handler=_actor_label(actors, order.handled_by),
            placed=_qty(allocation.ordered_units), cancelled=cancelled,
            ordered=_qty(allocation.ordered_units) - cancelled,
            not_returned=voids[allocation.order_item_id]["not_returned"],
            cancellations=[dict(at=action.created_at.isoformat() + "Z",
                quantity=_qty(action.quantity), returned=action.action == "void_return",
                reason=action.reason, actor=_actor_label(actors, action.changed_by))
                for action in sorted(voids[allocation.order_item_id]["events"],
                    key=lambda row: (row.created_at, row.id))],
            checkout_status="Checked out" if customer.id in paid_sessions else "Not checked out"))

    actions = InventoryAction.query.filter(
        InventoryAction.menu_item_id == meal_id,
        InventoryAction.created_at >= start, InventoryAction.created_at < end,
    ).order_by(InventoryAction.created_at, InventoryAction.id).all()
    stock = InventoryItem.query.filter_by(menu_item_id=meal_id, unit="servings").first()
    logs = InventoryLog.query.filter(
        InventoryLog.inventory_item_id == stock.id,
        InventoryLog.created_at >= start, InventoryLog.created_at < end,
    ).order_by(InventoryLog.created_at, InventoryLog.id).all() if stock else []
    names = _actor_names({row.changed_by for row in actions + logs if row.changed_by})
    batches = [dict(at=row.created_at.isoformat() + "Z", quantity=_qty(row.quantity),
        actor=_actor_label(names, row.changed_by), reason=row.reason)
        for row in actions if row.action == "add"]
    batches += [dict(at=row.created_at.isoformat() + "Z", quantity=_stock_number(row.change_qty),
        actor=_actor_label(names, row.changed_by), reason=row.reason)
        for row in logs if row.reason == "Setup: Menu item created" and row.change_qty > 0]
    batches.sort(key=lambda row: row["at"])
    movements = [dict(at=row.created_at.isoformat() + "Z", quantity=_stock_number(row.change_qty),
        actor=_actor_label(names, row.changed_by), reason=row.reason)
        for row in logs if not row.reason.startswith(("Sale:", "Add:"))
        and row.reason != "Setup: Menu item created"]
    movements += [dict(at=row.created_at.isoformat() + "Z", quantity=0,
        actor=_actor_label(names, row.changed_by), reason="Void without stock return: " + row.reason)
        for row in actions if row.action == "void_no_return"]
    movements.sort(key=lambda row: row["at"])
    return dict(meal_id=meal_id, meal_name=meal.name, date=day.isoformat(),
        summary=summary, batches=batches, orders=orders, movements=movements,
        next_page=page + 1 if len(allocations) > 50 else None)
