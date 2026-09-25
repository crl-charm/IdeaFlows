"""Server-side Cloudflare Turnstile validation for sensitive forms."""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask import current_app


SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
MAX_TOKEN_LENGTH = 2048


def verify_turnstile(token: object, remote_ip: str | None) -> tuple[bool, str | None]:
    """Validate one single-use Turnstile token.

    The second tuple item is an internal reason code. It is safe to log, but it
    must not be replaced with the submitted token or the configured secret.
    """

    if not current_app.config.get("TURNSTILE_ENABLED"):
        return True, None

    if not isinstance(token, str) or not token or len(token) > MAX_TOKEN_LENGTH:
        return False, "missing-or-invalid-token"

    payload = {
        "secret": current_app.config["TURNSTILE_SECRET_KEY"],
        "response": token,
    }
    if remote_ip:
        payload["remoteip"] = remote_ip

    request = Request(
        SITEVERIFY_URL,
        data=urlencode(payload).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        with urlopen(
            request,
            timeout=current_app.config["TURNSTILE_VERIFY_TIMEOUT"],
        ) as response:
            result = json.loads(response.read(64 * 1024).decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
        current_app.logger.exception("Cloudflare Turnstile Siteverify request failed")
        return False, "verification-service-unavailable"

    if not result.get("success"):
        error_codes = result.get("error-codes") or ["verification-failed"]
        safe_codes = ",".join(str(code)[:80] for code in error_codes[:5])
        return False, f"cloudflare-rejected:{safe_codes}"

    expected_action = current_app.config.get("TURNSTILE_EXPECTED_ACTION")
    if expected_action and result.get("action") != expected_action:
        return False, "action-mismatch"

    allowed_hostnames = current_app.config.get("TURNSTILE_ALLOWED_HOSTNAMES") or []
    if allowed_hostnames and result.get("hostname") not in allowed_hostnames:
        return False, "hostname-mismatch"

    return True, None
