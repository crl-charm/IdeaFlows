# Add these routes to your auth_routes.py or a new admin_routes.py

from flask import Blueprint, render_template, request, jsonify, session, redirect
from app.repositories.admin_repository import AdminRepository
from app.services.admin_service import AdminService
from app.utils.auth import login_required, admin_required
from app.core.idempotency import idempotent_request

_service = AdminService(repo=AdminRepository())


# ── Blueprint ─────────────────────────────────────────────────────────────────

admin_bp = Blueprint("admin", __name__)


# ── Registration page (GET) ───────────────────────────────────────────────────

@admin_bp.route("/register")
@login_required
@admin_required
def register_page():
    # Private system: registration is admin-only via the admin panel modal.
    return redirect("/admin")


# ── Register API (POST) ───────────────────────────────────────────────────────
# Used by both the public register page AND the admin "Add User" modal

@admin_bp.route("/api/register", methods=["POST"])
@login_required
@admin_required
@idempotent_request("admin-register-staff")
def register_api():
    payload = _service.register_staff(request.get_json() or {})
    if isinstance(payload, tuple):
        body, status = payload
        return jsonify(body), status
    return jsonify(payload)


# ── Admin page (GET) ──────────────────────────────────────────────────────────

@admin_bp.route("/admin")
@login_required
@admin_required
def admin_page():
    return render_template("admin.html")


# ── List all users (GET) ──────────────────────────────────────────────────────

@admin_bp.route("/api/admin/users", methods=["GET"])
@login_required
@admin_required
def get_all_users():
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 100)
    return jsonify(_service.list_users(page=page, per_page=per_page))


# ── Edit user (PUT) ───────────────────────────────────────────────────────────

@admin_bp.route("/api/admin/users/<int:user_id>", methods=["PUT"])
@login_required
@admin_required
@idempotent_request("admin-edit-staff")
def edit_user(user_id):
    resp = _service.edit_user(user_id=user_id, data=request.get_json() or {})
    if isinstance(resp, tuple):
        body, status = resp
        return jsonify(body), status
    return jsonify(resp)


# ── Delete user (DELETE) ──────────────────────────────────────────────────────

@admin_bp.route("/api/admin/users/<int:user_id>", methods=["DELETE"])
@login_required
@admin_required
@idempotent_request("admin-delete-staff")
def delete_user(user_id):

    # Prevent admin from deleting themselves
    if session.get("user_id") == user_id:
        return jsonify({"error": "You cannot delete your own account."}), 400

    resp = _service.delete_user(user_id)
    if isinstance(resp, tuple):
        body, status = resp
        return jsonify(body), status
    return jsonify(resp)


@admin_bp.route("/api/admin/customer-records", methods=["GET"])
@login_required
@admin_required
def get_customer_records():
    return jsonify(_service.customer_records())


@admin_bp.route("/api/admin/customer-count", methods=["GET"])
@login_required
@admin_required
def get_customer_count():
    return jsonify({"count": _service.customer_count()})


@admin_bp.route("/api/admin/staff-attendance", methods=["GET"])
@login_required
@admin_required
def get_staff_attendance():
    return jsonify(_service.staff_attendance())


# ── Space Capacity ──────────────────────────────────────────────────────────

@admin_bp.route("/api/admin/space-capacity", methods=["GET"])
@login_required
@admin_required
def get_space_capacities():
    return jsonify(_service.capacities())


@admin_bp.route("/api/admin/space-capacity/<int:space_id>", methods=["PUT"])
@login_required
@admin_required
@idempotent_request("admin-set-space-capacity")
def set_space_capacity(space_id):
    data = request.get_json() or {}
    resp = _service.set_capacity(space_id, data.get("capacity"))
    if isinstance(resp, tuple):
        body, status = resp
        return jsonify(body), status
    return jsonify(resp)


# ── Space Price Management ──────────────────────────────────────────────────

@admin_bp.route("/api/admin/spaces/prices", methods=["GET"])
@login_required
@admin_required
def get_space_prices():
    return jsonify({"success": True, "data": _service.space_prices()}), 200


@admin_bp.route("/api/admin/spaces/prices/<int:space_id>", methods=["PUT"])
@login_required
@admin_required
@idempotent_request("admin-update-space-price")
def update_space_price(space_id):
    from app.models import SpaceType, SpacePriceHistory
    from app import db
    
    data = request.get_json() or {}
    hourly_rate = data.get("hourly_rate")
    
    if hourly_rate is None:
        return jsonify({"error": "Hourly rate is required"}), 400
    
    try:
        hourly_rate = float(hourly_rate)
        if hourly_rate < 0:
            return jsonify({"error": "Price cannot be negative"}), 400
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid price format"}), 400
    
    space = SpaceType.query.get(space_id)
    if not space:
        return jsonify({"error": "Space not found"}), 404
    
    # Convert hourly rate to rate per minute
    rate_per_minute = hourly_rate / 60
    
    # Get the old price
    old_price = space.rate_per_minute
    
    # Update the space price
    space.rate_per_minute = rate_per_minute
    
    # Create a price history record
    history = SpacePriceHistory(
        space_type_id=space_id,
        old_price=old_price,
        new_price=rate_per_minute,
        changed_by_id=session.get("user_id")
    )
    
    db.session.add(history)
    db.session.commit()
    
    return jsonify({
        "success": True,
        "message": f"Price for {space.name} updated to ₱{hourly_rate:.2f}/hour",
        "data": {
            "id": space.id,
            "name": space.name,
            "hourly_rate": hourly_rate,
            "changed_at": history.changed_at.isoformat()
        }
    }), 200


@admin_bp.route("/api/admin/spaces/price-history/<int:space_id>", methods=["GET"])
@login_required
@admin_required
def get_space_price_history(space_id):
    from app.models import SpaceType, SpacePriceHistory
    
    space = SpaceType.query.get(space_id)
    if not space:
        return jsonify({"error": "Space not found"}), 404
    
    history = SpacePriceHistory.query.filter_by(space_type_id=space_id).order_by(
        SpacePriceHistory.changed_at.desc()
    ).all()
    
    data = [h.to_dict() for h in history]
    
    return jsonify({
        "success": True,
        "space_name": space.name,
        "data": data
    }), 200


# ── Staff Analytics ──────────────────────────────────────────────────────────

@admin_bp.route("/api/admin/staff-analytics", methods=["GET"])
@login_required
@admin_required
def staff_analytics():
    return jsonify(_service.analytics())
