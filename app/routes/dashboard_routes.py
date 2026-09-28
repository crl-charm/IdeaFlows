from flask import Blueprint, render_template, session, redirect, request
from app.utils.auth import login_required
from app.models import SpaceType

bp = Blueprint("dashboard", __name__)

@bp.route("/dashboard")
@login_required
def dashboard():
    space_types = SpaceType.query.filter(SpaceType.name.notin_(["Whole Hub", "Boardroom"])).order_by(SpaceType.id).all()
    requested_space = request.args.get("space")
    selected_space = (
        next((space for space in space_types if space.name == requested_space), None)
        if requested_space in {"Regular Lounge", "Premium Lounge"} else None
    )
    return render_template(
        "dashboard.html", space_types=space_types, selected_space=selected_space,
        boardroom_view=requested_space == "Boardroom",
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
