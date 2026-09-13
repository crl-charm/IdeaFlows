from __future__ import annotations

from functools import wraps
from typing import Callable, Optional, Tuple

from flask import Blueprint, Flask, current_app, flash, jsonify, redirect, request, session
from datetime import datetime
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
                        session.clear()
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
                            session.clear()
                            if _expects_json_response():
                                return jsonify({"success": False, "error": "Unauthorized"}), 401
                            flash("Please log in first!", "danger")
                            return redirect("/login")
                    else:
                        session.clear()
                        if _expects_json_response():
                            return jsonify({"success": False, "error": "Unauthorized"}), 401
                        flash("Please log in first!", "danger")
                        return redirect("/login")
    except Exception:
        session.clear()
        if _expects_json_response():
            return jsonify({"success": False, "error": "Unauthorized"}), 401
        flash("Please log in first!", "danger")
        return redirect("/login")

    last_activity = session.get("last_activity")
    if last_activity:
        session_timeout = current_app.config.get("PERMANENT_SESSION_LIFETIME", 3600 * 24)
        if datetime.utcnow().timestamp() - last_activity > session_timeout:
            security_logger.warning(
                f"Session timeout for user {session.get('username')} from {request.remote_addr}"
            )
            session.clear()
            if _expects_json_response():
                return jsonify({"success": False, "error": "Session expired"}), 401
            flash("Your session has expired. Please log in again.", "warning")
            return redirect("/login")

    session["last_activity"] = datetime.utcnow().timestamp()
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
