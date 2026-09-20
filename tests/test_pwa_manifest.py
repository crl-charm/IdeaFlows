import json
import re
from pathlib import Path

import pytest
from PIL import Image

from app import create_app


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
TEMPLATES = ROOT / "app" / "templates"


def _js_array(source, name):
    match = re.search(rf"const {name} = (\[.*?\]);", source, re.DOTALL)
    assert match, name
    return set(json.loads(match.group(1).replace("OFFLINE_URL", '"/static/offline.html"')))


@pytest.fixture
def app():
    application = create_app()
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return application


def test_manifest_identity_and_icons():
    manifest = json.loads((STATIC / "manifest.webmanifest").read_text(encoding="utf-8"))

    assert manifest["id"] == "/"
    assert manifest["start_url"] == "/welcome"
    assert manifest["scope"] == "/"
    assert manifest["display"] == "standalone"

    for icon in manifest["icons"]:
        path = STATIC / icon["src"].removeprefix("/static/")
        expected = tuple(map(int, icon["sizes"].split("x")))
        with Image.open(path) as image:
            assert image.format == "PNG"
            assert image.size == expected

    with Image.open(STATIC / "icons" / "apple-touch-icon.png") as apple_icon:
        assert apple_icon.format == "PNG"
        assert apple_icon.size == (180, 180)


def test_manifest_delivery_and_shared_metadata(app):
    client = app.test_client()
    manifest = client.get("/manifest.webmanifest")

    assert manifest.status_code == 200
    assert manifest.content_type == "application/manifest+json"
    for path in ("/", "/welcome", "/login"):
        page = client.get(path)
        assert page.status_code == 200
        assert b'rel="manifest" href="/manifest.webmanifest"' in page.data
        assert b'rel="apple-touch-icon"' in page.data


def test_install_controller_is_progressively_enhanced():
    controller = (STATIC / "js" / "pwa-install.js").read_text(encoding="utf-8")
    partial = (TEMPLATES / "partials" / "pwa_install.html").read_text(encoding="utf-8")

    assert "beforeinstallprompt" in controller
    assert "appinstalled" in controller
    assert 'matchMedia("(display-mode: standalone)")' in controller
    assert "Add IdeaFlow to Home Screen" in controller
    assert "navigator.standalone === true" in controller
    assert "data-pwa-install hidden" in partial
    assert "Share" in partial and "Add to Home Screen" in partial

    for name in ("login.html", "landing.html"):
        assert 'include "partials/pwa_install.html"' in (
            TEMPLATES / name
        ).read_text(encoding="utf-8")


def test_service_worker_delivery_and_safe_cache_boundary(app):
    client = app.test_client()
    response = client.get("/sw.js")
    worker = (STATIC / "sw.js").read_text(encoding="utf-8")
    registration = (STATIC / "js" / "pwa-register.js").read_text(encoding="utf-8")
    offline = (STATIC / "offline.html").read_text(encoding="utf-8")

    assert response.status_code == 200
    assert response.content_type == "application/javascript"
    assert response.headers["Cache-Control"] == "no-cache"
    assert response.headers["Service-Worker-Allowed"] == "/"
    assert "worker-src 'self'" in response.headers["Content-Security-Policy"]
    assert "manifest-src 'self'" in response.headers["Content-Security-Policy"]
    assert 'register("/sw.js", { scope: "/" })' in registration
    assert 'request.method !== "GET"' in worker
    assert 'request.mode === "navigate"' in worker
    assert 'url.origin !== self.location.origin' in worker
    assert '"/api/"' in worker
    assert '"/socket.io/"' in worker
    assert '"/static/uploads/"' in worker
    assert '"/static/js/pwa-register.js"' not in worker
    assert worker.index('request.mode === "navigate"') < worker.index(
        "NETWORK_ONLY_PREFIXES.some"
    )
    assert worker.count("cache.put(") == 1
    assert "cache.put(path, response)" in worker
    assert "no-store" in worker
    assert "backgroundsync" not in worker.lower()
    assert "needs an internet connection for live business data" in offline


def test_cache_allowlist_is_complete_and_contains_no_private_routes():
    worker = (STATIC / "sw.js").read_text(encoding="utf-8")
    expected = {
        "/manifest.webmanifest",
        "/static/offline.html",
        "/static/icons/apple-touch-icon.png",
        "/static/icons/icon-192.png",
        "/static/icons/icon-512.png",
        "/static/icons/icon-maskable-192.png",
        "/static/icons/icon-maskable-512.png",
        "/static/css/pwa-install.css",
        "/static/js/pwa-install.js",
    }

    assert _js_array(worker, "PRECACHE_URLS") == expected
    assert {"/api/", "/socket.io/", "/admin", "/login", "/static/uploads/"} <= (
        _js_array(worker, "NETWORK_ONLY_PREFIXES")
    )
    assert not any(
        marker in path
        for path in expected
        for marker in ("api", "admin", "report", "socket", "upload", "login")
    )
    assert 'name.startsWith("ideaflow-")' in worker
    assert "caches.delete(name)" in worker
    assert "caches.match(OFFLINE_URL)" in worker


def test_updates_require_user_action_and_one_controlled_reload():
    worker = (STATIC / "sw.js").read_text(encoding="utf-8")
    registration = (STATIC / "js" / "pwa-register.js").read_text(encoding="utf-8")

    assert 'event.data.type === "SKIP_WAITING"' in worker
    assert "registration.waiting" in registration
    assert 'registration.addEventListener("updatefound"' in registration
    assert 'navigator.serviceWorker.addEventListener("controllerchange"' in registration
    assert 'waitingWorker.postMessage({ type: "SKIP_WAITING" })' in registration
    assert 'event.target.closest("form")' in registration
    assert "You have unsaved changes" in registration
    assert "if (!updateRequested || reloadStarted) return" in registration
    assert registration.count("window.location.reload()") == 1
    assert 'sessionStorage.getItem("ideaflow-sw-reload")' in registration


def test_update_controller_is_always_revalidated(app):
    response = app.test_client().get("/static/js/pwa-register.js")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-cache"
