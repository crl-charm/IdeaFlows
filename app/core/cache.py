"""Small Redis read-through cache with graceful database fallback."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any, TypeVar

from flask import current_app


logger = logging.getLogger(__name__)
T = TypeVar("T")


def _client():
    return current_app.extensions.get("redis_health")


def _key(name: str) -> str:
    prefix = current_app.config.get("CACHE_KEY_PREFIX", "ideahub")
    return f"{prefix}:cache:{name}"


def get_or_set_json(name: str, producer: Callable[[], T], *, timeout: int | None = None) -> T:
    """Return cached JSON or compute it; Redis failure never breaks the request."""
    client = _client()
    if client is None or not current_app.config.get("CACHE_ENABLED", True):
        return producer()

    cache_key = _key(name)
    try:
        cached = client.get(cache_key)
        if cached is not None:
            return json.loads(cached)
    except Exception as exc:
        logger.warning("Redis cache read failed for %s: %s", name, exc)
        return producer()

    value = producer()
    ttl = timeout or current_app.config.get("CACHE_DEFAULT_TIMEOUT", 60)
    try:
        client.setex(
            cache_key,
            ttl,
            json.dumps(value, separators=(",", ":"), ensure_ascii=False),
        )
    except Exception as exc:
        logger.warning("Redis cache write failed for %s: %s", name, exc)
    return value


def invalidate_namespace(namespace: str) -> None:
    """Delete every cache entry in a small application-owned namespace."""
    client = _client()
    if client is None:
        return
    pattern = _key(f"{namespace}:*")
    try:
        keys = list(client.scan_iter(match=pattern, count=100))
        if keys:
            # UNLINK reclaims values asynchronously and avoids blocking Redis.
            client.unlink(*keys)
    except Exception as exc:
        logger.warning("Redis cache invalidation failed for %s: %s", namespace, exc)


def invalidate_menu_cache() -> None:
    invalidate_namespace("menu")
