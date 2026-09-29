from flask import Blueprint, render_template, session, redirect, request
from app.utils.auth import login_required
from app.models import SpaceType

bp = Blueprint("dashboard", __name__)

@bp.route("/dashboard")
@login_required
def dashboard():
    space_types = SpaceType.query.filter(SpaceType.name.in_(["Regular Lounge", "Premium Lounge"])).order_by(SpaceType.id).all()
    requested_space = request.args.get("space")
    selected_space = (
        next((space for space in space_types if space.name == requested_space), None)
        if requested_space in {"Regular Lounge", "Premium Lounge"} else None
    )
    return render_template(
        "dashboard.html", space_types=space_types, selected_space=selected_space,
        boardroom_view=requested_space == "Boardroom", food_only_view=False,
    )


@bp.route("/food-orders")
@login_required
def food_orders():
    names = ("Regular Lounge", "Premium Lounge", "Boardroom", "Take Out")
    spaces = {space.name: space for space in SpaceType.query.filter(SpaceType.name.in_(names)).all()}
    return render_template(
        "dashboard.html", food_only_view=True, boardroom_view=False,
        selected_space=None, space_types=[],
        food_locations=[spaces[name] for name in names if name in spaces],
    )


@bp.route("/checkout-records")
@login_required
def checkout_records_page():
    return render_template("checkout_records.html")


@bp.route("/daily-sales")
@login_required
def daily_sales_page():
    if session.get("role") == "admin":
        return redirect("/admin/daily-balance")
    return redirect("/dashboard")
