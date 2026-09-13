from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request, render_template, session

from app.core import get_notifier
from app.repositories.inventory_repository import InventoryRepository
from app.services.inventory_service import InventoryService
from app.utils.auth import admin_required
from app.utils.inventory_helpers import is_ingredient_category
from app.models.menu_item import MenuItem
from app import db, csrf
from app.core.socketio_handlers import emit_inventory_update
from app.core.idempotency import idempotent_request

logger = logging.getLogger(__name__)

inventory_bp = Blueprint("inventory", __name__, url_prefix="/admin/inventory")

_service = InventoryService(repo=InventoryRepository())


def _inventory_log_user_id(session_user_id: int | None) -> int | None:
    if not session_user_id:
        return None
    from app.models.user import User

    return session_user_id if User.query.get(session_user_id) else None


@inventory_bp.route("", methods=["GET"])
@admin_required
def list_items() -> str:
    return render_template("admin/inventory.html")


@inventory_bp.route("/api/items", methods=["GET"])
@admin_required
def api_list_items() -> tuple:
    items = _service.list_all()
    return jsonify({"success": True, "data": items}), 200


@inventory_bp.route("/api/items", methods=["POST"])
@admin_required
@csrf.exempt
@idempotent_request("admin-create-inventory-item")
def api_create_item() -> tuple:
    data = request.get_json()
    menu_item_id = data.get("menu_item_id")
    ingredient_name = (data.get("ingredient_name") or "").strip()
    if not menu_item_id and ingredient_name:
        # Only match existing items if they are categorized as raw ingredients
        existing_items = MenuItem.query.filter(MenuItem.status != "deleted", MenuItem.name.ilike(ingredient_name)).all()
        matching_ing = None
        for item in existing_items:
            if is_ingredient_category(item.category):
                matching_ing = item
                break
        
        if matching_ing:
            menu_item_id = matching_ing.id
        else:
            created = MenuItem(name=ingredient_name, price=0, category="ingredient", is_available=True)
            db.session.add(created)
            db.session.flush()
            menu_item_id = created.id
    if not menu_item_id:
        return jsonify({"success": False, "error": "Select an item or provide ingredient_name"}), 400
    result = _service.create(
        menu_item_id=menu_item_id,
        stock_qty=float(data.get("stock_qty", 0)),
        low_stock_threshold=int(data.get("low_stock_threshold", 10)),
        unit=data.get("unit", "pieces"),
    )
    if result.get("success"):
        emit_inventory_update('create', result.get("data", {}))
    return jsonify(result), 201


@inventory_bp.route("/api/items/<int:item_id>/stock", methods=["PATCH"])
@admin_required
@csrf.exempt
@idempotent_request("admin-update-inventory-stock")
def api_update_stock(item_id: int) -> tuple:
    data = request.get_json()
    result = _service.update_stock(
        item_id=item_id,
        new_qty=float(data.get("new_qty")),
        reason=data.get("reason", "Manual adjustment"),
        user_id=session.get("user_id"),
    )
    if isinstance(result, tuple):
        return jsonify(result[0]), result[1]
    if result.get("success"):
        emit_inventory_update('stock_change', {'item_id': item_id, 'new_qty': float(data.get("new_qty"))})
    return jsonify(result), 200


@inventory_bp.route("/api/menu-items/<int:menu_item_id>/stock", methods=["PATCH"])
@admin_required
@csrf.exempt
@idempotent_request("admin-update-menu-item-stock")
def api_update_stock_by_menu_item(menu_item_id: int) -> tuple:
    data = request.get_json()
    result = _service.update_stock(
        item_id=None,
        menu_item_id=menu_item_id,
        new_qty=float(data.get("new_qty")),
        reason=data.get("reason", "Manual adjustment"),
        user_id=session.get("user_id"),
    )
    if isinstance(result, tuple):
        return jsonify(result[0]), result[1]
    if result.get("success"):
        inv_id = result.get("data", {}).get("inventory_item_id")
        emit_inventory_update('stock_change', {'item_id': inv_id, 'new_qty': float(data.get("new_qty"))})
    return jsonify(result), 200


@inventory_bp.route("/api/items/<int:item_id>/logs", methods=["GET"])
@admin_required
def api_get_logs(item_id: int) -> tuple:
    logs = _service.get_logs(item_id)
    return jsonify({"success": True, "data": logs}), 200


@inventory_bp.route("/api/low-stock", methods=["GET"])
@admin_required
def api_low_stock() -> tuple:
    items = _service.get_low_stock()
    return jsonify({"success": True, "data": items}), 200


@inventory_bp.route("/api/items/<int:item_id>", methods=["DELETE"])
@admin_required
@csrf.exempt
@idempotent_request("admin-delete-inventory-item")
def api_delete_item(item_id: int) -> tuple:
    result = _service.delete(item_id)
    if isinstance(result, tuple):
        return jsonify(result[0]), result[1]
    if result.get("success"):
        emit_inventory_update('delete', {'item_id': item_id})
    return jsonify(result), 200


@inventory_bp.route("/api/direct-stock", methods=["GET"])
@admin_required
def api_direct_stock() -> tuple:
    return jsonify({"success": True, "data": _service.build_direct_stock_items()}), 200


@inventory_bp.route("/api/recipe-inventory", methods=["GET"])
@admin_required
def api_recipe_inventory() -> tuple:
    return jsonify({"success": True, "data": _service.build_recipe_inventory_items()}), 200


@inventory_bp.route("/api/dashboard-items", methods=["GET"])
@admin_required
def api_dashboard_items() -> tuple:
    return jsonify({"success": True, **_service.build_dashboard_snapshot()}), 200


@inventory_bp.route("/api/recipes/<int:menu_item_id>", methods=["GET"])
@admin_required
def get_recipe(menu_item_id: int) -> tuple:
    return jsonify({"success": True, "data": _service.build_recipe_detail(menu_item_id)}), 200


@inventory_bp.route("/api/recipes", methods=["POST"])
@admin_required
@csrf.exempt
@idempotent_request("admin-add-recipe-ingredient")
def add_recipe_ingredient() -> tuple:
    from app.models.menu_item import MenuItemIngredient

    data = request.get_json() or {}
    menu_item_id = data.get("menu_item_id")
    ingredient_item_id = data.get("ingredient_item_id")

    # Log submitted IDs (Task 2)
    logger.info(
        "add_recipe_ingredient submitted menu_item_id=%s ingredient_item_id=%s",
        menu_item_id,
        ingredient_item_id,
    )

    if not menu_item_id or not ingredient_item_id:
        return jsonify({
            "success": False,
            "error": "MISSING_FIELDS",
            "message": "Missing menu_item_id or ingredient_item_id",
        }), 400

    if menu_item_id == ingredient_item_id:
        return jsonify({
            "success": False,
            "error": "INVALID_MAPPING",
            "message": "A meal cannot be linked to itself as an ingredient",
        }), 400

    # 1. Menu item exists validation
    meal = MenuItem.query.get(menu_item_id)
    if not meal or meal.status == "deleted":
        return jsonify({
            "success": False,
            "error": "MENU_ITEM_NOT_FOUND",
            "message": "Menu item not found.",
        }), 404

    if is_ingredient_category(meal.category):
        return jsonify({
            "success": False,
            "error": "INVALID_MEAL",
            "message": "menu_item_id must be a sellable meal",
        }), 400

    # 2. Ingredient item exists validation
    ingredient = MenuItem.query.get(ingredient_item_id)
    if not ingredient or ingredient.status == "deleted":
        return jsonify({
            "success": False,
            "error": "INGREDIENT_NOT_FOUND",
            "message": "Ingredient item not found.",
        }), 404

    # 3. Ingredient category validation
    if not is_ingredient_category(ingredient.category):
        logger.info(
            "add_recipe_ingredient invalid category menu_item_id=%s ingredient_item_id=%s category=%r",
            menu_item_id,
            ingredient_item_id,
            ingredient.category,
        )
        return jsonify({
            "success": False,
            "error": "INVALID_INGREDIENT",
            "message": "Selected item is not categorized as an ingredient.",
        }), 400

    # Log final validated IDs and stored category (Task 2)
    logger.info(
        "add_recipe_ingredient final validated menu_item_id=%s ingredient_item_id=%s",
        menu_item_id,
        ingredient_item_id,
    )
    logger.info(
        "add_recipe_ingredient stored ingredient category=%s",
        ingredient.category,
    )

    try:
        qty = float(data.get("quantity_required", 1.0))
        if qty <= 0:
            return jsonify({
                "success": False,
                "error": "INVALID_QUANTITY",
                "message": "Quantity required must be greater than zero",
            }), 400
    except (ValueError, TypeError):
        return jsonify({
            "success": False,
            "error": "INVALID_QUANTITY",
            "message": "Quantity required must be a valid number",
        }), 400

    unit = data.get("unit")
    if unit:
        unit = str(unit).strip().lower()
        VALID_UNITS = {"pieces", "klg", "grams", "trays", "packs", "liters", "ml"}
        if unit not in VALID_UNITS:
            return jsonify({
                "success": False,
                "error": "INVALID_UNIT",
                "message": f"Invalid unit. Must be one of: {', '.join(VALID_UNITS)}",
            }), 400
    else:
        unit = None

    try:
        conversion_ratio = float(data.get("conversion_ratio", 1.0))
        if conversion_ratio <= 0:
            return jsonify({
                "success": False,
                "error": "INVALID_RATIO",
                "message": "Conversion ratio must be greater than zero",
            }), 400
    except (ValueError, TypeError):
        return jsonify({
            "success": False,
            "error": "INVALID_RATIO",
            "message": "Conversion ratio must be a valid number",
        }), 400

    inv_item = _service.ensure_inventory_row(int(ingredient_item_id))

    # 4. Recipe mapping does not already exist validation
    existing = MenuItemIngredient.query.filter_by(
        menu_item_id=menu_item_id,
        ingredient_item_id=ingredient_item_id,
    ).first()

    if existing:
        logger.info(
            "add_recipe_ingredient duplicate check failed: mapping already exists menu_item_id=%s ingredient_item_id=%s",
            menu_item_id,
            ingredient_item_id,
        )
        return jsonify({
            "success": False,
            "error": "MAPPING_ALREADY_EXISTS",
            "message": "Recipe mapping already exists.",
        }), 400

    # 5. Create the mapping
    new_map = MenuItemIngredient(
        menu_item_id=menu_item_id,
        ingredient_item_id=ingredient_item_id,
        quantity_required=qty,
        unit=unit,
        conversion_ratio=conversion_ratio,
    )
    db.session.add(new_map)

    from app.models.user import User
    from app.models.inventory import InventoryLog
    user = User.query.get(session.get("user_id")) if session.get("user_id") else None
    username = user.username if user else "System"
    log_reason = f"{username} linked to {meal.name}: req={qty} {unit or 'pcs'} (ratio {conversion_ratio:.4f})"
    log_reason = log_reason[:100]
    log = InventoryLog(
        inventory_item_id=inv_item.id,
        change_qty=0.00,
        reason=log_reason,
        changed_by=_inventory_log_user_id(session.get("user_id")),
    )
    db.session.add(log)

    try:
        db.session.commit()
        # Log successful creation (Task 2)
        logger.info(
            "add_recipe_ingredient mapping successfully created menu_item_id=%s ingredient_item_id=%s",
            menu_item_id,
            ingredient_item_id,
        )
        return jsonify({
            "success": True,
            "message": "Ingredient added to recipe.",
        }), 200
    except Exception as e:
        db.session.rollback()
        logger.exception("add_recipe_ingredient failed")
        return jsonify({"success": False, "error": "SERVER_ERROR", "message": str(e)}), 500


@inventory_bp.route("/api/recipes/<int:recipe_id>", methods=["DELETE"])
@admin_required
@csrf.exempt
@idempotent_request("admin-delete-recipe-ingredient")
def delete_recipe_ingredient(recipe_id: int) -> tuple:
    from app.models.menu_item import MenuItemIngredient

    mapping = MenuItemIngredient.query.get(recipe_id)
    if not mapping:
        return jsonify({"success": False, "error": "Recipe component not found"}), 404
    try:
        db.session.delete(mapping)
        db.session.commit()
        return jsonify({"success": True}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@inventory_bp.route("/api/ingredients/<int:menu_item_id>", methods=["DELETE"])
@admin_required
@csrf.exempt
@idempotent_request("admin-delete-raw-ingredient")
def api_delete_ingredient(menu_item_id: int) -> tuple:
    result = _service.delete_raw_ingredient(menu_item_id)
    if isinstance(result, tuple):
        return jsonify(result[0]), result[1]
    if result.get("success"):
        emit_inventory_update("delete", {"menu_item_id": menu_item_id})
    return jsonify(result), 200


@inventory_bp.route("/api/ingredients", methods=["GET"])
@admin_required
def list_ingredients() -> tuple:
    q = request.args.get("q")
    data = _service.list_ingredients_for_picker(q)
    return jsonify({"success": True, "data": data}), 200


@inventory_bp.route("/api/meals", methods=["GET"])
@admin_required
def list_meals() -> tuple:
    q = request.args.get("q", "").strip()
    query = MenuItem.query.filter(MenuItem.status != "deleted")
    if q:
        query = query.filter(MenuItem.name.ilike(f"%{q}%"))
    meals = [
        m for m in query.order_by(MenuItem.name).all()
        if not is_ingredient_category(m.category)
    ]
    data = [{"id": m.id, "name": m.name} for m in meals]
    return jsonify({"success": True, "data": data}), 200
