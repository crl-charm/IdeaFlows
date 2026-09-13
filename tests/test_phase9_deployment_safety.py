"""Phase 9 regression tests for production configuration and data boundaries."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from app import create_app


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def app():
    application = create_app()
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return application


def test_production_configuration_starts_with_required_integrations(app):
    environment = os.environ.copy()
    environment.update(
        {
            "FLASK_ENV": "production",
            "SECRET_KEY": "phase9-test-secret-key-not-for-production",
            "DATABASE_URL": "mysql+pymysql://test:hidden@127.0.0.1/phase9_test",
            "REDIS_URL": "redis://127.0.0.1:6379/0",
            "REDIS_REQUIRED": "true",
            "AUTO_MIGRATE_ON_STARTUP": "false",
            "R2_MEDIA_BUCKET": "phase9-test",
            "R2_MEDIA_ENDPOINT": "https://example.r2.cloudflarestorage.com",
            "R2_MEDIA_ACCESS_KEY_ID": "test-access-key",
            "R2_MEDIA_SECRET_ACCESS_KEY": "test-secret-key",
            "R2_MEDIA_PUBLIC_URL": "https://media.example.test",
            "TURNSTILE_SITE_KEY": "test-site-key",
            "TURNSTILE_SECRET_KEY": "test-secret-key",
        }
    )
    code = """
import json
from config import Config
print(json.dumps({
    "environment": Config.FLASK_ENV,
    "database": Config.SQLALCHEMY_DATABASE_URI.startswith("mysql+pymysql://"),
    "redis": bool(Config.REDIS_URL),
    "redis_required": Config.REDIS_REQUIRED,
    "r2": Config.R2_MEDIA_ENABLED,
    "turnstile": Config.TURNSTILE_ENABLED,
    "auto_migrate": Config.AUTO_MIGRATE_ON_STARTUP,
    "socketio": Config.SOCKETIO_ASYNC_MODE,
}))
"""

    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout.strip())

    assert result == {
        "environment": "production",
        "database": True,
        "redis": True,
        "redis_required": True,
        "r2": True,
        "turnstile": True,
        "auto_migrate": False,
        "socketio": "threading",
    }


def test_runtime_data_paths_are_ignored_by_git(app):
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert "instance/" in gitignore
    assert "*.db" in gitignore
    assert "static/uploads/" in gitignore
