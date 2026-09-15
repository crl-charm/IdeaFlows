from flask import Blueprint, current_app, render_template, request, jsonify, session, redirect
from app.models import Admin, User, StaffAttendance
from app import db, limiter, csrf
from app.core.bot_defense import get_login_rate_limit_key
from app.core.turnstile import verify_turnstile
from datetime import datetime
import logging
from app.core.session_leases import SessionLeaseUnavailable
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
            if acquired_token:
                session["login_lease_identity"] = acquired_identity
                session["login_lease_token"] = acquired_token

            if account_type == "staff":
                # Close stale open sessions for this user
                open_sessions = StaffAttendance.query.filter_by(user_id=account.id, time_out=None).all()
                for obs in open_sessions:
                    obs.time_out = datetime.utcnow()

                # Log attendance
                attendance = StaffAttendance(user_id=account.id, time_in=datetime.utcnow())
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


@bp.route("/logout")
def logout():
    """Secure logout with session cleanup"""
    try:
        account_type = session.get("account_type")
        user_id = session.get("user_id")
        attendance_id = session.get("attendance_id")

        if current_app.config.get("SINGLE_SESSION_ENABLED"):
            try:
                current_app.extensions["session_leases"].release(
                    session.get("login_lease_identity", ""),
                    session.get("login_lease_token", ""),
                )
            except SessionLeaseUnavailable:
                security_logger.warning(
                    "Could not release login lease during logout for %s",
                    session.get("username", "unknown"),
                )

        if account_type == "staff":
            if attendance_id:
                attendance = StaffAttendance.query.get(attendance_id)
                if attendance and attendance.time_out is None:
                    attendance.time_out = datetime.utcnow()
                    db.session.commit()

            # Close all stale open sessions for this staff user
            if user_id:
                open_sessions = StaffAttendance.query.filter_by(user_id=user_id, time_out=None).all()
                for obs in open_sessions:
                    obs.time_out = datetime.utcnow()
                db.session.commit()

                # Emit real-time status update
                emit_staff_status_change(user_id, "offline")

        username = session.get("username", "unknown")
        security_logger.info(f"Logout: {username} from {request.remote_addr}")
        session.clear()
        session.modified = True
        return redirect("/login")
    except Exception as e:
        security_logger.error(f"Logout error: {str(e)}")
        session.clear()
        return redirect("/login")
