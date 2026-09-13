import pytest
from decimal import Decimal
from datetime import datetime, UTC
from app import create_app, db
from app.models import CustomerSession, Transaction, SpaceType
from app.utils.payment import parse_money_amount, compute_change


from app.db.migrator import SchemaMigrator


@pytest.fixture
def app():
    application = create_app()
    application.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
    )
    # Ensure database is clean or set up for test
    with application.app_context():
        db.create_all()
        SchemaMigrator(db, application).run()
        # Ensure default SpaceTypes exist
        if not SpaceType.query.get(1):
            space1 = SpaceType(id=1, name="Regular Lounge", capacity=10, rate_per_minute=Decimal("1.50"))
            db.session.add(space1)
        if not SpaceType.query.get(2):
            space2 = SpaceType(id=2, name="Premium Lounge", capacity=5, rate_per_minute=Decimal("2.50"))
            db.session.add(space2)
        db.session.commit()
    return application


@pytest.fixture
def client(app):
    return app.test_client()


def _set_auth_session(client, role: str = "staff", user_id: int = 1):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["username"] = f"test_{role}"
        sess["role"] = role
        sess["last_activity"] = datetime.now(UTC).timestamp()


class TestPaymentUtilities:
    def test_parse_money_amount_valid(self):
        assert parse_money_amount("150.00") == Decimal("150.00")
        assert parse_money_amount("200") == Decimal("200.00")
        assert parse_money_amount(150.5) == Decimal("150.50")
        assert parse_money_amount(Decimal("10")) == Decimal("10.00")

    def test_parse_money_amount_invalid(self):
        with pytest.raises(ValueError, match="Invalid amount tendered"):
            parse_money_amount("abc")
        with pytest.raises(ValueError, match="Invalid amount tendered"):
            parse_money_amount("")
        with pytest.raises(ValueError, match="Invalid amount tendered"):
            parse_money_amount("-10")
        with pytest.raises(ValueError, match="Invalid amount tendered"):
            parse_money_amount(None)

    def test_compute_change_valid(self):
        assert compute_change("150.00", "200.00") == 50.00
        assert compute_change(150.00, 150.00) == 0.00
        assert compute_change(Decimal("150.00"), Decimal("200.00")) == 50.00

    def test_compute_change_under(self):
        assert compute_change("150.00", "100.00") == 0.00

    def test_compute_change_invalid(self):
        assert compute_change(None, "200.00") is None
        assert compute_change("150.00", "abc") is None


class TestCheckoutChangeTracking:
    def test_cash_checkout_success(self, app, client):
        _set_auth_session(client)
        
        with app.app_context():
            # Create active session
            sess = CustomerSession(
                customer_name="John Cash",
                space_type_id=1,
                number_of_people=1,
                time_in=datetime.now(UTC),
                status="active"
            )
            db.session.add(sess)
            db.session.commit()
            session_id = sess.id

        # Trigger checkout with sufficient cash
        response = client.post(
            f"/api/checkout/{session_id}",
            json={
                "payment_method": "cash",
                "amount_tendered": "200.00"
            }
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["amount_tendered"] == 200.0
        assert data["change_given"] >= 0.0

        with app.app_context():
            tx = Transaction.query.filter_by(session_id=session_id).first()
            assert tx is not None
            assert tx.payment_method == "cash"
            assert float(tx.amount_tendered) == 200.0
            
            sess_after = CustomerSession.query.get(session_id)
            assert sess_after.status == "completed"
            assert float(sess_after.amount_tendered) == 200.0

    def test_cash_checkout_missing_tendered(self, app, client):
        _set_auth_session(client)
        
        with app.app_context():
            sess = CustomerSession(
                customer_name="John Missing",
                space_type_id=1,
                number_of_people=1,
                time_in=datetime.now(UTC),
                status="active"
            )
            db.session.add(sess)
            db.session.commit()
            session_id = sess.id

        response = client.post(
            f"/api/checkout/{session_id}",
            json={
                "payment_method": "cash"
            }
        )
        assert response.status_code == 400
        data = response.get_json()
        assert "Amount tendered is required" in data["error"]

    def test_cash_checkout_insufficient_tendered(self, app, client):
        _set_auth_session(client)
        
        with app.app_context():
            # Setup session in the past so total_bill is guaranteed > 0
            # Space rate is 1.50 per minute, 100 minutes = 150.00 bill
            past_time = datetime.now(UTC) - __import__("datetime").timedelta(minutes=100)
            sess = CustomerSession(
                customer_name="John Poor",
                space_type_id=1,
                number_of_people=1,
                time_in=past_time,
                status="active"
            )
            db.session.add(sess)
            db.session.commit()
            session_id = sess.id

        response = client.post(
            f"/api/checkout/{session_id}",
            json={
                "payment_method": "cash",
                "amount_tendered": "5.00"  # Clearly less than the bill
            }
        )
        assert response.status_code == 400
        data = response.get_json()
        assert "must be at least the total bill" in data["error"]

    def test_gcash_checkout_ignores_tendered(self, app, client):
        _set_auth_session(client)
        
        with app.app_context():
            sess = CustomerSession(
                customer_name="John GCash",
                space_type_id=1,
                number_of_people=1,
                time_in=datetime.now(UTC),
                status="active"
            )
            db.session.add(sess)
            db.session.commit()
            session_id = sess.id

        response = client.post(
            f"/api/checkout/{session_id}",
            json={
                "payment_method": "gcash",
                "amount_tendered": "500.00"
            }
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["amount_tendered"] is None
        assert data["change_given"] is None

        with app.app_context():
            tx = Transaction.query.filter_by(session_id=session_id).first()
            assert tx.amount_tendered is None
            
            sess_after = CustomerSession.query.get(session_id)
            assert sess_after.amount_tendered is None

    def test_reprint_receipt_shows_cash_details(self, app, client):
        _set_auth_session(client)
        
        with app.app_context():
            now = datetime.now(UTC)
            sess = CustomerSession(
                customer_name="Receipt Cust",
                space_type_id=1,
                number_of_people=1,
                time_in=now - __import__("datetime").timedelta(minutes=10),
                time_out=now,
                status="completed",
                payment_method="cash",
                amount_tendered=Decimal("100.00")
            )
            db.session.add(sess)
            db.session.commit()
            session_id = sess.id
            
            tx = Transaction(
                session_id=session_id,
                time_bill=Decimal("15.00"),
                food_bill=Decimal("0.00"),
                total_bill=Decimal("15.00"),
                payment_method="cash",
                amount_tendered=Decimal("100.00")
            )
            db.session.add(tx)
            db.session.commit()

        with app.app_context():
            sess_db = CustomerSession.query.get(session_id)
            space_rate = sess_db.space_type.rate_per_minute if sess_db.space_type else Decimal("0")
            expected_change = 100.00 - float(10 * space_rate)

        response = client.get(f"/receipt/{session_id}")
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        try:
            assert "Amount Tendered:" in html
            assert "Change:" in html
            assert "\u20b1100.00" in html
            assert f"{expected_change:.2f}" in html
        except AssertionError:
            print("--- HTML OUTPUT ---")
            print(html.encode('ascii', errors='replace').decode('ascii'))
            print("-------------------")
            raise
