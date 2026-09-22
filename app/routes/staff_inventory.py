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
