from flask import Blueprint, current_app, render_template, request, jsonify, session, redirect
from app.models import Admin, User, StaffAttendance
from app import db, limiter, csrf
from app.core.bot_defense import get_login_rate_limit_key
from app.core.turnstile import verify_turnstile
from datetime import datetime, timedelta, timezone
import logging
from app.core.session_leases import SessionLeaseUnavailable, current_lease_is_valid
from app.utils.auth import end_login_session, login_required, session_idle_deadline
from app.core.socketio_handlers import (
    emit_login_attempt_blocked,
    emit_staff_status_change,
)


bp = Blueprint("auth", __name__)

security_logger = logging.getLogger('security')


def get_redirect_by_role(role):
    if role == "admin":
        return "/admin"
    return "/dashboard"


def _lookup_account(username: str):
    user = User.query.filter_by(username=username, is_active=True).first()
    if user:
        # Only normal staff rows may use the staff authentication path.
        if (user.role or "").lower() != "staff":
            return None, None
        return user, "staff"
    admin = Admin.query.filter_by(username=username).first()
    if admin:
        return admin, "admin"
    return None, None


def _username_exists(username: str) -> bool:
    return bool(
        User.query.filter_by(username=username).first()
        or Admin.query.filter_by(username=username).first()
    )


def _get_or_create_admin_user(admin: Admin) -> User:
    """Return the shadow users.User row for an admin account."""
    admin_user = User.query.filter_by(username=admin.username).first()
    if admin_user:
        return admin_user

    admin_user = User(
        full_name=admin.full_name,
        username=admin.username,
        role="admin",
        job_role="admin",
        is_active=False,
    )
    admin_user.password = admin.password
    admin_user.failed_login_attempts = admin.failed_login_attempts
    admin_user.locked_until = admin.locked_until
    admin_user.last_login = admin.last_login
    admin_user.password_changed_at = admin.password_changed_at
    admin_user.created_at = admin.created_at
    db.session.add(admin_user)
    db.session.flush()
    return admin_user


@bp.route("/login")
def login_page():

    if "user_id" in session:
        return redirect(get_redirect_by_role(session.get("role")))

    return render_template("login.html")


@bp.route("/api/login", methods=["POST"])
@limiter.limit("10 per minute", key_func=get_login_rate_limit_key)
@csrf.exempt
def login_api():
    """Secure login with rate limiting and account lockout"""
    acquired_identity = None
    acquired_token = None
    try:
        data = request.get_json()

        # Input validation
        if not data or not isinstance(data, dict):
            security_logger.warning("Invalid login request format")
            return jsonify({"error": "Invalid request format"}), 400

        username = data.get("username", "").strip()
        password = data.get("password", "")

        if not username or not password:
            security_logger.warning(f"Missing credentials for login attempt: {request.remote_addr}")
            return jsonify({"error": "Username and password are required"}), 400

        turnstile_ok, turnstile_error = verify_turnstile(
            data.get("turnstile_token"), request.remote_addr
        )
        if not turnstile_ok:
            security_logger.warning(
                "Turnstile login verification failed from %s: %s",
                request.remote_addr,
                turnstile_error,
            )
            if turnstile_error == "verification-service-unavailable":
                return jsonify({
                    "error": "Human verification is temporarily unavailable. Please try again."
                }), 503
            return jsonify({
                "error": "Please complete the human verification and try again."
            }), 400

        account, account_type = _lookup_account(username)

        if not account:
            security_logger.warning(f"Login attempt for non-existent user: {username} from {request.remote_addr}")
            return jsonify({"error": "Invalid credentials"}), 401

        # Check if account is locked
        if account.is_locked():
            security_logger.warning(f"Login attempt on locked account: {username} from {request.remote_addr}")
            return jsonify({"error": "Account is temporarily locked due to too many failed attempts"}), 429

        # Verify password
        if account.check_password(password):
            if account_type == "admin":
                admin_user = _get_or_create_admin_user(account)
                db.session.commit()
                session_user_id = admin_user.id
                lease_identity = f"admin:{account.id}"
                login_role = "admin"
            else:
                session_user_id = account.id
                lease_identity = f"{account_type}:{account.id}"
                login_role = account.role

            if current_app.config.get("SINGLE_SESSION_ENABLED"):
                lease_service = current_app.extensions["session_leases"]
                try:
                    acquired_token = lease_service.acquire(
                        lease_identity,
                        user_id=session_user_id,
                        username=account.username,
                        role=login_role,
                        ip_address=request.remote_addr or "unknown",
                        user_agent=request.user_agent.string or "unknown",
                    )
                except SessionLeaseUnavailable:
                    security_logger.exception(
                        "Single-session registry unavailable during login for %s",
                        username,
                    )
                    return jsonify({
                        "error": "Login is temporarily unavailable. Please try again shortly."
                    }), 503

                if acquired_token is None:
                    emit_login_attempt_blocked(session_user_id)
                    security_logger.warning(
                        "Verified duplicate login blocked for %s from %s",
                        username,
                        request.remote_addr,
                    )
                    return jsonify({
                        "error": (
                            "This account is already signed in on another device. "
                            "Log out there first or wait about two minutes."
                        ),
                        "code": "account_already_active",
                    }), 409
                acquired_identity = lease_identity

            # Clear existing session and start a fresh one
            session.clear()
            session.modified = True

            session["user_id"] = session_user_id

            session["username"] = account.username
            session["account_type"] = account_type
            session["role"] = login_role
            session["job_role"] = "admin" if account_type == "admin" else account.job_role
            now = datetime.now(timezone.utc)
            session["last_activity"] = now.timestamp()
            if acquired_token:
                session["login_lease_identity"] = acquired_identity
                session["login_lease_token"] = acquired_token

            if account_type == "staff":
                # Close stale open sessions for this user
                open_sessions = StaffAttendance.query.filter_by(user_id=account.id, time_out=None).all()
                idle_seconds = current_app.config["PERMANENT_SESSION_LIFETIME"]
                if hasattr(idle_seconds, "total_seconds"):
                    idle_seconds = idle_seconds.total_seconds()
                now_utc = now.replace(tzinfo=None)
                for obs in open_sessions:
                    obs.time_out = min(now_utc, obs.last_activity_at + timedelta(seconds=idle_seconds)) if obs.last_activity_at else now_utc

                # Log attendance
                attendance = StaffAttendance(user_id=account.id, time_in=now_utc, last_activity_at=now_utc)
                db.session.add(attendance)
                db.session.commit()
                session["attendance_id"] = attendance.id

                # Emit real-time status update
                emit_staff_status_change(account.id, "online")
            else:
                db.session.commit()

            security_logger.info(f"Successful login: {username} from {request.remote_addr}")
            return jsonify({
                "message": "Login successful",
                "redirect": get_redirect_by_role(session["role"])
            })
        else:
            security_logger.warning(f"Failed login attempt: {username} from {request.remote_addr}")
            return jsonify({"error": "Invalid credentials"}), 401

    except Exception as e:
        if acquired_identity and acquired_token:
            try:
                current_app.extensions["session_leases"].release(
                    acquired_identity, acquired_token
                )
            except SessionLeaseUnavailable:
                pass
        security_logger.exception(f"Login error: {str(e)} from {request.remote_addr}")
        db.session.rollback()
        return jsonify({"error": "Login failed"}), 500


@bp.route("/api/session-status")
@login_required
def session_status():
    return jsonify({"ok": True})


@bp.route("/api/session-activity", methods=["POST"])
@login_required
def session_activity():
    """Extend the idle deadline only after browser user input."""
    now = datetime.now(timezone.utc)
    if session.get("account_type") == "staff" and session.get("attendance_id"):
        attendance = db.session.get(StaffAttendance, session["attendance_id"])
        if attendance and attendance.user_id == session.get("user_id") and attendance.time_out is None:
            attendance.last_activity_at = now.replace(tzinfo=None)
            db.session.commit()

    if current_app.config.get("SINGLE_SESSION_ENABLED"):
        try:
            if not current_lease_is_valid(refresh=True):
                end_login_session()
                return jsonify({"error": "Session expired or was signed out"}), 401
        except SessionLeaseUnavailable:
            return jsonify({"error": "Authentication service temporarily unavailable"}), 503

    session["last_activity"] = now.timestamp()
    return jsonify({"ok": True})


@bp.route("/logout")
def logout():
    """Secure logout with session cleanup"""
    username = session.get("username", "unknown")
    end_login_session(ended_at=session_idle_deadline())
    security_logger.info("Logout: %s from %s", username, request.remote_addr)
    return redirect("/login")
