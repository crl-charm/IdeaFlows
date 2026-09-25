"""Regression coverage for the shared, non-invasive UI motion layer."""

from pathlib import Path

import pytest

from app import create_app


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "app" / "templates"
MOTION_CSS = (ROOT / "static" / "css" / "motion.css").read_text(encoding="utf-8")
MOTION_JS = (ROOT / "static" / "js" / "motion.js").read_text(encoding="utf-8")


@pytest.fixture
def app():
    application = create_app()
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return application


def test_primary_layouts_load_the_shared_motion_assets():
    for name in ("layout.html", "auth_layout.html"):
        source = (TEMPLATES / name).read_text(encoding="utf-8")
        assert "css/motion.css" in source, name
        assert "js/motion.js" in source, name
        assert 'class="ih-navigation-progress"' in source, name
        assert "ih-skeleton-shell" in source, name

    assert "ih-skeleton-app" in (TEMPLATES / "layout.html").read_text(encoding="utf-8")
    assert "ih-skeleton-auth" in (TEMPLATES / "auth_layout.html").read_text(encoding="utf-8")


def test_skeleton_is_non_blocking_and_has_script_failure_failsafe():
    assert ".ih-skeleton-shell" in MOTION_CSS
    assert "pointer-events: none" in MOTION_CSS
    assert "ih-skeleton-failsafe" in MOTION_CSS
    assert "html.ih-content-ready .ih-skeleton-shell" in MOTION_CSS
    assert 'root.classList.add("ih-content-ready")' in MOTION_JS
    assert 'window.addEventListener("load", revealContent' in MOTION_JS
    assert "window.setTimeout(revealContent, 1500)" in MOTION_JS


def test_motion_layer_supports_cross_page_navigation_and_reduced_motion():
    assert "@view-transition" in MOTION_CSS
    assert "navigation: auto" in MOTION_CSS
    assert "::view-transition-new(root)" in MOTION_CSS
    assert "@media (prefers-reduced-motion: reduce)" in MOTION_CSS
    assert "scroll-behavior: auto" in MOTION_CSS
    reduced_motion = MOTION_CSS.split("@media (prefers-reduced-motion: reduce)", 1)[1]
    assert "*::before" not in reduced_motion
    assert "*::after" not in reduced_motion


def test_finished_page_entrance_does_not_trap_modals_under_their_backdrop():
    fallback_rule = MOTION_CSS.split(
        "/* A restrained progress line", 1
    )[0].rsplit("html.ih-motion-ready", 1)[1]
    assert (
        "animation: ih-content-in var(--ih-motion-slow) "
        "var(--ih-ease-enter) backwards;"
    ) in fallback_rule
    assert "#main-content {\n  view-transition-name:" not in MOTION_CSS
    assert "::view-transition-new(ideaflow-main)" not in MOTION_CSS


def test_auth_image_retains_its_desktop_slide_transition():
    assert "@media (min-width: 992px)" in MOTION_CSS
    assert ".auth-sliding-panel" in MOTION_CSS
    assert "transition: transform 750ms" in MOTION_CSS
    assert ".auth-hero-img" in MOTION_CSS
    assert ".auth-split-container.is-login-mode .auth-hero-img" in MOTION_CSS


def test_navigation_feedback_preserves_native_page_loading():
    assert 'document.addEventListener("click"' in MOTION_JS
    assert 'window.addEventListener("beforeunload"' in MOTION_JS
    assert "event.preventDefault" not in MOTION_JS
    assert "fetch(" not in MOTION_JS
    assert "innerHTML" not in MOTION_JS
    assert "location.href =" not in MOTION_JS


def test_navigation_feedback_ignores_nonstandard_links():
    assert 'link.hasAttribute("download")' in MOTION_JS
    assert 'link.target && link.target !== "_self"' in MOTION_JS
    assert "isModifiedClick(event)" in MOTION_JS
    assert "parsed.origin === window.location.origin" in MOTION_JS
