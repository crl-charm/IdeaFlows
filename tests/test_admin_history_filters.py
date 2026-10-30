"""Admin visit/event periods use Manila dates without deleting any history."""

from datetime import datetime

import pytest
from sqlalchemy import event

from app import create_app, db
from app.models import CustomerSession, SpaceType, StaffAttendance, StaffShift, User
from app.routes import admin_routes
from app.services.admin_service import AdminService
from app.repositories.admin_repository import AdminRepository
from app.utils.dates import entered_manila_time, history_period
from tests.test_staff_shifts import _signed_in


@pytest.fixture
def app():
    application = create_app()
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False, SINGLE_SESSION_ENABLED=False)
    return application


@pytest.fixture
def clock(monkeypatch):
    value = [datetime(2026, 10, 30, 4)]  # Noon in Manila, not the computer's local date.
    monkeypatch.setattr(admin_routes, "history_period", lambda period="today", month=None: history_period(period, month, now=value[0]))
    return value


def _at(value):
    return entered_manila_time(value)


def _visits():
    space = SpaceType(name="Regular Lounge", rate_per_minute=1)
    db.session.add(space)
    db.session.flush()
    specs = [
        ("Carl", "2026-10-30T00:00", "active", "timed", 1),
        ("Carl", "2026-10-30T09:00", "completed", "timed", 1),
        ("Food customer", "2026-10-30T10:00", "active", "food_only", 1),
        ("Boardroom group", "2026-10-30T11:00", "active", "timed", 8),
        ("Cancelled", "2026-10-30T11:30", "cancelled", "timed", 1),
        ("Future", "2026-10-31T00:00", "active", "timed", 1),
        ("Overnight", "2026-10-29T23:59", "completed", "timed", 1),
        ("Month start", "2026-10-01T00:00", "completed", "timed", 1),
        ("September last", "2026-09-30T23:59", "completed", "timed", 1),
        ("September first", "2026-09-01T00:00", "completed", "timed", 1),
    ]
    for name, at, status, mode, people in specs:
        db.session.add(CustomerSession(customer_name=name, space_type_id=space.id,
                                      time_in=_at(at), status=status, service_mode=mode,
                                      number_of_people=people,
                                      time_out=_at("2026-10-30T01:00") if name == "Overnight" else None))
    db.session.commit()


def test_customer_period_totals_match_paginated_records_and_preserve_rows(app, clock):
    with app.app_context():
        _visits()
        before = [(row.id, row.customer_name, row.status, row.time_in, row.time_out)
                  for row in CustomerSession.query.order_by(CustomerSession.id)]
    client = _signed_in(app, "admin")
    for query, expected in [("", 4), ("period=yesterday", 1),
                            ("period=month&month=2026-10", 6),
                            ("period=month&month=2026-09", 2), ("period=all", 8)]:
        count = client.get("/api/admin/customer-count?" + query).get_json()
        rows, page = [], 1
        while True:
            response = client.get(f"/api/admin/customer-records?{query}&page={page}&per_page=2")
            assert response.status_code == 200
            result = response.get_json()
            assert result["total"] == count["count"] == expected
            assert result["filter"]["label"] == count["filter"]["label"]
            rows.extend(result["data"])
            if not result["has_next"]:
                break
            page += 1
        assert len(rows) == len({row["id"] for row in rows}) == expected
        if not query:
            assert [row["name"] for row in rows].count("Carl") == 2
            assert next(row for row in rows if row["service_mode"] == "food_only")["visit_date"] == "2026-10-30"
            assert next(row for row in rows if row["name"] == "Food customer")["time_in"].startswith("2026-10-30")
    with app.app_context():
        assert before == [(row.id, row.customer_name, row.status, row.time_in, row.time_out)
                          for row in CustomerSession.query.order_by(CustomerSession.id)]


def test_midnight_rollover_preserves_yesterday_and_fixed_month(app, clock):
    with app.app_context():
        _visits()
    client = _signed_in(app, "admin")
    clock[0] = datetime(2026, 10, 30, 15, 59, 59)
    assert client.get("/api/admin/customer-count").get_json()["count"] == 4
    clock[0] = datetime(2026, 10, 30, 16)  # October 31 at exactly 00:00 Manila.
    result = client.get("/api/admin/customer-count").get_json()
    assert result["count"] == 0
    assert result["filter"]["today"] == result["filter"]["end_date"] == "2026-10-31"
    assert client.get("/api/admin/customer-count?period=yesterday").get_json()["count"] == 4
    assert client.get("/api/admin/customer-count?period=month&month=2026-10").get_json()["count"] == 6
    with app.app_context():
        assert CustomerSession.query.count() == 10


@pytest.mark.parametrize(("value", "month", "at", "first", "last"), [
    ("today", None, datetime(2026, 10, 29, 16), "2026-10-30", "2026-10-30"),
    ("yesterday", None, datetime(2026, 10, 30, 4), "2026-10-29", "2026-10-29"),
    ("month", "2026-10", datetime(2026, 10, 1, 1), "2026-10-01", "2026-10-01"),
    ("month", "2024-02", datetime(2026, 10, 30), "2024-02-01", "2024-02-29"),
    ("month", "2025-12", datetime(2026, 1, 1), "2025-12-01", "2025-12-31"),
])
def test_period_bounds_and_calendar_edges(value, month, at, first, last):
    start, end, info = history_period(value, month, now=at)
    assert start == _at(first + "T00:00")
    assert end <= at
    assert info["start_date"] == first and info["end_date"] == last
    assert 0 < info["next_day_in_seconds"] <= 86400


@pytest.mark.parametrize("query", [
    "period=bad", "period=month", "month=2026-09", "period=today&month=2026-09",
    "period=month&month=2026-9", "period=month&month=2026-13",
    "period=month&month=2026-11", "period=today&period=yesterday", "period=today&date=2026-10-01",
])
def test_customer_filters_reject_invalid_and_conflicting_values(app, clock, query):
    client = _signed_in(app, "admin")
    for endpoint in ("customer-count", "customer-records"):
        result = client.get(f"/api/admin/{endpoint}?{query}")
        assert result.status_code == 400 and result.get_json()["error"]


def test_pagination_and_admin_access_are_enforced(app, clock):
    client = _signed_in(app, "admin")
    for query in ("page=0", "page=1000001", "per_page=101", "per_page=0", "page=x", "page=1&page=2"):
        assert client.get("/api/admin/customer-records?" + query).status_code == 400
    for endpoint in ("customer-count", "customer-records", "staff-attendance?events=1&period=today"):
        assert app.test_client().get("/api/admin/" + endpoint).status_code == 401
        assert _signed_in(app).get("/api/admin/" + endpoint).status_code == 403


def test_staff_period_filters_each_event_and_preserves_paired_context(app, clock):
    with app.app_context():
        former = User(username="former", full_name="Former Staff", role="staff", is_active=False)
        former.set_password("SyntheticOnly123!")
        db.session.add(former)
        db.session.flush()
        db.session.add_all([
            StaffShift(user_id=1, shift_role="cashier", time_in=_at("2026-10-29T23:55"), time_out=_at("2026-10-30T00:05")),
            StaffShift(user_id=1, shift_role="cook", time_in=_at("2026-10-30T10:00")),
            StaffShift(user_id=former.id, shift_role="server", time_in=_at("2026-10-30T09:00"), time_out=_at("2026-10-30T11:00")),
            StaffAttendance(user_id=1, time_in=_at("2026-09-01T09:00"), time_out=_at("2026-09-01T10:00"), show_in_history=True),
            StaffAttendance(user_id=1, time_in=_at("2026-10-30T08:00"), time_out=_at("2026-10-30T09:00"), show_in_history=False),
        ])
        db.session.commit()
    client = _signed_in(app, "admin")
    endpoint = "/api/admin/staff-attendance?events=1&period="
    today = client.get(endpoint + "today").get_json()
    yesterday = client.get(endpoint + "yesterday").get_json()
    assert today["total"] == 4 and yesterday["total"] == 1
    assert all(row["event_date"] == "2026-10-30" for row in today["data"])
    overnight = next(row for row in today["data"] if row["shift_role"] == "Cashier")
    assert overnight["event"] == "Time Out" and overnight["paired_time"].startswith("2026-10-29")
    assert any(row["name"] == "Former Staff" for row in today["data"])
    assert any(row["paired_time"] == "Open shift" for row in today["data"])
    assert client.get(endpoint + "month&month=2026-09").get_json()["total"] == 2
    all_rows = client.get(endpoint + "all").get_json()
    assert all_rows["total"] == 7
    assert {row["source"] for row in all_rows["data"]} == {"Manual shift", "Legacy login record"}
    first = client.get(endpoint + "today&per_page=2").get_json()
    second = client.get(endpoint + "today&per_page=2&page=2").get_json()
    assert len({row["id"] for row in first["data"] + second["data"]}) == 4
    assert client.get(endpoint + "today&date=2026-10-01").status_code == 400
    with app.app_context():
        assert User.query.filter_by(role="staff", is_active=True).count() == 1
        assert StaffShift.query.count() == 3 and StaffAttendance.query.count() == 2


def test_customer_count_and_paged_records_use_bounded_database_queries(app, clock):
    with app.app_context():
        _visits()
        service = AdminService(AdminRepository())
        start, end, _ = history_period(now=clock[0])
        statements = []

        def capture(connection, cursor, statement, parameters, context, executemany):
            if statement.lstrip().upper().startswith("SELECT"):
                statements.append(statement)

        event.listen(db.engine, "before_cursor_execute", capture)
        try:
            assert service.customer_count(start, end) == 4
            assert len(statements) == 1 and "count(" in statements[0].lower()
            statements.clear()
            assert len(service.customer_records(start, end, page=1, per_page=2)) == 2
            assert len(statements) <= 5
            assert "LIMIT" in statements[0].upper()
        finally:
            event.remove(db.engine, "before_cursor_execute", capture)
