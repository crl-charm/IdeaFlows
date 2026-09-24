from datetime import date, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace

import pytest
from flask import render_template
from openpyxl import load_workbook

from app import create_app, db
from app.models import CustomerSession, SpaceType, Transaction, MenuItem, Order, OrderItem
from app.utils.billing import calculate_time_bill
from app.utils.payment import normalize_payment_method, payment_method_label
from app.repositories.sales_repository import SalesRepository
from app.repositories.session_repository import SessionRepository
from app.services.session_service import SessionService
from app.services.daily_balance_export_service import DailyBalanceExportService


@pytest.fixture
def app():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return app


@pytest.mark.parametrize('minutes,regular,premium,boardroom', [
    (0,10,20,250), (15,10,20,250), (46,10,20,250),
    (60,10,20,250), (60+1/60,15,30,500), (75,15,30,500),
    (90,15,30,500), (90+1/60,20,40,500), (106,20,40,500),
    (120,20,40,500), (120+1/60,25,50,750),
])
def test_billing_boundaries(minutes, regular, premium, boardroom):
    for name, expected in [('Regular Lounge',regular), ('Premium Lounge',premium), ('Boardroom',boardroom)]:
        assert calculate_time_bill(SimpleNamespace(name=name), minutes) == Decimal(expected)


def test_queenbank_checkout_reporting_and_saved_receipt(app):
    with app.app_context():
        now = datetime.utcnow()
        space = SpaceType(name='Premium Lounge', rate_per_minute=Decimal('0.3333'))
        db.session.add(space)
        db.session.flush()
        session = CustomerSession(customer_name='Bank Customer', space_type_id=space.id,
                                  number_of_people=3, time_in=now-timedelta(minutes=75), status='active')
        db.session.add(session)
        db.session.commit()
        service = SessionService(SessionRepository(), SimpleNamespace(now=lambda: now),
                                 SimpleNamespace(session_checked_out=lambda payload: None))
        assert service.preview_checkout(session.id)['time_bill'] == 30
        result = service.checkout(session.id, 'queenbank')
        assert result['total_bill'] == 30
        assert result['payment_label'] == 'QueenBank'
        assert result['amount_tendered'] is None
        report_date = Transaction.query.filter_by(session_id=session.id).one().created_at.date()
        totals = SalesRepository().payment_totals_by_dates([report_date])[report_date]
        assert totals['queenbank_total'] == 30
        assert totals['queenbank_count'] == 1
        assert totals['cash_total'] == 0
        assert totals['cash_count'] == 0
        assert DailyBalanceExportService._payment_totals([totals])['total_queenbank'] == 30
        space.rate_per_minute = 99
        db.session.commit()
        client = app.test_client()
        with client.session_transaction() as auth:
            auth['user_id'] = 1
            auth['role'] = 'staff'
        receipt = client.get(f'/receipt/{session.id}')
        assert receipt.status_code == 200
        assert b'QueenBank' in receipt.data
        assert b'30.00' in receipt.data


def test_queenbank_normalization():
    assert normalize_payment_method(' QueenBank ') == 'queenbank'
    assert payment_method_label('queenbank') == 'QueenBank'


def test_pwd_discount_applies_to_one_unit_of_selected_food_item(app):
    with app.app_context():
        now = datetime.utcnow()
        space = SpaceType(name='Premium Lounge', rate_per_minute=Decimal('0.3333'))
        menu = MenuItem(name='Meal', price=Decimal('120.00'), category='Main Dish')
        db.session.add_all([space, menu])
        db.session.flush()
        customer = CustomerSession(customer_name='PWD Customer', space_type_id=space.id,
                                   number_of_people=2, time_in=now-timedelta(minutes=75), status='active')
        db.session.add(customer)
        db.session.flush()
        order = Order(customer_session_id=customer.id)
        db.session.add(order)
        db.session.flush()
        item = OrderItem(order_id=order.id, menu_item_id=menu.id, quantity=2, price=Decimal('120.00'))
        db.session.add(item)
        db.session.commit()
        service = SessionService(SessionRepository(), SimpleNamespace(now=lambda: now),
                                 SimpleNamespace(session_checked_out=lambda _: None))
        assert service.preview_checkout(customer.id, 'pwd', item.id)['discount_amount'] == 24
        assert service.preview_checkout(customer.id, 'pwd', 999)[1] == 400
        assert service.preview_checkout(customer.id, 'pwd', '1.5')[1] == 400
        result = service.checkout(customer.id, 'cash', '300', 'pwd', item.id)
        assert result['food_bill'] == 240
        assert result['discount_amount'] == 24
        assert result['total_bill'] == 246
        tx = Transaction.query.filter_by(session_id=customer.id).one()
        assert tx.discount_type == 'pwd'
        assert tx.discount_item_id == item.id
        assert tx.discount_amount == Decimal('24.00')


def test_queenbank_daily_balance_exports(app):
    report = {
        'report_date': date(2026, 9, 10),
        'total_revenue': 30.0,
        'cash_total': 0.0,
        'gcash_total': 0.0,
        'bdo_total': 0.0,
        'bpi_total': 0.0,
        'queenbank_total': 30.0,
        'cash_count': 0,
        'gcash_count': 0,
        'bdo_count': 0,
        'bpi_count': 0,
        'queenbank_count': 1,
        'total_expenses': 0.0,
        'net_balance': 30.0,
        'total_orders': 0,
        'total_sessions': 1,
        'generated_by': 'Test User',
        'notes': '',
    }
    service = DailyBalanceExportService(db)

    with app.test_request_context():
        csv_response = service.export_csv([report])
        csv_response.direct_passthrough = False
        csv_text = csv_response.get_data(as_text=True)
        assert 'QueenBank' in csv_text
        assert '₱30.00' in csv_text

        excel_response = service.export_excel([report])
        excel_response.direct_passthrough = False
        workbook = load_workbook(BytesIO(excel_response.get_data()))
        assert workbook['Summary']['A15'].value == 'QueenBank Payments:'
        assert workbook['Summary']['B15'].value == 30
        assert workbook['Daily Reports']['G1'].value == 'QueenBank'
        assert workbook['Daily Reports']['G2'].value == 30

        pdf_context = service.build_pdf_context([report], [])
        pdf_html = render_template(service.PDF_TEMPLATE, **pdf_context)
        assert 'QueenBank Payments' in pdf_html
        assert 'Php 30.00' in pdf_html
        pdf_response = service.export_pdf([report], [])
        assert pdf_response.get_data().startswith(b'%PDF')
