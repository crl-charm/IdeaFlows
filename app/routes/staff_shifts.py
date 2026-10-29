"""Manual work shifts, separate from login presence."""

from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, request, session
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app import db
from app.core.idempotency import idempotent_request
from app.models import CustomerSession, SpaceType, StaffShift, User
from app.utils.auth import login_required
from app.utils.dates import MANILA_OFFSET


bp = Blueprint("staff_shifts", __name__)
SHIFT_ROLES = {"general", "cashier", "cook", "server"}


def _staff_user(*, lock=False):
    if session.get("role") != "staff":
        return None
    query = User.query.filter_by(id=session.get("user_id"), role="staff", is_active=True)
    return (query.with_for_update() if lock else query).first()


def _open_shift(user_id):
    return (StaffShift.query.filter_by(user_id=user_id, time_out=None)
            .order_by(StaffShift.id.desc()).first())


def _entered_time(value):
    if not isinstance(value, str):
        return None
    try:
        local = datetime.strptime(value, "%Y-%m-%dT%H:%M")
    except ValueError:
        return None
    utc = local - MANILA_OFFSET
    if utc > datetime.now(timezone.utc).replace(tzinfo=None):
        return None
    return utc


def _shift_json(shift):
    if not shift:
        return None
    return {
        "id": shift.id,
        "role": shift.shift_role,
        "time_in": (shift.time_in + MANILA_OFFSET).strftime("%Y-%m-%dT%H:%M"),
        "time_out": (shift.time_out + MANILA_OFFSET).strftime("%Y-%m-%dT%H:%M") if shift.time_out else None,
    }


@bp.get("/api/staff-shift")
@login_required
def shift_status():
    user = _staff_user()
    if not user:
        return jsonify({"error": "Staff account required."}), 403
    return jsonify({"name": user.full_name, "account_role": user.job_role,
                    "open_shift": _shift_json(_open_shift(user.id))})


@bp.post("/api/staff-shift/time-in")
@login_required
@idempotent_request("staff-time-in")
def time_in():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid shift details."}), 400
    role = data.get("role")
    entered = _entered_time(data.get("time_in"))
    if role not in SHIFT_ROLES or entered is None:
        return jsonify({"error": "Choose a role and a valid past or current Time In."}), 400

    user = _staff_user(lock=True)
    if not user:
        return jsonify({"error": "Staff account required."}), 403
    if _open_shift(user.id):
        return jsonify({"error": "You already have an open shift. Save Time Out first."}), 409

    shift = StaffShift(user_id=user.id, shift_role=role, time_in=entered)
    db.session.add(shift)
    db.session.commit()
    return jsonify({"shift": _shift_json(shift)}), 201


@bp.post("/api/staff-shift/time-out")
@login_required
@idempotent_request("staff-time-out")
def time_out():
    data = request.get_json(silent=True)
    entered = _entered_time(data.get("time_out")) if isinstance(data, dict) else None
    if entered is None:
        return jsonify({"error": "Enter a valid past or current Time Out."}), 400

    user = _staff_user(lock=True)
    if not user:
        return jsonify({"error": "Staff account required."}), 403
    shift = _open_shift(user.id)
    if not shift:
        return jsonify({"error": "There is no open shift to time out."}), 409
    if entered <= shift.time_in:
        return jsonify({"error": "Time Out must be after Time In."}), 400

    active = (CustomerSession.query.join(SpaceType).filter(
        CustomerSession.status == "active", CustomerSession.service_mode == "timed",
        SpaceType.name.in_(("Regular Lounge", "Premium Lounge")),
    ).order_by(CustomerSession.id).all())
    if active:
        signer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="staff-timeout-handover")
        context = {"staff": user.id, "shift": shift.id, "time_out": data["time_out"],
                   "visits": [[row.id, row.time_in.isoformat(), row.paused_at.isoformat() if row.paused_at else None]
                              for row in active]}
        acknowledgement = None
        try:
            if isinstance(data.get("handover_token"), str):
                acknowledgement = signer.loads(data["handover_token"], max_age=300)
        except BadSignature:
            pass
        if acknowledgement != context:
            return jsonify({"error": "Customers are still checked in. Review them or confirm a handover.",
                            "needs_handover": True, "handover_token": signer.dumps(context),
                            "active_customers": [{"id": row.id, "name": row.customer_name,
                                "space": row.space_type.name,
                                "time_in": (row.time_in + MANILA_OFFSET).strftime("%Y-%m-%d %I:%M %p"),
                                "paused": row.paused_at is not None} for row in active]}), 409

    shift.time_out = entered
    shift.time_out_recorded_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.session.commit()
    return jsonify({"shift": _shift_json(shift)})
