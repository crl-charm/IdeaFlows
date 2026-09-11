from __future__ import annotations

from flask import Blueprint, jsonify, request, render_template, current_app
from flask.views import MethodView
import os
import uuid
from werkzeug.utils import secure_filename
import logging

from app.repositories.menu_repository import MenuRepository
from app.services.menu_service import MenuService
from app.utils.auth import admin_required
from app.utils.uploads import validate_and_save_image, delete_old_image
from app.core.socketio_handlers import emit_menu_update
from app.core.cache import get_or_set_json, invalidate_menu_cache
from functools import wraps

# Import CSRF protection from app module
from app import csrf

csrf_exempt = csrf.exempt

menu_bp = Blueprint("menu", __name__, url_prefix="/admin/menu")

_service = MenuService(repo=MenuRepository())

logger = logging.getLogger(__name__)

def get_valid_categories():
    try:
        from app.models.menu_category import MenuCategory
        return get_or_set_json(
            "menu:categories",
            lambda: [c.name for c in MenuCategory.query.order_by(MenuCategory.id).all()],
        )
    except Exception as e:
        logger.warning(f"Error fetching categories from DB: {e}")
        return ["Main Dish", "Snack", "Beverages"]



@menu_bp.route("", methods=["GET"])
@admin_required
def menu_page() -> str:
    items = _service.list_all()
    return render_template("admin/menu.html", items=items, categories=get_valid_categories())


@menu_bp.route("/api/items", methods=["GET"])
@admin_required
@csrf.exempt
def api_list_items() -> tuple:
    items = _service.list_available()
    return jsonify({"success": True, "data": items}), 200


@menu_bp.route("/api/items/all", methods=["GET"])
@admin_required
@csrf.exempt
def api_all_items() -> tuple:
    items = _service.list_all()
    return jsonify({"success": True, "data": items}), 200


@menu_bp.route("/api/categories", methods=["GET"])
@admin_required
@csrf.exempt
def api_get_categories() -> tuple:
    return jsonify({"success": True, "data": get_valid_categories()}), 200


@menu_bp.route("/api/categories", methods=["POST"])
@admin_required
@csrf.exempt
def api_create_category() -> tuple:
    if request.is_json:
        data = request.get_json() or {}
        name = str(data.get("name", "")).strip()
    else:
        name = request.form.get("name", "").strip()
    
    if not name:
        return jsonify({"success": False, "error": "Category name is required"}), 400
        
    from app.models.menu_category import MenuCategory
    from app import db
    
    existing = MenuCategory.query.filter(db.func.lower(MenuCategory.name) == name.lower()).first()
    if existing:
        return jsonify({"success": False, "error": "Category already exists"}), 400
        
    try:
        new_cat = MenuCategory(name=name)
        db.session.add(new_cat)
        db.session.commit()
        invalidate_menu_cache()
        
        emit_menu_update('create_category', {'name': name})
        
        return jsonify({"success": True, "data": {"name": name}}), 201
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating category: {e}")
        return jsonify({"success": False, "error": "Database error"}), 500


@menu_bp.route("/api/items", methods=["POST"])
@admin_required
@csrf.exempt
def api_create_item() -> tuple:
    if request.is_json:
        data = request.get_json() or {}
        category = str(data.get("category", "")).strip()
        name = str(data.get("name", "")).strip()
        price = str(data.get("price", "")).strip()
        description = str(data.get("description", "")).strip() or None
    else:
        category = request.form.get("category", "").strip()
        name = request.form.get("name", "").strip()
        price = request.form.get("price", "").strip()
        description = request.form.get("description", "").strip() or None
    
    # Validate category
    valid_cats = get_valid_categories()
    if category not in valid_cats:
        return jsonify({"success": False, "error": f"Category must be one of: {', '.join(valid_cats)}"}), 400
    
    # Validate required fields
    if not name:
        return jsonify({"success": False, "error": "Item name is required"}), 400
    
    if not price:
        return jsonify({"success": False, "error": "Price is required"}), 400
    
    try:
        price = float(price)
        if price < 0:
            return jsonify({"success": False, "error": "Price must be positive"}), 400
    except ValueError:
        return jsonify({"success": False, "error": "Price must be a valid number"}), 400
    
    # Handle image upload
    image_url = None
    if 'image' in request.files:
        image_url, error = validate_and_save_image(request.files['image'])
        if error:
            return jsonify({"success": False, "error": error}), 400
    
    # Create item
    result = _service.create(
        name=name,
        price=price,
        category=category,
        description=description,
        image_url=image_url,
    )
    if result.get("success"):
        emit_menu_update('create', result.get("data", {}))
    return jsonify(result), 201


@menu_bp.route("/api/items/variants", methods=["POST"])
@admin_required
@csrf.exempt
def api_create_item_variants() -> tuple:
    """
    Create multiple Beverage variants (e.g., Coffee Hot/Cold) from one base name.
    - base_name: "Latte"
    - variant_labels: "Hot,Iced"
    - variant_prices: "80,95"
    Creates items named: "Hot Latte", "Iced Latte"
    """
    category = "Beverages"

    # We expect multipart/form-data from the admin modal, but also accept JSON.
    if request.is_json:
        data = request.get_json() or {}
        base_name = str(data.get("base_name", "")).strip()
        variant_labels_raw = str(data.get("variant_labels", "")).strip()
        variant_prices_raw = str(data.get("variant_prices", "")).strip()
        description = str(data.get("description", "")).strip() or None
    else:
        base_name = request.form.get("base_name", "").strip()
        variant_labels_raw = request.form.get("variant_labels", "").strip()
        variant_prices_raw = request.form.get("variant_prices", "").strip()
        description = request.form.get("description", "").strip() or None

    # Validate category
    if category not in get_valid_categories():
        return jsonify({"success": False, "error": "Invalid category configuration"}), 500

    if not base_name:
        return jsonify({"success": False, "error": "base_name is required"}), 400
    if not variant_labels_raw:
        return jsonify({"success": False, "error": "variant_labels is required"}), 400
    if not variant_prices_raw:
        return jsonify({"success": False, "error": "variant_prices is required"}), 400

    labels = [s.strip() for s in variant_labels_raw.split(",") if s.strip()]
    prices_str_arr = [s.strip() for s in variant_prices_raw.split(",") if s.strip()]

    if not labels:
        return jsonify({"success": False, "error": "variant_labels must not be empty"}), 400
    if len(labels) != len(prices_str_arr):
        return jsonify(
            {"success": False, "error": "Labels count must match prices count"}
        ), 400

    prices: list[float] = []
    for p in prices_str_arr:
        try:
            val = float(p)
        except ValueError:
            return jsonify({"success": False, "error": "Prices must be valid numbers"}), 400
        if val < 0:
            return jsonify({"success": False, "error": "Prices must be >= 0"}), 400
        prices.append(val)

    image_url = None
    if "image" in request.files and request.files["image"].filename:
        image_url, error = validate_and_save_image(request.files["image"])
        if error:
            return jsonify({"success": False, "error": error}), 400

    result = _service.create_variants(
        base_name=base_name,
        variant_labels=labels,
        variant_prices=prices,
        category=category,
        description=description,
        image_url=image_url,
    )

    created_ids = result.get("created_ids") or []
    emit_menu_update("create", {"count": len(created_ids)})
    return jsonify({"success": True, "data": result}), 201


@menu_bp.route("/api/items/<int:item_id>", methods=["PATCH"])
@admin_required
@csrf.exempt
def api_update_item(item_id: int) -> tuple:
    from app.models.menu_item import MenuItem
    from app import db
    
    category = request.form.get("category", "").strip()
    valid_cats = get_valid_categories()
    if category and category not in valid_cats:
        return jsonify({"success": False, "error": f"Category must be one of: {', '.join(valid_cats)}"}), 400
    
    # Validate price if provided
    price = request.form.get("price", "").strip()
    if price:
        try:
            price = float(price)
            if price < 0:
                return jsonify({"success": False, "error": "Price must be positive"}), 400
        except ValueError:
            return jsonify({"success": False, "error": "Price must be a valid number"}), 400
    else:
        price = None
    
    # Handle image upload
    image_url = None
    old_image_url = None
    
    if 'image' in request.files and request.files['image'].filename:
        # Get old image URL for cleanup
        item = db.session.get(MenuItem, item_id)
        if item:
            old_image_url = item.image_url
        
        # Save new image
        image_url, error = validate_and_save_image(request.files['image'])
        if error:
            return jsonify({"success": False, "error": error}), 400
        
        # Delete old image after successful save
        if old_image_url:
            delete_old_image(old_image_url)
    
    # Update item
    result = _service.update(
        item_id=item_id,
        name=request.form.get("name", "").strip() or None,
        price=price,
        category=category if category else None,
        description=request.form.get("description", "").strip() or None,
        image_url=image_url,
    )
    if isinstance(result, tuple):
        return jsonify(result[0]), result[1]
    if result.get("success"):
        emit_menu_update('update', {'item_id': item_id, **result.get("data", {})})
    return jsonify(result), 200


@menu_bp.route("/api/items/<int:item_id>/availability", methods=["PATCH"])
@admin_required
@csrf.exempt
def api_toggle_availability(item_id: int) -> tuple:
    result = _service.toggle_availability(item_id)
    if isinstance(result, tuple):
        return jsonify(result[0]), result[1]
    if result.get("success"):
        emit_menu_update('availability_toggle', {'item_id': item_id, **result.get("data", {})})
    return jsonify(result), 200


@menu_bp.route("/api/items/<int:item_id>", methods=["DELETE"])
@admin_required
@csrf.exempt
def api_delete_item(item_id: int) -> tuple:
    from app.models.menu_item import MenuItem
    from app import db
    from sqlalchemy.exc import SQLAlchemyError

    item = db.session.get(MenuItem, item_id)
    if not item:
        return jsonify({"success": False, "error": "Menu item not found"}), 404

    image_url = item.image_url

    try:
        result = _service.delete(item_id)
    except SQLAlchemyError as exc:
        db.session.rollback()
        logger.error(f"Menu delete failed for item {item_id}: {exc}")
        return jsonify({
            "success": False,
            "error": "Could not remove this item. Please try again.",
        }), 500

    if isinstance(result, tuple):
        return jsonify(result[0]), result[1]
    if result.get("success"):
        emit_menu_update("delete", {"item_id": item_id})
    return jsonify(result), 200


@menu_bp.route("/api/menu-items", methods=["GET"])
@admin_required
@csrf.exempt
def api_menu_items_alias() -> tuple:
    items = _service.list_all()
    return jsonify({"success": True, "data": items}), 200
