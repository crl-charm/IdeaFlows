from flask import Blueprint, request, jsonify, render_template
from app.core import get_notifier
from app.core.clock import SystemClock
from app.repositories.booking_repository import BookingRepository
from app.services.booking_service import BookingService
from app.utils.auth import login_required
from app.core.idempotency import idempotent_request

lounge_bp = Blueprint("lounge_routes", __name__)
_service = BookingService(repo=BookingRepository(), notifier=get_notifier(), clock=SystemClock())


# ----------------------------------
# LOUNGE BOOKING PAGE
# ----------------------------------
@lounge_bp.route("/lounge-booking")
@login_required
def lounge_booking_page():
    return render_template("lounge_booking.html")


# ----------------------------------
# CREATE BOOKING
# ----------------------------------
@lounge_bp.route("/api/book-lounge", methods=["POST"])
@login_required
@idempotent_request("book-lounge")
def book_lounge():
    resp = _service.create_booking(request.get_json() or {})
    if isinstance(resp, tuple):
        payload, status = resp
        return jsonify(payload), status
    return jsonify(resp)


# ----------------------------------
# GET BOOKINGS (optionally by date)
# ----------------------------------
@lounge_bp.route("/api/lounge-bookings")
@login_required
def get_lounge_bookings():
    date_str = request.args.get("date", "").strip()
    status_filter = request.args.get("status", "").strip().lower()
    return jsonify(_service.list_bookings(date_str=date_str, status_filter=status_filter))


# ----------------------------------
# CANCEL BOOKING
# ----------------------------------
@lounge_bp.route("/api/lounge-bookings/<int:booking_id>", methods=["DELETE"])
@login_required
@idempotent_request("cancel-lounge-booking")
def cancel_lounge_booking(booking_id):
    resp = _service.cancel_booking(booking_id)
    if isinstance(resp, tuple):
        payload, status = resp
        return jsonify(payload), status
    return jsonify(resp)


# ----------------------------------
# UPDATE BOOKED START TIME (LATE ARRIVAL)
# ----------------------------------
@lounge_bp.route("/api/lounge-bookings/<int:booking_id>", methods=["PATCH"])
@login_required
@idempotent_request("update-lounge-booking")
def update_lounge_booking(booking_id):
    data = request.get_json(silent=True) or {}
    resp = _service.update_booking_start(
        booking_id=booking_id,
        start_time_str=(data.get("start_time") or "").strip(),
    )
    if isinstance(resp, tuple):
        payload, status = resp
        return jsonify(payload), status
    return jsonify(resp)


# ----------------------------------
# START BOARDROOM SESSION FROM BOOKING
# ----------------------------------
@lounge_bp.route("/api/lounge-bookings/<int:booking_id>/start", methods=["POST"])
@login_required
@idempotent_request("start-lounge-booking")
def start_booking_session(booking_id):
    resp = _service.start_booking(booking_id)
    if isinstance(resp, tuple):
        payload, status = resp
        return jsonify(payload), status
    return jsonify(resp)


# ----------------------------------
# EXTEND ACTIVE BOOKING
# ----------------------------------
@lounge_bp.route("/api/lounge-bookings/<int:booking_id>/extend", methods=["POST"])
@login_required
@idempotent_request("extend-lounge-booking")
def extend_booking(booking_id):
    data = request.get_json(silent=True) or {}
    resp = _service.extend_booking(booking_id=booking_id, minutes=int(data.get("minutes", 0)))
    if isinstance(resp, tuple):
        payload, status = resp
        return jsonify(payload), status
    return jsonify(resp)


# ----------------------------------
# OVERDUE ALERTS (GLOBAL POLL)
# ----------------------------------
@lounge_bp.route("/api/lounge-bookings/overdue-alerts")
@login_required
def overdue_alerts():
    return jsonify(_service.overdue_alerts())
