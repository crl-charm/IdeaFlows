from flask import Blueprint, render_template, session, redirect
from app.utils.auth import login_required
from app.models import SpaceType

bp = Blueprint("dashboard", __name__)

@bp.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", space_types=SpaceType.query.order_by(SpaceType.id).all())


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
