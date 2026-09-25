from __future__ import annotations

from functools import wraps
from typing import Callable, Optional, Tuple

from flask import Blueprint, Flask, current_app, flash, jsonify, redirect, request, session
from datetime import datetime, timezone
from time import time
import logging

security_logger = logging.getLogger('security')

ADMIN_ROLES = frozenset({"admin"})

ADMIN_PATH_PREFIXES = (
    "/api/admin/",
    "/finance",
    "/management",
    "/analytics",
    "/api/finance/",
    "/api/management/",
    "/api/analytics/",
)

ADMIN_PATH_EXACT = (
    "/api/daily-sales",
    "/api/sales-summary",
    "/api/sales-compare",
)


def _get_allowed_admin_roles() -> frozenset[str]:
    return ADMIN_ROLES


def _expects_json_response() -> bool:
    """True for API/fetch calls that should receive JSON instead of redirects."""
    path = request.path or ""
    if path.startswith("/api/") or "/api/" in path:
        return True
    if path.startswith("/admin/") and "/api/" in path:
        return True
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return True
    best = request.accept_mimetypes.best_match(["application/json", "text/html"])
    return best == "application/json" and best is not None


def _role_dashboard(role: str | None) -> str:
    if (role or "").lower() == "admin":
        return "/admin"
    return "/dashboard"


def session_idle_deadline() -> datetime | None:
    """Return the UTC logout time when this browser has been idle too long."""
    last_activity = session.get("last_activity")
    if last_activity is None:
        return None
    lifetime = current_app.config.get("PERMANENT_SESSION_LIFETIME", 3600)
    seconds = lifetime.total_seconds() if hasattr(lifetime, "total_seconds") else float(lifetime)
    try:
        deadline = float(last_activity) + seconds
        if time() < deadline:
            return None
        return datetime.fromtimestamp(deadline, timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError, OverflowError):
        return datetime.now(timezone.utc).replace(tzinfo=None)


def end_login_session(*, ended_at: datetime | None = None) -> None:
    """Release this browser's lease and close only its own attendance row."""
    if current_app.config.get("SINGLE_SESSION_ENABLED"):
        from app.core.session_leases import SessionLeaseUnavailable

        try:
            current_app.extensions["session_leases"].release(
                session.get("login_lease_identity", ""),
                session.get("login_lease_token", ""),
            )
        except SessionLeaseUnavailable:
            security_logger.warning("Could not release login lease for %s", session.get("username"))

    if session.get("account_type") == "staff" and session.get("attendance_id"):
        from app import db
        from app.models import StaffAttendance
        from app.core.socketio_handlers import emit_staff_status_change

        try:
            attendance = db.session.get(StaffAttendance, session["attendance_id"])
            if (attendance and attendance.user_id == session.get("user_id")
                    and attendance.time_out is None):
                attendance.time_out = ended_at or datetime.now(timezone.utc).replace(tzinfo=None)
                db.session.commit()
                emit_staff_status_change(attendance.user_id, "offline")
        except Exception:
            db.session.rollback()
            security_logger.exception("Could not close staff attendance during logout")

    session.clear()


def _check_session_auth() -> Optional[Tuple]:
    """Return a Flask response tuple if auth/session invalid, else None."""
    if "user_id" not in session:
        if _expects_json_response():
            return jsonify({"success": False, "error": "Unauthorized"}), 401
        flash("Please log in first!", "danger")
        return redirect("/login")

    # Ensure the stored user_id actually refers to a valid users.User row.
    # If it doesn't, try to remap admin sessions (admins.username -> users.username).
    try:
        from app.models import User

        stored_user_id = session.get("user_id")
        if stored_user_id is not None:
            found = User.query.get(stored_user_id)
            stored_role = (session.get("role") or "").lower()
            if found and not current_app.testing and (
                (stored_role != "admin" and not found.is_active)
                or (found.role or "").lower() != stored_role
            ):
                end_login_session()
                if _expects_json_response():
                    return jsonify({"success": False, "error": "Unauthorized"}), 401
                flash("Your account is no longer active.", "warning")
                return redirect("/login")
            if not found:
                # If session user_id doesn't map to a User, try remapping via known
                # admin identity (either account_type/username or Admin.id).
                account_type = session.get("account_type")
                username = session.get("username")

                # First try: if session already has account_type/admin username, map to User
                if account_type == "admin" and username:
                    admin_user = User.query.filter_by(username=username).first()
                    if admin_user:
                        session["user_id"] = admin_user.id
                        # ensure account_type is consistent
                        session["account_type"] = "admin"
                    else:
                        end_login_session()
                        if _expects_json_response():
                            return jsonify({"success": False, "error": "Unauthorized"}), 401
                        flash("Please log in first!", "danger")
                        return redirect("/login")
                else:
                    # Second try: maybe stored_user_id is actually an Admin.id (legacy).
                    from app.models import Admin

                    maybe_admin = Admin.query.get(stored_user_id)
                    if maybe_admin:
                        admin_user = User.query.filter_by(username=maybe_admin.username).first()
                        if admin_user:
                            session["user_id"] = admin_user.id
                            session["username"] = maybe_admin.username
                            session["account_type"] = "admin"
                        else:
                            end_login_session()
                            if _expects_json_response():
                                return jsonify({"success": False, "error": "Unauthorized"}), 401
                            flash("Please log in first!", "danger")
                            return redirect("/login")
                    else:
                        end_login_session()
                        if _expects_json_response():
                            return jsonify({"success": False, "error": "Unauthorized"}), 401
                        flash("Please log in first!", "danger")
                        return redirect("/login")
    except Exception:
        end_login_session()
        if _expects_json_response():
            return jsonify({"success": False, "error": "Unauthorized"}), 401
        flash("Please log in first!", "danger")
        return redirect("/login")

    idle_deadline = session_idle_deadline()
    if idle_deadline is not None:
        security_logger.warning(
            "Session timeout for user %s from %s", session.get("username"), request.remote_addr
        )
        end_login_session(ended_at=idle_deadline)
        if _expects_json_response():
            return jsonify({"success": False, "error": "Session expired"}), 401
        flash("Your session has expired. Please log in again.", "warning")
        return redirect("/login")

    if current_app.config.get("SINGLE_SESSION_ENABLED"):
        from app.core.session_leases import (
            SessionLeaseUnavailable,
            current_lease_is_valid,
        )

        try:
            lease_valid = current_lease_is_valid(refresh=False)
        except SessionLeaseUnavailable:
            security_logger.exception(
                "Single-session registry unavailable for authenticated request"
            )
            if _expects_json_response():
                return jsonify({
                    "success": False,
                    "error": "Authentication service temporarily unavailable",
                }), 503
            return "Authentication service temporarily unavailable", 503

        if not lease_valid:
            username = session.get("username", "unknown")
            end_login_session()
            security_logger.warning(
                "Expired or revoked login session for %s from %s",
                username,
                request.remote_addr,
            )
            if _expects_json_response():
                return jsonify({
                    "success": False,
                    "error": "Session expired or was signed out",
                    "code": "session_revoked",
                }), 401
            flash("Your session ended. Please log in again.", "warning")
            return redirect("/login")

    return None


def _deny_access(message: str = "Forbidden", status: int = 403):
    if _expects_json_response():
        return jsonify({"success": False, "error": message}), status
    flash("Admin access required.", "danger")
    return redirect(_role_dashboard(session.get("role")))


def is_admin_path(path: str) -> bool:
    if not path:
        return False
    if path in ADMIN_PATH_EXACT:
        return True
    if path == "/admin" or path.startswith("/admin/"):
        return True
    return any(path.startswith(prefix) for prefix in ADMIN_PATH_PREFIXES)


def enforce_admin_access() -> Optional[Tuple]:
    """Shared admin RBAC check. Returns None if allowed, else a Flask response."""
    auth_error = _check_session_auth()
    if auth_error is not None:
        return auth_error

    role = (session.get("role") or "").lower()
    if role not in _get_allowed_admin_roles():
        security_logger.warning(
            f"Unauthorized admin access attempt by {session.get('username')} "
            f"({role}) to {request.path} from {request.remote_addr}"
        )
        return _deny_access("Forbidden", 403)

    return None


def register_admin_blueprint(app: Flask, blueprint: Blueprint) -> None:
    """Register a blueprint and enforce admin RBAC on every route in it."""
    if not blueprint._got_registered_once:
        @blueprint.before_request
        def _enforce_admin_blueprint_access():
            denied = enforce_admin_access()
            if denied is not None:
                return denied

    app.register_blueprint(blueprint)


def login_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        auth_error = _check_session_auth()
        if auth_error is not None:
            return auth_error
        return view_func(*args, **kwargs)

    return wrapper


def admin_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        denied = enforce_admin_access()
        if denied is not None:
            return denied
        return view_func(*args, **kwargs)

    return wrapper


def sanitize_input(input_string):
    """Sanitize user input to prevent XSS"""
    if not input_string:
        return input_string

    return (
        input_string.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
        .replace("/", "&#x2F;")
    )
