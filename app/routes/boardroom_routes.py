from flask import Blueprint, request, jsonify, render_template

from app.core import get_notifier
from app.core.clock import SystemClock
from app.repositories.booking_repository import BookingRepository
from app.services.booking_service import BookingService
from app.utils.auth import login_required
from app.core.idempotency import idempotent_request

boardroom_bp = Blueprint("boardroom_routes", __name__)
_service = BookingService(repo=BookingRepository(), notifier=get_notifier(), clock=SystemClock())


# -----------------------------
# CREATE BOOKING
# -----------------------------
@boardroom_bp.route("/api/book-boardroom", methods=["POST"])
@login_required
@idempotent_request("book-boardroom")
def book_boardroom():
    resp = _service.create_booking(request.get_json() or {})
    if isinstance(resp, tuple):
        payload, status = resp
        return jsonify(payload), status
    return jsonify(resp)
    

# -----------------------------
# GET BOOKINGS
# -----------------------------
@boardroom_bp.route("/api/boardroom-bookings")
@login_required
def get_bookings():
    return jsonify(_service.list_bookings(date_str="", status_filter=""))

@boardroom_bp.route("/boardroom")
@login_required
def boardroom_page():
    return render_template("boardroom.html")
