"""Small request-level observability hooks with no external dependency."""

from __future__ import annotations

import logging
import re
import time
import uuid

from flask import g, request


_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
logger = logging.getLogger("ideahub.requests")


def register_observability(app) -> None:
    @app.before_request
    def start_request_metrics():
        supplied_id = request.headers.get("X-Request-ID", "")
        g.request_id = supplied_id if _REQUEST_ID_RE.fullmatch(supplied_id) else uuid.uuid4().hex
        g.request_started_at = time.perf_counter()

    @app.after_request
    def finish_request_metrics(response):
        elapsed_ms = (time.perf_counter() - g.request_started_at) * 1000
        response.headers["X-Request-ID"] = g.request_id
        response.headers["Server-Timing"] = f"app;dur={elapsed_ms:.1f}"

        threshold = app.config.get("SLOW_REQUEST_MS", 1000)
        if threshold and elapsed_ms >= threshold:
            logger.warning(
                "slow_request method=%s path=%s status=%s duration_ms=%.1f request_id=%s",
                request.method,
                request.path,
                response.status_code,
                elapsed_ms,
                g.request_id,
            )
        return response
