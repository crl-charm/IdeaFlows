import os
import secrets


def _env_int(name, default, minimum=0):
    """Read a bounded integer setting with a clear startup error."""
    raw_value = os.environ.get(name)
    if raw_value in (None, ""):
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value < minimum:
        raise RuntimeError(f"{name} must be at least {minimum}")
    return value


def _env_bool(name, default=False):
    raw_value = os.environ.get(name)
    if raw_value in (None, ""):
        return default
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"{name} must be true or false")

# Load .env configuration if present
try:
    from dotenv import load_dotenv
    for _env_file in [
        os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"),
        "/var/www/ideahub/.env",
        ".env",
    ]:
        if os.path.exists(_env_file):
            load_dotenv(_env_file, override=False)
            break
except ImportError:
    pass

class Config:
    FLASK_ENV = os.environ.get("FLASK_ENV", "development")
    DEBUG = FLASK_ENV != "production"

    # Security: production must set SECRET_KEY; dev uses env or .flask_secret file
    _secret_key = os.environ.get("SECRET_KEY")
    if not _secret_key and FLASK_ENV == "production":
        raise RuntimeError(
            "SECRET_KEY environment variable is required when FLASK_ENV=production"
        )
    if not _secret_key:
        _instance_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "instance")
        os.makedirs(_instance_dir, exist_ok=True)
        _dev_key_file = os.path.join(_instance_dir, ".flask_secret")
        if os.path.exists(_dev_key_file):
            with open(_dev_key_file, encoding="utf-8") as _f:
                _secret_key = _f.read().strip()
        else:
            _secret_key = secrets.token_hex(32)
            with open(_dev_key_file, "w", encoding="utf-8") as _f:
                _f.write(_secret_key)
    SECRET_KEY = _secret_key

    # Database
    _input_db_uri = os.environ.get("DATABASE_URL", "").strip()
    if not _input_db_uri and FLASK_ENV == "production":
        raise RuntimeError(
            "DATABASE_URL environment variable is required when FLASK_ENV=production"
        )

    if not _input_db_uri:
        _input_db_uri = (
            f"sqlite:///{os.path.join(os.path.dirname(os.path.dirname(__file__)), 'ideahub_local.db')}"
        )

    SQLALCHEMY_DATABASE_URI = _input_db_uri
    if _input_db_uri.startswith("sqlite"):
        SQLALCHEMY_ENGINE_OPTIONS = {}
    else:
        SQLALCHEMY_ENGINE_OPTIONS = {
            "pool_pre_ping": True,
            "pool_recycle": _env_int("DB_POOL_RECYCLE", 280, 1),
            "pool_timeout": _env_int("DB_POOL_TIMEOUT", 15, 1),
            "pool_size": _env_int("DB_POOL_SIZE", 10, 1),
            "max_overflow": _env_int("DB_MAX_OVERFLOW", 10, 0),
        }

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Security Headers
    SECURITY_HEADERS = {
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'DENY',
        'X-XSS-Protection': '1; mode=block',
        'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
        'Content-Security-Policy': (
            "default-src 'self'; "
            "base-uri 'self'; object-src 'none'; frame-ancestors 'self'; "
            "form-action 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net "
            "https://cdn.socket.io https://challenges.cloudflare.com "
            "https://static.cloudflareinsights.com; "
            "script-src-elem 'self' 'unsafe-inline' https://cdn.jsdelivr.net "
            "https://cdn.socket.io https://challenges.cloudflare.com "
            "https://static.cloudflareinsights.com; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net "
            "https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net; "
            "img-src 'self' data: https://media.idea-flows.online; "
            "connect-src 'self' ws: wss: https://cdn.jsdelivr.net "
            "https://cdn.socket.io https://cloudflareinsights.com; "
            "frame-src https://challenges.cloudflare.com;"
        ),
    }

    # File Upload Settings (Production-Ready)
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10MB max total request size
    UPLOAD_MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB max per file
    ALLOWED_UPLOAD_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    # On VPS, set UPLOAD_FOLDER=/var/www/pos/static/uploads/menu in .env
    # Falls back to local static dir for development
    UPLOAD_FOLDER = os.environ.get(
        'UPLOAD_FOLDER',
        os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'uploads', 'menu')
    )

    # Cloudflare R2 media storage. When every value is present, new menu images
    # are written to R2; otherwise development keeps using the local folder.
    R2_MEDIA_BUCKET = os.environ.get("R2_MEDIA_BUCKET", "").strip()
    R2_MEDIA_ENDPOINT = os.environ.get("R2_MEDIA_ENDPOINT", "").strip().rstrip("/")
    R2_MEDIA_ACCESS_KEY_ID = os.environ.get("R2_MEDIA_ACCESS_KEY_ID", "").strip()
    R2_MEDIA_SECRET_ACCESS_KEY = os.environ.get("R2_MEDIA_SECRET_ACCESS_KEY", "").strip()
    R2_MEDIA_PUBLIC_URL = os.environ.get("R2_MEDIA_PUBLIC_URL", "").strip().rstrip("/")
    R2_MEDIA_PREFIX = os.environ.get("R2_MEDIA_PREFIX", "menu").strip().strip("/") or "menu"

    _r2_media_values = {
        "R2_MEDIA_BUCKET": R2_MEDIA_BUCKET,
        "R2_MEDIA_ENDPOINT": R2_MEDIA_ENDPOINT,
        "R2_MEDIA_ACCESS_KEY_ID": R2_MEDIA_ACCESS_KEY_ID,
        "R2_MEDIA_SECRET_ACCESS_KEY": R2_MEDIA_SECRET_ACCESS_KEY,
        "R2_MEDIA_PUBLIC_URL": R2_MEDIA_PUBLIC_URL,
    }
    if any(_r2_media_values.values()) and not all(_r2_media_values.values()):
        _missing_r2_media = ", ".join(
            name for name, value in _r2_media_values.items() if not value
        )
        raise RuntimeError(
            f"Cloudflare R2 media configuration is incomplete; missing: {_missing_r2_media}"
        )
    R2_MEDIA_ENABLED = all(_r2_media_values.values())

    # Cloudflare Turnstile login protection. Both keys are required together;
    # leaving both blank keeps local development and staged deployments working.
    TURNSTILE_SITE_KEY = os.environ.get("TURNSTILE_SITE_KEY", "").strip()
    TURNSTILE_SECRET_KEY = os.environ.get("TURNSTILE_SECRET_KEY", "").strip()
    if bool(TURNSTILE_SITE_KEY) != bool(TURNSTILE_SECRET_KEY):
        raise RuntimeError(
            "Cloudflare Turnstile configuration is incomplete; both "
            "TURNSTILE_SITE_KEY and TURNSTILE_SECRET_KEY are required"
        )
    TURNSTILE_ENABLED = bool(TURNSTILE_SITE_KEY and TURNSTILE_SECRET_KEY)
    TURNSTILE_VERIFY_TIMEOUT = _env_int("TURNSTILE_VERIFY_TIMEOUT", 5, 1)
    TURNSTILE_EXPECTED_ACTION = "login"
    _turnstile_default_hostnames = (
        "idea-flows.online,www.idea-flows.online" if FLASK_ENV == "production" else ""
    )
    TURNSTILE_ALLOWED_HOSTNAMES = [
        hostname.strip().lower()
        for hostname in os.environ.get(
            "TURNSTILE_ALLOWED_HOSTNAMES", _turnstile_default_hostnames
        ).split(",")
        if hostname.strip()
    ]

    # Session Security
    SESSION_COOKIE_HTTPONLY = True
    # Lax works correctly when HTTPS termination is handled by Nginx (our VPS setup).
    # Using 'None' would require Secure=True AND cross-site context — not needed here.
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = os.environ.get('FLASK_ENV') == 'production'
    PERMANENT_SESSION_LIFETIME = 7200  # 2 hours

    # Rate Limiting
    RATELIMIT_DEFAULT = os.environ.get("RATELIMIT_DEFAULT", "100 per minute")
    REDIS_URL = os.environ.get("REDIS_URL", "").strip() or None
    REDIS_REQUIRED = _env_bool("REDIS_REQUIRED", FLASK_ENV == "production")
    RATELIMIT_STORAGE_URI = REDIS_URL or "memory://"
    RATELIMIT_STORAGE_URL = RATELIMIT_STORAGE_URI
    RATELIMIT_IN_MEMORY_FALLBACK_ENABLED = True
    RATELIMIT_SWALLOW_ERRORS = True

    # Redis lets Socket.IO broadcasts and rate limits work across processes/hosts.
    SOCKETIO_MESSAGE_QUEUE = REDIS_URL
    # Phase 7 standardizes every environment on Flask-SocketIO's threaded
    # transport. Keeping this explicit prevents a stale production .env value
    # from silently re-enabling the removed Eventlet runtime.
    SOCKETIO_ASYNC_MODE = "threading"

    # Short-lived read-through caching. Operational/live transaction data is
    # deliberately excluded; menu mutations explicitly invalidate these keys.
    CACHE_ENABLED = _env_bool("CACHE_ENABLED", True)
    CACHE_DEFAULT_TIMEOUT = _env_int("CACHE_DEFAULT_TIMEOUT", 60, 1)
    CACHE_KEY_PREFIX = os.environ.get("CACHE_KEY_PREFIX", "ideahub").strip() or "ideahub"

    # Reverse-proxy hops trusted by ProxyFix. Keep these at zero when Flask is
    # directly internet-facing; the supplied Nginx deployment uses one hop.
    PROXY_FIX_X_FOR = _env_int("PROXY_FIX_X_FOR", 1, 0)
    PROXY_FIX_X_PROTO = _env_int("PROXY_FIX_X_PROTO", 1, 0)
    PROXY_FIX_X_HOST = _env_int("PROXY_FIX_X_HOST", 1, 0)

    # Operational controls
    AUTO_MIGRATE_ON_STARTUP = _env_bool("AUTO_MIGRATE_ON_STARTUP", True)
    LOG_DIR = os.environ.get("LOG_DIR", "").strip() or None
    LOG_MAX_BYTES = _env_int("LOG_MAX_BYTES", 10 * 1024 * 1024, 1024)
    LOG_BACKUP_COUNT = _env_int("LOG_BACKUP_COUNT", 5, 1)
    SLOW_REQUEST_MS = _env_int("SLOW_REQUEST_MS", 1000, 0)
    INITIAL_ADMIN_PASSWORD = os.environ.get("INITIAL_ADMIN_PASSWORD", "")

    # CORS Settings (restrictive)
    # In production, CORS_ORIGINS env var must be set to your domain.
    # Default below covers local dev; VPS .env sets: https://idea-flows.online,https://www.idea-flows.online
    _default_cors = (
        'https://idea-flows.online,https://www.idea-flows.online'
        if FLASK_ENV == 'production'
        else 'http://localhost:5000,http://127.0.0.1:5000'
    )
    CORS_ORIGINS = [
        origin.strip()
        for origin in os.environ.get('CORS_ORIGINS', _default_cors).split(',')
        if origin.strip()
    ]

    # Password Policy
    PASSWORD_MIN_LENGTH = 12
    PASSWORD_REQUIRE_UPPERCASE = True
    PASSWORD_REQUIRE_LOWERCASE = True
    PASSWORD_REQUIRE_DIGITS = True
    PASSWORD_REQUIRE_SPECIAL = True

    # Account Lockout
    MAX_LOGIN_ATTEMPTS = 5
    LOCKOUT_DURATION = 900  # 15 minutes

    # Bot Defense & Honeypot Configuration
    # Uses HONEYPOT_SECRET_PATH from env if provided; otherwise derives a stable
    # pseudorandom route from SECRET_KEY hash so it is never a predictable hardcoded string.
    _hp_env = os.environ.get("HONEYPOT_SECRET_PATH")
    if _hp_env:
        HONEYPOT_SECRET_PATH = _hp_env if _hp_env.startswith("/") else f"/{_hp_env}"
    else:
        import hashlib
        _hp_token = hashlib.sha256((SECRET_KEY + "honeypot_seed").encode("utf-8")).hexdigest()[:16]
        HONEYPOT_SECRET_PATH = f"/_trap_{_hp_token}"


