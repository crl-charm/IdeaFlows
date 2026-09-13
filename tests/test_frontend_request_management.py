"""Regression tests for browser request and Socket.IO coordination."""

import re
from pathlib import Path

import pytest

from app import create_app


TEMPLATES = Path(__file__).resolve().parents[1] / "app" / "templates"


@pytest.fixture
def app():
    application = create_app()
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return application


def _template(relative_path):
    return (TEMPLATES / relative_path).read_text(encoding="utf-8")


def test_layout_defines_shared_socket_and_debounced_refresh_helpers():
    layout = _template("layout.html")

    assert "window.getIdeaFlowSocket = function getIdeaFlowSocket()" in layout
    assert "window.__ideaFlowSocket" in layout
    assert "window.createDebouncedRefresh = function createDebouncedRefresh" in layout
    assert "schedule.cancel = function ()" in layout


def test_pages_use_the_shared_socket_instead_of_opening_extra_connections():
    socket_pages = (
        "admin.html",
        "admin/expenses.html",
        "admin/inventory.html",
        "admin/menu.html",
        "admin/receivables.html",
        "staff/expenses.html",
        "menu.html",
        "order.html",
    )

    for page in socket_pages:
        source = _template(page)
        assert "window.getIdeaFlowSocket()" in source, page
        assert not re.search(r"(?<![\w.])io\s*\(\s*\)", source), page


def test_manual_initial_loads_do_not_get_repeated_by_pollers_immediately():
    expected = {
        "admin.html": (
            "createSmartPoller(loadUsers, 30000, { runImmediately: false })",
            "createSmartPoller(loadStaffAnalytics, 60000, { runImmediately: false })",
            "createSmartPoller(loadCapacity, 60000, { runImmediately: false })",
            "createSmartPoller(loadSpacePrices, 120000, { runImmediately: false })",
        ),
        "dashboard.html": (
            "createSmartPoller(loadSessions, 10000, { runImmediately: false })",
            "createSmartPoller(loadSpaceAvailability, 15000, { runImmediately: false })",
        ),
        "checkout_records.html": (
            "createSmartPoller(loadCheckoutRecords, 20000, { runImmediately: false })",
        ),
        "lounge_booking.html": (
            "createSmartPoller(loadSchedule, 30000, { runImmediately: false })",
        ),
    }

    for page, snippets in expected.items():
        source = _template(page)
        for snippet in snippets:
            assert snippet in source, f"{page}: {snippet}"


def test_hidden_sidebar_badges_do_not_poll_unused_endpoints():
    layout = _template("layout.html")

    assert layout.count("if (!badges.length) return;") >= 2
    assert '"/admin/receivables/api/receivables/unpaid"' in layout
    assert '"/receivables-view/api/receivables/unpaid"' in layout


def test_receivables_cancels_queued_socket_refresh_before_modal_reload():
    receivables = _template("admin/receivables.html")
    cancel_at = receivables.index("refreshReceivables.cancel();")
    reload_at = receivables.index(
        "fetch('/admin/receivables/api/receivables')", cancel_at
    )

    assert cancel_at < reload_at
