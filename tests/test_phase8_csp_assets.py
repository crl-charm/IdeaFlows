"""Phase 8 regression tests for browser assets and CSP allowlists."""

from pathlib import Path

import pytest

from app import create_app


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def app():
    application = create_app()
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return application


def _csp_directives(header: str) -> dict[str, list[str]]:
    directives = {}
    for raw_directive in header.split(";"):
        tokens = raw_directive.strip().split()
        if tokens:
            directives[tokens[0]] = tokens[1:]
    return directives


def test_csp_has_exact_browser_asset_origins_without_wildcards(app):
    response = app.test_client().get("/health/live")
    directives = _csp_directives(response.headers["Content-Security-Policy"])

    assert "https://static.cloudflareinsights.com" in directives["script-src"]
    assert "https://static.cloudflareinsights.com" in directives["script-src-elem"]
    assert "https://cdn.jsdelivr.net" in directives["connect-src"]
    assert "https://cdn.socket.io" in directives["connect-src"]
    assert "https://cloudflareinsights.com" in directives["connect-src"]
    assert "https://media.idea-flows.online" in directives["img-src"]
    assert directives["object-src"] == ["'none'"]
    assert all("*" not in source for sources in directives.values() for source in sources)
    assert all("https:" != source for sources in directives.values() for source in sources)


def test_shared_templates_use_consistent_pinned_asset_versions(app):
    layout = (ROOT / "app" / "templates" / "layout.html").read_text(encoding="utf-8")
    auth_layout = (
        ROOT / "app" / "templates" / "auth_layout.html"
    ).read_text(encoding="utf-8")
    analytics = (
        ROOT / "app" / "templates" / "analytics" / "_content.html"
    ).read_text(encoding="utf-8")

    for template in (layout, auth_layout):
        assert "bootstrap@5.3.3/dist/css/bootstrap.min.css" in template
        assert "bootstrap-icons@1.11.3/font/bootstrap-icons.css" in template
    assert "chart.js@4.4.7/dist/chart.umd.min.js" in analytics
    assert 'src="https://cdn.jsdelivr.net/npm/chart.js"' not in analytics
