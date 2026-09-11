import os
import logging
from flask import request, abort, jsonify, render_template_string
from flask_limiter.util import get_remote_address

security_logger = logging.getLogger("security")

# Common scanner trap endpoints that regular users will never legitimately request
DECOY_SCANNER_PATHS = [
    "/wp-login.php",
    "/wp-admin",
    "/phpmyadmin",
    "/.env",
    "/.git/config",
    "/xmlrpc.php",
]

# Signatures of automated vulnerability exploit scanners
BLOCKED_TOOL_SIGNATURES = [
    "sqlmap",
    "nikto",
    "masscan",
    "acunetix",
    "havij",
    "dirbuster",
    "zgrab",
    "wpscan",
]


def get_login_rate_limit_key():
    """
    Composite key for rate-limiting login attempts: IP + username.
    Prevents an entire office on a shared NAT'd IP from being locked out
    when a single user repeatedly enters bad credentials, while still strictly
    limiting brute-force attempts on any given account or from any given IP.
    """
    client_ip = get_remote_address()
    username = ""
    try:
        if request.is_json and request.json:
            username = str(request.json.get("username", "")).strip().lower()
        elif request.form:
            username = str(request.form.get("username", "")).strip().lower()
    except Exception:
        pass

    if username:
        return f"{client_ip}:{username}"
    return client_ip


def register_bot_defense(app):
    """
    Register bot defense middlewares, honeypot traps, and security measures.
    """
    honeypot_path = app.config.get("HONEYPOT_SECRET_PATH", "/_trap_security")

    def _trigger_honeypot(trap_name):
        client_ip = request.remote_addr or get_remote_address()
        ua = request.headers.get("User-Agent", "Unknown")
        security_logger.error(
            f"BOT_HONEYPOT_TRIGGERED: {client_ip} accessed {trap_name} '{request.path}' | User-Agent: {ua}"
        )
        # Return 403 forbidden to scraper
        abort(403)

    # 1. Register the randomized honeypot route
    @app.route(honeypot_path, methods=["GET", "POST"])
    def honeypot_trap():
        return _trigger_honeypot("secret_honeypot")

    # 2. Register decoy scanner endpoints
    for decoy_path in DECOY_SCANNER_PATHS:
        rule_name = f"decoy_{decoy_path.strip('/').replace('.', '_').replace('/', '_')}"
        app.add_url_rule(
            decoy_path,
            endpoint=rule_name,
            view_func=lambda dp=decoy_path: _trigger_honeypot(f"decoy_{dp}"),
            methods=["GET", "POST", "HEAD"]
        )

    # 3. Before request defense-in-depth check
    @app.before_request
    def check_suspicious_clients():
        # Skip static assets
        if request.path.startswith("/static/"):
            return None

        ua = request.headers.get("User-Agent", "").lower()

        # Check vulnerability scanners
        for sig in BLOCKED_TOOL_SIGNATURES:
            if sig in ua:
                client_ip = request.remote_addr or get_remote_address()
                security_logger.warning(
                    f"BOT_TOOL_BLOCKED: {client_ip} detected with signature '{sig}' | UA: {ua}"
                )
                abort(403)

        return None

    # 4. Context processor for injecting invisible honeypot link into templates
    @app.context_processor
    def inject_honeypot_link():
        def honeypot_tag():
            return (
                f'<a href="{honeypot_path}" rel="nofollow" '
                f'style="display:none !important; visibility:hidden; opacity:0; position:absolute; left:-9999px;" '
                f'aria-hidden="true" tabindex="-1">System Status Check</a>'
            )
        return dict(honeypot_tag=honeypot_tag)

    # 5. Add X-Robots-Tag header to private/authenticated responses
    @app.after_request
    def add_bot_prevention_headers(response):
        path = request.path or ""
        # The landing page can be indexed, all other internal POS / management routes are strictly noindex
        if path != "/" and not path.startswith(("/static/", "/health/")):
            response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
        return response
