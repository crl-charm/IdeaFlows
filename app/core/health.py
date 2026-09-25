"""Liveness and database/Redis-backed readiness probes."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify
from sqlalchemy import text

from app import db, limiter


health_bp = Blueprint("health", __name__, url_prefix="/health")


@health_bp.get("/live")
@limiter.exempt
def liveness():
    return jsonify({"status": "ok"}), 200


@health_bp.get("/ready")
@limiter.exempt
def readiness():
    try:
        db.session.execute(text("SELECT 1"))
        if (
            current_app.config.get("REDIS_REQUIRED")
            and current_app.extensions.get("redis_startup_error")
        ):
            return jsonify({"status": "unavailable"}), 503
        redis_client = current_app.extensions.get("redis_health")
        if redis_client is not None:
            redis_client.ping()
    except Exception:
        db.session.rollback()
        return jsonify({"status": "unavailable"}), 503
    return jsonify({"status": "ready"}), 200
