"""Regular and Premium check-ins reserve exactly one seat per customer."""

from datetime import datetime
from decimal import Decimal
from time import time

import pytest

from app import create_app, db
from app.models import CustomerSession, SpaceType


@pytest.fixture
def app():
    application = create_app()
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False, SINGLE_SESSION_ENABLED=False)
    return application


@pytest.fixture
def client(app, isolated_database):
    with app.app_context():
        db.session.add_all([
            SpaceType(name="Regular Lounge", rate_per_minute=Decimal("0.1667"), capacity=4),
            SpaceType(name="Premium Lounge", rate_per_minute=Decimal("0.3333"), capacity=1),
            SpaceType(name="Boardroom", rate_per_minute=Decimal("4.1667")),
            SpaceType(name="Take Out", rate_per_minute=Decimal("0")),
        ])
        db.session.commit()
    client = app.test_client()
    with client.session_transaction() as auth:
        auth.update(user_id=1, username="test_user", role="staff", last_activity=time())
    return client


def test_lounge_form_and_api_allow_one_person_only(app, client):
    for url in ("/dashboard", "/dashboard?space=Regular+Lounge", "/dashboard?space=Premium+Lounge"):
        page = client.get(url)
        assert page.status_code == 200
        assert b'numberOfPeople' not in page.data
        assert b'One check-in per person.' in page.data

    regular = client.post("/api/checkin", json={"customer_name": "A", "space_type_id": 1})
    premium = client.post("/api/checkin", json={
        "customer_name": "B", "space_type_id": 2, "number_of_people": 1,
    })
    assert regular.status_code == premium.status_code == 200
    for space_id in (1, 2):
        for bad in (2, 0, -1, 1.0, 1.5, "1", "two", True, None, []):
            response = client.post("/api/checkin", json={
                "customer_name": "Rejected", "space_type_id": space_id, "number_of_people": bad,
            })
            assert response.status_code == 400, (space_id, bad, response.get_json())
    assert client.post("/api/checkin", json=[]).status_code == 400
    assert client.post("/api/checkin", json={
        "customer_name": "Take Out", "space_type_id": 4, "number_of_people": 1,
    }).status_code == 400
    full = client.post("/api/checkin", json={"customer_name": "C", "space_type_id": 2})
    assert full.status_code == 409 and full.get_json()["full"]

    with app.app_context():
        rows = CustomerSession.query.order_by(CustomerSession.id).all()
        assert len(rows) == 2
        assert [row.number_of_people for row in rows] == [1, 1]
    availability = {row["space_name"]: row for row in client.get("/api/space-availability").get_json()}
    assert availability["Regular Lounge"]["occupied"] == 1
    assert availability["Premium Lounge"]["occupied"] == 1

    boardroom = client.post("/api/checkin", json={
        "customer_name": "Booking party", "space_type_id": 3, "number_of_people": "3",
    })
    assert boardroom.status_code == 200
    with app.app_context():
        assert db.session.get(CustomerSession, boardroom.get_json()["session_id"]).number_of_people == 3


def test_older_group_session_keeps_its_original_occupancy(app, client):
    with app.app_context():
        db.session.add(CustomerSession(
            customer_name="Old group", space_type_id=1, number_of_people=3,
            time_in=datetime.utcnow(), status="active",
        ))
        db.session.commit()
    assert client.post("/api/checkin", json={"customer_name": "One more", "space_type_id": 1}).status_code == 200
    full = client.post("/api/checkin", json={"customer_name": "Too many", "space_type_id": 1})
    assert full.status_code == 409 and full.get_json()["full"]
    regular = next(row for row in client.get("/api/space-availability").get_json()
                   if row["space_name"] == "Regular Lounge")
    assert regular["occupied"] == 4 and regular["seats_left"] == 0
    with app.app_context():
        assert [row.number_of_people for row in CustomerSession.query.order_by(CustomerSession.id)] == [3, 1]
