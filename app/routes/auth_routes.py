from flask import Blueprint, render_template, request, jsonify, session, redirect
from app.models import Admin, User, StaffAttendance
from app import db, limiter, csrf
from app.core.bot_defense import get_login_rate_limit_key
from datetime import datetime
import logging
from app.core.socketio_handlers import emit_staff_status_change


bp = Blueprint("auth", __name__)

security_logger = logging.getLogger('security')


def get_redirect_by_role(role):
    if role == "admin":
        return "/admin"
    return "/dashboard"


def _lookup_account(username: str):
    user = User.query.filter_by(username=username, is_active=True).first()
    if user:
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
            # Clear existing session and start a fresh one
            session.clear()
            session.modified = True

            if account_type == "admin":
                admin_user = _get_or_create_admin_user(account)
                session["user_id"] = admin_user.id
            else:
                session["user_id"] = account.id

            session["username"] = account.username
            session["account_type"] = account_type
            session["role"] = "admin" if account_type == "admin" else account.role
            session["job_role"] = "admin" if account_type == "admin" else account.job_role

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