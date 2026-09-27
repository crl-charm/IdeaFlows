from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request, session

from app.repositories.inventory_repository import InventoryRepository
from app.services.inventory_service import InventoryService
from app.utils.auth import login_required
from app.core.idempotency import idempotent_request

staff_inventory_bp = Blueprint("staff_inventory", __name__, url_prefix="/inventory")

_service = InventoryService(repo=InventoryRepository())


@staff_inventory_bp.route("", methods=["GET"])
@login_required
def view_inventory() -> str:
    from app.services.stock_management import kitchen_access
    return render_template("staff/inventory.html", can_manage_kitchen=kitchen_access(session.get("user_id")))


@staff_inventory_bp.route("/api/items", methods=["GET"])
@login_required
def api_list_items() -> tuple:
    items = _service.list_all()
    return jsonify({"success": True, "data": items}), 200


@staff_inventory_bp.route("/api/dashboard-items", methods=["GET"])
@login_required
def api_dashboard_items() -> tuple:
    return jsonify({"success": True, **_service.build_dashboard_snapshot()}), 200


@staff_inventory_bp.route("/api/menu-items/<int:menu_id>/action", methods=["POST"])
@login_required
@idempotent_request("staff-inventory-stock-action")
def stock_action(menu_id):
    from app import db
    from app.services.stock_management import change_stock, kitchen_access
    from app.services.menu_availability import StockError
    from app.core.socketio_handlers import emit_inventory_update
    actor = session.get("user_id")
    if not kitchen_access(actor):
        return jsonify(error="Only the owner or a cook can change kitchen stock."), 403
    try:
        result = change_stock(menu_id, request.get_json(silent=True) or {}, actor,
            request.headers.get("Idempotency-Key"), admin=session.get("role") == "admin")
    except StockError as exc:
        db.session.rollback()
        return jsonify(error=exc.code, message=str(exc)), exc.status
    if not result.get("duplicate"):
        emit_inventory_update("stock_change", {"menu_item_id": menu_id})
    return jsonify(result)


@staff_inventory_bp.route("/api/ingredients/<int:menu_id>/stock", methods=["PATCH"])
@login_required
@idempotent_request("staff-ingredient-stock-count")
def set_ingredient_stock(menu_id):
    from app import db
    from app.models import MenuItem, InventoryItem
    from app.services.stock_management import kitchen_access
    from app.core.socketio_handlers import emit_inventory_update
    from app.utils.inventory_helpers import is_ingredient_category

    if not kitchen_access(session.get("user_id")):
        return jsonify(error="Only the owner or a cook can update ingredients."), 403
    ingredient = db.session.get(MenuItem, menu_id)
    if not ingredient or ingredient.status == "deleted" or not is_ingredient_category(ingredient.category):
        return jsonify(error="Ingredient not found."), 404
    rows = InventoryItem.query.filter_by(menu_item_id=menu_id).all()
    if not rows:
        return jsonify(error="Ask the owner to add this ingredient and its unit first."), 400
    if len(rows) != 1:
        return jsonify(error="Duplicate stock records need owner review."), 409
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="Enter a valid stock quantity."), 400
    result = _service.update_stock(rows[0].id, data.get("quantity"), "Manual count", session.get("user_id"),
                                   unit=data.get("unit"), conversion_ratio=data.get("conversion_ratio"))
    if isinstance(result, tuple):
        return jsonify(result[0]), result[1]
    emit_inventory_update("stock_change", {"item_id": rows[0].id})
    return jsonify(result)


@staff_inventory_bp.route("/api/history", methods=["GET"])
@login_required
def stock_history():
    from app.services.stock_management import kitchen_access
    from app.models.inventory import InventoryAction
    from app.models import User
    if not kitchen_access(session.get("user_id")):
        return jsonify(error="Forbidden"), 403
    from app import db
    rows = db.session.query(InventoryAction, User.full_name).outerjoin(User, User.id == InventoryAction.changed_by).order_by(InventoryAction.id.desc()).limit(100).all()
    return jsonify(data=[dict(item=a.item_name, menu_item_id=a.menu_item_id, action=a.action, quantity=float(a.quantity),
        reason=a.reason, actor=name or "System", at=a.created_at.isoformat()+"Z") for a, name in rows])


@staff_inventory_bp.route("/api/menu-items/<int:menu_id>/history", methods=["GET"])
@login_required
def meal_history(menu_id):
    from sqlalchemy import literal, select, union_all
    from app import db
    from app.models import InventoryItem, InventoryLog, MenuItem, User
    from app.models.inventory import InventoryAction
    from app.services.stock_management import kitchen_access
    from app.utils.inventory_helpers import is_ingredient_category

    if not kitchen_access(session.get("user_id")):
        return jsonify(error="Forbidden"), 403
    meal = db.session.get(MenuItem, menu_id)
    if not meal or meal.status == "deleted" or is_ingredient_category(meal.category):
        return jsonify(error="Meal not found."), 404
    try:
        page = int(request.args.get("page", "1"))
        if not 1 <= page <= 10000:
            raise ValueError
    except ValueError:
        return jsonify(error="Choose a valid history page."), 400

    logs = select(
        InventoryLog.id.label("id"), InventoryLog.created_at.label("at"),
        InventoryLog.change_qty.label("quantity"), InventoryLog.reason.label("reason"),
        InventoryLog.changed_by.label("actor_id"), literal("log").label("source"),
    ).join(InventoryItem, InventoryItem.id == InventoryLog.inventory_item_id).where(
        InventoryItem.menu_item_id == menu_id)
    no_return_voids = select(
        InventoryAction.id.label("id"), InventoryAction.created_at.label("at"),
        literal(0).label("quantity"), InventoryAction.reason.label("reason"),
        InventoryAction.changed_by.label("actor_id"), literal("void_no_return").label("source"),
    ).where(InventoryAction.menu_item_id == menu_id, InventoryAction.action == "void_no_return")
    events = union_all(logs, no_return_voids).subquery()
    rows = db.session.execute(select(events).order_by(
        events.c.at.desc(), events.c.id.desc(), events.c.source.desc()
    ).offset((page - 1) * 30).limit(31)).mappings().all()
    actors = {user.id: user.full_name or user.username for user in User.query.filter(
        User.id.in_({row["actor_id"] for row in rows if row["actor_id"] is not None})
    ).all()}
    data = []
    for row in rows[:30]:
        reason = row["reason"]
        action = ("Void without stock return" if row["source"] == "void_no_return" else
                  "Order" if reason.startswith("Sale:") else
                  "Void return" if reason.startswith("Void return:") else
                  "Set servings" if reason.startswith(("Set servings:", "Manual serving estimate")) else
                  "Stock change")
        data.append(dict(action=action, quantity=float(row["quantity"]), reason=reason,
            actor=actors.get(row["actor_id"], "System"), at=row["at"].isoformat() + "Z"))
    return jsonify(data=data, next_page=page + 1 if len(rows) > 30 else None)


@staff_inventory_bp.route("/api/menu-items/<int:menu_id>/last-batch", methods=["GET"])
@login_required
def last_batch(menu_id):
    from app.services.stock_management import kitchen_access
    from app.models.inventory import InventoryAction
    if not kitchen_access(session.get("user_id")):
        return jsonify(error="Forbidden"), 403
    batch = InventoryAction.query.filter_by(menu_item_id=menu_id, action="add").order_by(InventoryAction.id.desc()).first()
    return jsonify(quantity=int(batch.quantity) if batch else None)


@staff_inventory_bp.route("/api/prepared-summary", methods=["GET"])
@login_required
def prepared_summary():
    from sqlalchemy import func
    from app.models import MenuItem, InventoryItem
    from app.models.inventory import InventoryAction, OrderInventoryAllocation
    from app.services.stock_management import kitchen_access
    from app import db
    if not kitchen_access(session.get("user_id")):
        return jsonify(error="Forbidden"), 403
    items = MenuItem.query.filter_by(inventory_mode="prepared").filter(MenuItem.status != "deleted").order_by(MenuItem.name).all()
    ids = [item.id for item in items]
    if not ids:
        return jsonify(data=[])
    stocks = {row.menu_item_id: row.stock_qty for row in InventoryItem.query.filter(InventoryItem.menu_item_id.in_(ids)).all()}
    movements = {(menu_id, action): quantity for menu_id, action, quantity in db.session.query(
        InventoryAction.menu_item_id, InventoryAction.action, func.sum(InventoryAction.quantity)
    ).filter(InventoryAction.menu_item_id.in_(ids)).group_by(InventoryAction.menu_item_id, InventoryAction.action).all()}
    ordered = {menu_id: quantity for menu_id, quantity in db.session.query(
        OrderInventoryAllocation.menu_item_id, func.sum(OrderInventoryAllocation.quantity_deducted)
    ).filter(OrderInventoryAllocation.menu_item_id.in_(ids), OrderInventoryAllocation.inventory_mode == "prepared")
      .group_by(OrderInventoryAllocation.menu_item_id).all()}
    return jsonify(data=[dict(name=item.name,
        prepared=float(movements.get((item.id, "add"), 0)),
        ordered=float(ordered.get(item.id, 0)),
        voided=float(movements.get((item.id, "void_return"), 0) + movements.get((item.id, "void_no_return"), 0)),
        wasted=float(-movements.get((item.id, "waste"), 0) - movements.get((item.id, "sold_out"), 0)),
        remaining=float(stocks.get(item.id, 0))) for item in items])
