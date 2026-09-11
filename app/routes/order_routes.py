from flask import Blueprint, jsonify, request, render_template, session as flask_session
from app.utils.auth import login_required

from app.core import get_notifier
from app.core.idempotency import idempotent_request
from app.repositories.order_repository import OrderRepository
from app.services.order_service import OrderService


# Blueprint for order related routes
order_bp = Blueprint("order_routes", __name__)

_service = OrderService(repo=OrderRepository(), notifier=get_notifier())


# ----------------------------------
# GET MENU ITEMS
# ----------------------------------
@order_bp.route("/menu")
@login_required
def menu_page():
    return render_template("menu.html")


@order_bp.route("/api/menu")
@login_required
def get_menu():
    return jsonify(_service.list_menu())


# ----------------------------------
# ADD ORDER
# ----------------------------------
@order_bp.route("/api/add-order", methods=["POST"])
@login_required
@idempotent_request("add-order")
def add_order():

    data = request.get_json()

    session_id = data.get("session_id")
    items = data.get("items")

    if not session_id or not items:
        return jsonify({"error": "session_id and items are required"}), 400
    handled_by = flask_session.get("user_id")
    resp = _service.add_order(session_id=int(session_id), items=items, handled_by=handled_by)
    if isinstance(resp, tuple):
        payload, status = resp
        return jsonify(payload), status
    return jsonify(resp)


# ----------------------------------
# UPDATE ORDER STATUS (preparing -> serving)
# ----------------------------------
@order_bp.route("/api/order-status/<int:order_id>", methods=["PUT"])
@login_required
def update_order_status(order_id):
    data = request.get_json(silent=True) or {}
    new_status = data.get("status")
    resp = _service.update_order_status(order_id=order_id, new_status=new_status)
    if isinstance(resp, tuple):
        payload, status = resp
        return jsonify(payload), status
    return jsonify(resp)


# ----------------------------------
# GET SESSION ORDERS
# ----------------------------------
@order_bp.route("/api/session-orders/<int:session_id>")
@login_required
def get_session_orders(session_id):
    # By default, hide completed orders ("done") from the customer orders page.
    # The dashboard receipt needs them, so it can call with `?include_done=1`.
    include_done = request.args.get("include_done", "0").lower() in {"1", "true", "yes"}
    return jsonify(_service.get_session_orders(session_id=session_id, include_done=include_done))


@order_bp.route("/order/<int:session_id>")
@login_required
def order_page(session_id):
    return render_template("order.html", session_id=session_id)


# ----------------------------------
# ORDERS (VIEW ONLY)
# ----------------------------------
@order_bp.route("/orders")
@login_required
def orders_list_page():
    return render_template("orders_list.html")


@order_bp.route("/api/orders-list")
@login_required
def orders_list_api():
    return jsonify(_service.session_orders_list_view())


@order_bp.route("/api/orders/pending-count")
@login_required
def orders_pending_count():
    return jsonify(_service.pending_count())


@order_bp.route("/orders/<int:session_id>")
@login_required
def orders_view_page(session_id):
    return render_template("orders_view.html", session_id=session_id)


@order_bp.route("/api/void-item/<int:item_id>", methods=["DELETE"])
@login_required
def void_item(item_id):
    resp = _service.void_item(item_id)
    if isinstance(resp, tuple):
        payload, status = resp
        return jsonify(payload), status
    return jsonify(resp)


# ----------------------------------
# TOGGLE ORDER ITEM STATUS (preparing <-> done)
# ----------------------------------
@order_bp.route("/api/order-item-status/<int:item_id>", methods=["PUT"])
@login_required
def toggle_order_item_status(item_id):
    resp = _service.toggle_order_item_status(item_id)
    if isinstance(resp, tuple):
        payload, status = resp
        return jsonify(payload), status
    return jsonify(resp)


# ----------------------------------
# MARK ALL SESSION ORDERS AS SERVED
# ----------------------------------
@order_bp.route("/api/session-served/<int:session_id>", methods=["POST"])
@login_required
def session_served(session_id):
    resp = _service.mark_session_served(session_id)
    if isinstance(resp, tuple):
        payload, status = resp
        return jsonify(payload), status
    return jsonify(resp)

