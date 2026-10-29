"""Customer statements reconcile receivable history without posting sales or cash."""
from datetime import date, datetime, timezone
from decimal import Decimal
from io import BytesIO
import re

import pytest
from sqlalchemy import event, inspect, text

from app import create_app, db
from app.db.migrator import SchemaMigrator
from app.models import (
    Admin, User, MenuItem, Order, OrderItem, InventoryLog, Transaction,
    Receivable, ReceivableAccount, ReceivableAccountEvent, ReceivableItem, ReceivablePayment, ReceivableTab,
)
from app.repositories.receivable_repository import ReceivableRepository
from app.services.customer_statement_service import CustomerStatementService
from app.services.export_service import ExportService
from app.services.receivable_service import ReceivableService


@pytest.fixture
def app():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return app


def auth(client, role="admin", user_id=1):
    with client.session_transaction() as session:
        session.update(user_id=user_id, username="test_user", role=role,
                       last_activity=datetime.now(timezone.utc).timestamp())


def debt(name="Demo Building", contact="0911", amount="180.00", **kwargs):
    return ReceivableService(ReceivableRepository()).create(
        name, contact, "Original food description", amount, "2026-10-31", 1, None,
        incurred_date="2026-10-01", **kwargs)["data"]


def test_grouped_payments_reconcile_and_never_include_another_account(app):
    with app.app_context():
        one, two = debt(), debt()
        other = debt("Different Customer", "0922", "999")
        ReceivableRepository().record_tab_payment(one["tab_id"], Decimal("200"), 1, "gcash",
                                                 received_at=datetime(2026, 10, 1, 16, 10))
        db.session.commit()
        before = (Receivable.query.count(), ReceivablePayment.query.count(), Transaction.query.count())
        s = CustomerStatementService.build(one["account_id"])
        assert (s["total_charged"], s["total_paid"], s["remaining"]) == (Decimal("360"), Decimal("200"), Decimal("160"))
        assert len(s["payments"]) == 1 and len(s["payments"][0]["allocations"]) == 2
        assert s["payments"][0]["when"] == "2026-10-02 12:10 AM"
        assert s["ledger"][-1]["balance"] == 160 and s["can_export"]
        assert {r["id"] for r in s["charges"]} == {one["id"], two["id"]}
        assert "Different Customer" not in str(s) and "999" not in str(s)
        assert before == (Receivable.query.count(), ReceivablePayment.query.count(), Transaction.query.count())


def test_closed_cycles_reopen_under_selected_permanent_account(app):
    with app.app_context():
        one = debt()
        repo = ReceivableRepository()
        repo.record_payment(one["id"], None, 1, "cash")
        repo.save()
        assert db.session.get(ReceivableTab, one["tab_id"]).closed_at
        two = debt(account_id=one["account_id"])
        assert two["account_id"] == one["account_id"] and two["tab_id"] != one["tab_id"]
        s = CustomerStatementService.build(one["account_id"])
        assert len(s["charges"]) == 2 and s["remaining"] == 180
        matches = ReceivableService(repo).suggest_customers("Demo")
        assert matches[0]["account_id"] == one["account_id"]


def test_migration_keeps_same_names_separate_until_explicit_review(app):
    with app.app_context():
        n, c, _ = ReceivableTab.identity("Sam", "")
        for closed in (False, True):
            tab = ReceivableTab(customer_name="Sam", normalized_name=n, normalized_contact=c,
                                closed_at=datetime(2026, 9, 30) if closed else None)
            db.session.add(tab)
        db.session.commit()
        migrator = SchemaMigrator(db, app)
        migrator._backfill_receivable_accounts()
        migrator._backfill_receivable_accounts()
        tabs = ReceivableTab.query.order_by(ReceivableTab.id).all()
        assert tabs[0].account_id != tabs[1].account_id
        assert ReceivableAccount.query.count() == ReceivableAccountEvent.query.count() == 2
        assert all(a.history_reviewed_at is None for a in ReceivableAccount.query.all())
        ids = [t.account_id for t in tabs]
        assert CustomerStatementService.candidates(db.session.get(ReceivableAccount, ids[0])).total == 1


def test_full_migration_is_idempotent_and_preserves_uncontacted_legacy_customers(app):
    with app.app_context():
        for description in ("Person A lunch", "Person B coffee"):
            db.session.add(Receivable(customer_name="Sam", items_description=description,
                amount_owed=50, partial_paid=0, paid=False, due_date=date(2026, 10, 31), created_by=1,
                created_at=datetime(2026, 10, 1, 18)))
        db.session.commit()
        migrator = SchemaMigrator(db, app)
        migrator.run()
        migrator.run()
        assert ReceivableAccount.query.count() == ReceivableTab.query.count() == 2
        rows = Receivable.query.all()
        assert rows[0].tab_id != rows[1].tab_id and sum(r.amount_owed for r in rows) == 100
        assert all(r.incurred_date == date(2026, 10, 2) for r in rows)
        assert all(a.history_reviewed_at is None for a in ReceivableAccount.query.all())


def test_upgrade_adds_columns_to_existing_sqlite_schema(app):
    with app.app_context():
        db.session.execute(text("ALTER TABLE receivables DROP COLUMN ordered_by"))
        db.session.execute(text("DROP TABLE receivable_tabs"))
        db.session.execute(text("""CREATE TABLE receivable_tabs (
            id INTEGER PRIMARY KEY, customer_name VARCHAR(100) NOT NULL, customer_contact VARCHAR(100),
            normalized_name VARCHAR(100) NOT NULL, normalized_contact VARCHAR(100) NOT NULL DEFAULT '',
            active_key VARCHAR(64) UNIQUE, opened_at DATETIME NOT NULL, closed_at DATETIME)"""))
        db.session.execute(text("""INSERT INTO receivable_tabs (id, customer_name, normalized_name, opened_at)
                                   VALUES (1, 'Legacy customer', 'legacy customer', '2026-10-01 01:00:00')"""))
        db.session.commit()
        migrator = SchemaMigrator(db, app)
        migrator.run()
        migrator.run()
        assert 'ordered_by' in {c['name'] for c in inspect(db.engine).get_columns('receivables')}
        assert 'account_id' in {c['name'] for c in inspect(db.engine).get_columns('receivable_tabs')}
        assert ReceivableAccount.query.count() == 1
        assert db.session.get(ReceivableTab, 1).account_id is not None


def test_individual_debt_can_be_separated_from_an_ambiguous_old_cycle(app):
    with app.app_context():
        one, two = debt(), debt()
        target = debt("Separate customer", "0922", "20")
        CustomerStatementService.review(target["account_id"], 1, receivable_id=two["id"])
        moved = db.session.get(Receivable, two["id"])
        assert moved.tab_id != one["tab_id"] and moved.amount_owed == 180
        log = ReceivableAccountEvent.query.filter_by(action="associate_debt").one()
        assert (log.receivable_id, log.previous_tab_id, log.previous_account_id) == (two["id"], one["tab_id"], one["account_id"])
        assert CustomerStatementService.build(one["account_id"])["remaining"] == 180
        assert CustomerStatementService.build(target["account_id"])["remaining"] == 200


def test_association_is_audited_and_confirmation_required_before_pdf(app):
    with app.app_context():
        first, second = debt("Sam", "", "20"), debt("Sam", "", "30")
        ids = first["account_id"], second["account_id"], second["tab_id"]
        original = [(r.id, r.amount_owed, r.partial_paid, r.incurred_date) for r in Receivable.query.all()]
    client = app.test_client()
    auth(client)
    path = f"/admin/reports/api/accounts/{ids[0]}/review"
    assert client.post(path, json={"action": "associate", "tab_id": ids[2]}).status_code == 200
    assert client.get(f"/admin/reports/api/customer-statements/{ids[0]}/pdf").status_code == 409
    assert client.post(path, json={"action": "confirm"}).status_code == 400
    assert client.post(path, json={"action": "confirm", "confirmed": True}).status_code == 200
    with app.app_context():
        s = CustomerStatementService.build(ids[0])
        assert s["remaining"] == 50 and s["can_export"]
        log = ReceivableAccountEvent.query.filter_by(action="associate_cycle").one()
        assert (log.previous_account_id, log.account_id, log.actor_id) == (ids[1], ids[0], 1)
        assert [(r.id, r.amount_owed, r.partial_paid, r.incurred_date) for r in Receivable.query.all()] == original


def test_history_confirmation_retry_does_not_duplicate_audit_events(app):
    with app.app_context():
        first = debt()
    client = app.test_client()
    auth(client)
    path = f"/admin/reports/api/accounts/{first['account_id']}/review"
    headers = {"Idempotency-Key": "confirm-history-once"}
    payload = {"action": "confirm", "confirmed": True}
    assert client.post(path, json=payload, headers=headers).status_code == 200
    assert client.post(path, json=payload, headers=headers).status_code == 409
    with app.app_context():
        assert ReceivableAccountEvent.query.filter_by(action="confirm_history").count() == 1


def test_unassigned_legacy_debt_can_be_mapped_without_rewriting_money_or_dates(app):
    with app.app_context():
        first = debt()
        row = Receivable(customer_name="Demo Building", items_description="Old drinks", amount_owed=75,
                         partial_paid=0, paid=False, due_date=date(2026, 9, 1), created_by=1,
                         created_at=datetime(2026, 8, 1, 18), incurred_date=date(2026, 8, 2))
        db.session.add(row)
        db.session.commit()
        row_id = row.id
        CustomerStatementService.review(first["account_id"], 1, receivable_id=row_id)
        s = CustomerStatementService.build(first["account_id"])
        assert len(s["charges"]) == 2 and not s["can_export"]
        row = db.session.get(Receivable, row_id)
        assert (row.amount_owed, row.incurred_date, row.created_at) == (75, date(2026, 8, 2), datetime(2026, 8, 1, 18))


def test_legacy_known_credits_are_undated_and_conflicting_payments_block_export(app):
    with app.app_context():
        first = debt(amount="100")
        row = db.session.get(Receivable, first["id"])
        row.partial_paid = 40
        db.session.commit()
        s = CustomerStatementService.build(first["account_id"])
        assert s["total_paid"] == 40 and s["remaining"] == 60
        assert s["historical_credits"][0]["amount"] == 40 and not s["payments"]
        assert s["ledger"][-1]["when"] == "Date unavailable" and s["can_export"]
        db.session.add(ReceivablePayment(receivable_id=row.id, amount=50, received_by=1, payment_method="cash"))
        db.session.commit()
        s = CustomerStatementService.build(first["account_id"])
        assert s["issues"] and not s["can_export"]


def test_old_paid_flag_without_receipts_stays_settled_without_inventing_receipt(app):
    with app.app_context():
        first = debt(amount="100")
        db.session.get(Receivable, first["id"]).paid = True
        db.session.commit()
        s = CustomerStatementService.build(first["account_id"])
        assert s["remaining"] == 0 and s["historical_credits"][0]["amount"] == 100
        assert s["payments"] == [] and s["can_export"]


def test_group_without_id_is_not_merged_and_cross_account_group_is_blocked(app):
    with app.app_context():
        first, other = debt(), debt("Other", "0922")
        row = db.session.get(Receivable, first["id"])
        row.partial_paid = 20
        for _ in range(2):
            db.session.add(ReceivablePayment(receivable_id=row.id, amount=10, received_at=datetime(2026, 10, 2),
                                             received_by=1, payment_method="cash"))
        db.session.commit()
        assert len(CustomerStatementService.build(first["account_id"])["payments"]) == 2
        p = ReceivablePayment.query.first()
        p.payment_group_id = "malformed-group"
        db.session.add(ReceivablePayment(receivable_id=other["id"], amount=5, received_by=1,
                                         payment_method="cash", payment_group_id="malformed-group"))
        db.session.commit()
        s = CustomerStatementService.build(first["account_id"])
        assert any("different account" in text for text in s["issues"]) and not s["can_export"]
        assert "Other" not in str(s)


def test_itemized_debt_snapshots_prices_actor_and_modifiers_without_stock_or_order_writes(app):
    with app.app_context():
        # Deliberately different Admin and User PKs: the recording actor is the canonical User.
        owner = User(id=7, username="canonical_owner", full_name="Owner", role="admin")
        owner.set_password("IsolatedOwner123!")
        legacy = Admin(id=19, username="canonical_owner", full_name="Owner")
        legacy.set_password("IsolatedOwner123!")
        menu = MenuItem(id=3, name="Bangus silog", price=180, status="active", can_remove_rice=True, can_remove_egg=True)
        db.session.add_all([owner, legacy, menu])
        db.session.commit()
    client = app.test_client()
    auth(client, user_id=7)
    payload = {"customer_name": "Demo Building", "customer_contact": "", "items": [
        {"menu_item_id": 3, "quantity": 2, "no_rice": True, "expected_base_price": "180.00"}],
        "amount_owed": "1", "due_date": "2026-10-31", "incurred_date": "2026-10-29", "ordered_by": "Building manager"}
    response = client.post("/admin/receivables/api/receivables", json=payload, headers={"Idempotency-Key": "itemized-owner-debt"})
    assert response.status_code == 201
    assert client.post("/admin/receivables/api/receivables", json=payload, headers={"Idempotency-Key": "itemized-owner-debt"}).status_code == 409
    saved = response.get_json()["data"]
    with app.app_context():
        row = db.session.get(Receivable, saved["id"])
        assert (row.created_by, row.approved_by_staff, row.amount_owed) == (7, "canonical_owner", Decimal("324"))
        item = ReceivableItem.query.one()
        assert item.quantity == 2 and item.unit_price == 162 and item.name_snapshot == "Bangus silog"
        db.session.get(MenuItem, 3).name, db.session.get(MenuItem, 3).price = "Changed name", 999
        db.session.commit()
        db.session.delete(db.session.get(MenuItem, 3))
        db.session.commit()
        s = CustomerStatementService.build(saved["account_id"])
        assert s["charges"][0]["ordered_by"] == "Building manager"
        assert s["charges"][0]["lines"][0]["name"] == "Bangus silog" and s["remaining"] == 324
        assert all(model.query.count() == 0 for model in (Order, OrderItem, InventoryLog, Transaction, ReceivablePayment))


@pytest.mark.parametrize("items", [[], [{"menu_item_id": 999, "quantity": 1}], [{"menu_item_id": 3, "quantity": 0}],
    [{"menu_item_id": 3, "quantity": True}], [{"menu_item_id": 3, "quantity": 1, "no_rice": "true"}],
    [{"menu_item_id": 3, "quantity": 1, "expected_base_price": "50"}], [{"menu_item_id": 3, "quantity": 1, "unit_price": "1"}]])
def test_invalid_menu_debt_is_atomic(app, items):
    with app.app_context():
        db.session.add(MenuItem(id=3, name="Coffee", price=100, status="active"))
        db.session.commit()
    client = app.test_client()
    auth(client, "staff")
    response = client.post("/receivables-view/api/receivables", json={
        "customer_name": "Test", "items": items, "due_date": "2026-10-31"})
    assert response.status_code == 400
    with app.app_context():
        assert Receivable.query.count() == ReceivableAccount.query.count() == ReceivableItem.query.count() == 0


def test_admin_only_preview_pdf_mapping_and_session_expiry(app):
    with app.app_context():
        first = debt()
    client = app.test_client()
    preview = f"/admin/reports/api/customer-statements/{first['account_id']}"
    review = f"/admin/reports/api/accounts/{first['account_id']}/review"
    assert client.get(preview).status_code == client.get(preview + "/pdf").status_code == 401
    auth(client, "staff")
    for path in ("/admin/reports", preview, preview + "/pdf"):
        assert client.get(path, headers={"Accept": "application/json"}).status_code == 403
    assert client.post(review, json={"action": "confirm", "confirmed": True}).status_code == 403
    auth(client)
    assert client.get(preview).status_code == 200
    page = client.get("/admin/reports", query_string={"tab_id": first["tab_id"]})
    assert page.status_code == 200 and b"Export Customer Statement PDF" in page.data
    statement_html = re.search(rb'<main class="container-fluid statement-page">(.*?)</main>', page.data, re.DOTALL)
    assert statement_html is not None and b"salary" not in statement_html.group(1).lower()
    assert "salary" not in str(client.get(preview).get_json()).lower()
    assert client.get(preview + "?attention=" + "a" * 101).status_code == 400
    assert client.get("/admin/reports?account_id=abc").status_code == 400
    assert client.get("/admin/reports/api/customer-statements/9999").status_code == 404
    with client.session_transaction() as session:
        session["last_activity"] = 1
    assert client.get(preview).status_code == 401


def test_large_statement_has_bounded_reads_and_no_screen_pagination_limit(app):
    with app.app_context():
        first = debt(amount="1")
        for i in range(75):
            db.session.add(Receivable(customer_name="Demo Building", tab_id=first["tab_id"], created_by=1,
                                     items_description=f"History {i}", amount_owed=1, partial_paid=0,
                                     paid=False, incurred_date=date(2026, 10, 2), due_date=date(2026, 10, 31)))
        db.session.commit()
        db.session.remove()
        queries = []
        def count(conn, cursor, statement, *args):
            if statement.lstrip().upper().startswith("SELECT"):
                queries.append(statement)
        event.listen(db.engine, "before_cursor_execute", count)
        try:
            s = CustomerStatementService.build(first["account_id"])
        finally:
            event.remove(db.engine, "before_cursor_execute", count)
        assert len(s["charges"]) == 76 and s["remaining"] == 76
        assert len(queries) <= 8


def test_pdf_endpoint_uses_customer_only_builder_and_clear_render_failure(app, monkeypatch):
    with app.app_context():
        first = debt()
        debt("PRIVATE OTHER CUSTOMER", "0922", "99999")
    captured = {}
    def render(self, template, **context):
        captured.update(context)
        assert template == "admin/customer_statement_pdf.html"
        return b"%PDF-1.4\nfixture"
    monkeypatch.setattr(ExportService, "render_pdf_bytes", render)
    client = app.test_client()
    auth(client)
    path = f"/admin/reports/api/customer-statements/{first['account_id']}/pdf"
    response = client.get(path)
    assert response.status_code == 200 and response.mimetype == "application/pdf"
    assert response.headers["Cache-Control"] == "private, no-store"
    assert "RA-000001" in response.headers["Content-Disposition"]
    assert set(captured) == {"statement", "logo"} and "PRIVATE OTHER CUSTOMER" not in str(captured)
    def fail(*args, **kwargs):
        raise RuntimeError("renderer unavailable")
    monkeypatch.setattr(ExportService, "render_pdf_bytes", fail)
    assert client.get(path).status_code == 503


def test_real_pdf_contains_full_customer_history_and_no_other_account(app):
    from pypdf import PdfReader
    with app.app_context():
        first = debt()
        for i in range(30):
            debt(account_id=first["account_id"])
        debt("PRIVATE OTHER CUSTOMER", "0922", "99999")
    client = app.test_client()
    auth(client)
    response = client.get(f"/admin/reports/api/customer-statements/{first['account_id']}/pdf")
    assert response.status_code == 200
    reader = PdfReader(BytesIO(response.data))
    content = "\n".join(page.extract_text() for page in reader.pages)
    assert len(reader.pages) >= 3 and "R-31" in content and "5580.00" in content
    assert "PRIVATE OTHER CUSTOMER" not in content and "salary" not in content.lower()
