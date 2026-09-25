"""Phase 7 regression tests for the threaded real-time runtime."""

from pathlib import Path
from importlib.util import find_spec

import pytest

from app import create_app, socketio


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def app():
    application = create_app()
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return application


def test_socketio_uses_threading_mode(app):

    assert app.config["SOCKETIO_ASYNC_MODE"] == "threading"
    assert socketio.server.async_mode == "threading"


def test_simple_websocket_dependency_is_loadable(app):
    assert find_spec("simple_websocket") is not None


def test_eventlet_is_absent_from_active_runtime_files(app):
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    constraints = (ROOT / "constraints.txt").read_text(encoding="utf-8").lower()
    wsgi = (ROOT / "wsgi.py").read_text(encoding="utf-8").lower()

    assert "eventlet" not in requirements
    assert "eventlet" not in constraints
    assert "eventlet" not in wsgi
    assert "simple-websocket" in requirements


def test_phase7_service_uses_one_threaded_worker(app):
    override = (
        ROOT / "deploy" / "phase7-threaded-socketio-override.conf"
    ).read_text(encoding="utf-8")

    assert "--worker-class gthread" in override
    assert "--threads 50" in override
    assert "--workers 1" in override
    assert "--bind 127.0.0.1:5000" in override
