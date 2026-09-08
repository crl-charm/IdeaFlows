import os
import secrets

# Load .env configuration if present
try:
    from dotenv import load_dotenv
    for _env_file in [
        os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"),
        "/var/www/pos/.env",
        "/var/www/ideahub/.env",
        ".env",
    ]:
        if os.path.exists(_env_file):
            load_dotenv(_env_file, override=False)
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
        _dev_key_file = os.path.join(os.path.dirname(__file__), ".flask_secret")
        if os.path.exists(_dev_key_file):
            with open(_dev_key_file, encoding="utf-8") as _f:
                _secret_key = _f.read().strip()
        else:
            _secret_key = secrets.token_hex(32)
            with open(_dev_key_file, "w", encoding="utf-8") as _f:
                _f.write(_secret_key)
    SECRET_KEY = _secret_key

    # Database
    from urllib.parse import urlsplit, urlunsplit

    _input_db_uri = os.environ.get("DATABASE_URL") or "mysql+pymysql://pos_user:@localhost/pos_db"
    try:
        _parsed = urlsplit(_input_db_uri)
        _pwd = (
            _parsed.password
            or os.environ.get("DB_PASSWORD")
            or os.environ.get("DATABASE_PASSWORD")
            or os.environ.get("MYSQL_PASSWORD")
            or "k8F9vP2xM7wQ1tZ4_9B!"
        )
        _hostname = _parsed.hostname or "localhost"
        _port_str = f":{_parsed.port}" if _parsed.port else ""
        _netloc = f"pos_user:{_pwd}@{_hostname}{_port_str}"
        _scheme = _parsed.scheme or "mysql+pymysql"
        _path = "/pos_db"
        _raw_db_uri = urlunsplit((_scheme, _netloc, _path, _parsed.query, _parsed.fragment))
    except Exception:
        _pwd = os.environ.get("DB_PASSWORD") or "k8F9vP2xM7wQ1tZ4_9B!"
        _raw_db_uri = f"mysql+pymysql://pos_user:{_pwd}@localhost/pos_db"

    # PyMySQL does not support ssl_mode/ssl-mode in query string directly; handle SSL via connect_args
    _needs_ssl = "aivencloud.com" in _raw_db_uri or "ssl_mode" in _raw_db_uri or "ssl-mode" in _raw_db_uri
    if "?" in _raw_db_uri and ("ssl_mode" in _raw_db_uri or "ssl-mode" in _raw_db_uri):
        _base_uri = _raw_db_uri.split("?")[0]
        SQLALCHEMY_DATABASE_URI = _base_uri
    else:
        SQLALCHEMY_DATABASE_URI = _raw_db_uri

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    _engine_options = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
        "pool_timeout": 15,
        "pool_size": 20,
        "max_overflow": 10,
    }
    if _needs_ssl:
        _engine_options["connect_args"] = {"ssl": {}}

    SQLALCHEMY_ENGINE_OPTIONS = _engine_options

    # Security Headers
    SECURITY_HEADERS = {
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'DENY',
        'X-XSS-Protection': '1; mode=block',
        'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
        'Content-Security-Policy': "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://code.jquery.com https://cdn.socket.io; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net; img-src 'self' data: https:; connect-src 'self' ws: wss:;",
    }

    # File Upload Settings (Production-Ready)
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10MB max total request size
    UPLOAD_MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB max per file
    ALLOWED_UPLOAD_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    # On VPS, set UPLOAD_FOLDER=/var/www/ideahub/static/uploads/menu in .env
    # Falls back to local static dir for development
    UPLOAD_FOLDER = os.environ.get(
        'UPLOAD_FOLDER',
        os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'uploads', 'menu')
    )

    # Session Security
    SESSION_COOKIE_HTTPONLY = True
    # Lax works correctly when HTTPS termination is handled by Nginx (our VPS setup).
    # Using 'None' would require Secure=True AND cross-site context — not needed here.
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = os.environ.get('FLASK_ENV') == 'production'
    PERMANENT_SESSION_LIFETIME = 7200  # 2 hours

    # Rate Limiting
    RATELIMIT_DEFAULT = "100 per minute"
    RATELIMIT_STORAGE_URL = "memory://"

    # CORS Settings (restrictive)
    # In production, CORS_ORIGINS env var must be set to your domain.
    # Default below covers local dev; VPS .env sets: https://idea-flows.online,https://www.idea-flows.online
    _default_cors = (
        'https://idea-flows.online,https://www.idea-flows.online'
        if FLASK_ENV == 'production'
        else 'http://localhost:5000,http://127.0.0.1:5000'
    )
    CORS_ORIGINS = os.environ.get('CORS_ORIGINS', _default_cors).split(',')

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


