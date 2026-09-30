from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import text, inspect, case, func
from app.models import Admin, Receivable, ReceivablePayment, ReceivableTab
from app.utils.dates import manila_date
from app.models.finance import FinanceBudget, FinanceTransaction
from app.models.soft_balance import SoftBalanceEntry
from app.models.space_price_history import SpacePriceHistory
from app.models.payable import Payable
from app.models.menu_category import MenuCategory
from app.models.checkout_void import CheckoutVoidRequest


class SchemaMigrator:
    """Runs ALTER TABLE statements in an idempotent way."""

    def __init__(self, db, app) -> None:
        self._db = db
        self._app = app

    def run(self) -> None:
        db = self._db
        _ = (FinanceBudget, FinanceTransaction, SoftBalanceEntry, SpacePriceHistory, Payable, MenuCategory, CheckoutVoidRequest)
        try:
            db.create_all()
            # Phase 3: Drop the obsolete reservations table if it exists
            db.session.execute(text("DROP TABLE IF EXISTS reservations"))
            db.session.commit()
            
            # Safe MySQL column modifications to support decimal stock
            if db.engine.dialect.name == "mysql":
                try:
                    db.session.execute(text("ALTER TABLE inventory_items MODIFY COLUMN stock_qty DECIMAL(10,2) NOT NULL DEFAULT 0.00"))
                    db.session.execute(text("ALTER TABLE inventory_logs MODIFY COLUMN change_qty DECIMAL(10,2) NOT NULL"))
                    db.session.commit()
                except Exception as e:
                    db.session.rollback()
                    print(f"[WARNING] Database column modification failed/skipped: {e}")
        except Exception as e:
            print(f"[WARNING] Database migration skipped (database unavailable): {e}")
            return

        try:
            inspector = inspect(db.engine)
        except Exception as e:
            print(f"[WARNING] Database migration inspector failed: {e}")
            return

        checks = [
            ("receivable_payments", "balance_before", "ALTER TABLE receivable_payments ADD COLUMN balance_before DECIMAL(10,2) NULL"),
            ("receivable_payments", "balance_after", "ALTER TABLE receivable_payments ADD COLUMN balance_after DECIMAL(10,2) NULL"),
            ("receivable_payments", "request_key", "ALTER TABLE receivable_payments ADD COLUMN request_key VARCHAR(200) NULL"),
            ("staff_attendance", "last_activity_at", "ALTER TABLE staff_attendance ADD COLUMN last_activity_at DATETIME NULL"),
            ("staff_attendance", "show_in_history", "ALTER TABLE staff_attendance ADD COLUMN show_in_history BOOLEAN NOT NULL DEFAULT TRUE"),
            ("menu_items", "inventory_mode", "ALTER TABLE menu_items ADD COLUMN inventory_mode VARCHAR(16) NULL"),
            ("menu_items", "can_remove_rice", "ALTER TABLE menu_items ADD COLUMN can_remove_rice BOOLEAN NOT NULL DEFAULT FALSE"),
            ("menu_items", "can_remove_egg", "ALTER TABLE menu_items ADD COLUMN can_remove_egg BOOLEAN NOT NULL DEFAULT FALSE"),
            ("order_items", "name_snapshot", "ALTER TABLE order_items ADD COLUMN name_snapshot VARCHAR(100) NULL"),
            ("order_items", "base_price", "ALTER TABLE order_items ADD COLUMN base_price DECIMAL(10,2) NULL"),
            ("order_items", "no_rice", "ALTER TABLE order_items ADD COLUMN no_rice BOOLEAN NOT NULL DEFAULT FALSE"),
            ("order_items", "no_egg", "ALTER TABLE order_items ADD COLUMN no_egg BOOLEAN NOT NULL DEFAULT FALSE"),
            ("order_items", "unit_deduction", "ALTER TABLE order_items ADD COLUMN unit_deduction DECIMAL(10,2) NOT NULL DEFAULT 0"),
            ("orders", "food_total_before", "ALTER TABLE orders ADD COLUMN food_total_before DECIMAL(10,2) NULL"),
            ("orders", "food_total_after", "ALTER TABLE orders ADD COLUMN food_total_after DECIMAL(10,2) NULL"),
            ("order_inventory_allocations", "menu_item_id", "ALTER TABLE order_inventory_allocations ADD COLUMN menu_item_id INTEGER NULL"),
            ("order_inventory_allocations", "ordered_units", "ALTER TABLE order_inventory_allocations ADD COLUMN ordered_units INTEGER NULL"),
            ("order_inventory_allocations", "updated_at", "ALTER TABLE order_inventory_allocations ADD COLUMN updated_at DATETIME NULL"),
            (
                "orders",
                "status",
                "ALTER TABLE orders ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'preparing'",
            ),
            (
                "order_items",
                "status",
                "ALTER TABLE order_items ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'preparing'",
            ),
            ("space_types", "capacity", "ALTER TABLE space_types ADD COLUMN capacity INT NULL"),
            (
                "users",
                "job_role",
                "ALTER TABLE users ADD COLUMN job_role VARCHAR(50) NOT NULL DEFAULT 'general'",
            ),
            (
                "users",
                "is_active",
                "ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE",
            ),
            ("orders", "handled_by", "ALTER TABLE orders ADD COLUMN handled_by INT NULL"),
            (
                "customer_sessions",
                "number_of_people",
                "ALTER TABLE customer_sessions ADD COLUMN number_of_people INT NOT NULL DEFAULT 1",
            ),
            (
                "customer_sessions",
                "service_mode",
                "ALTER TABLE customer_sessions ADD COLUMN service_mode VARCHAR(16) NOT NULL DEFAULT 'timed'",
            ),
            ("customer_sessions", "cancelled_at", "ALTER TABLE customer_sessions ADD COLUMN cancelled_at DATETIME NULL"),
            ("customer_sessions", "cancelled_by_id", "ALTER TABLE customer_sessions ADD COLUMN cancelled_by_id INT NULL"),
            ("customer_sessions", "cancelled_by_role", "ALTER TABLE customer_sessions ADD COLUMN cancelled_by_role VARCHAR(20) NULL"),
            ("customer_sessions", "cancelled_by_name", "ALTER TABLE customer_sessions ADD COLUMN cancelled_by_name VARCHAR(100) NULL"),
            ("customer_sessions", "cancel_reason", "ALTER TABLE customer_sessions ADD COLUMN cancel_reason VARCHAR(500) NULL"),
            ("customer_sessions", "cancelled_space_name", "ALTER TABLE customer_sessions ADD COLUMN cancelled_space_name VARCHAR(100) NULL"),
            ("customer_sessions", "cancelled_uncollected_amount", "ALTER TABLE customer_sessions ADD COLUMN cancelled_uncollected_amount DECIMAL(10,2) NULL"),
            ("boardroom_bookings", "session_id", "ALTER TABLE boardroom_bookings ADD COLUMN session_id INT NULL"),
            ("boardroom_bookings", "started_at", "ALTER TABLE boardroom_bookings ADD COLUMN started_at DATETIME NULL"),
            (
                "boardroom_bookings",
                "expected_end_at",
                "ALTER TABLE boardroom_bookings ADD COLUMN expected_end_at DATETIME NULL",
            ),
            ("boardroom_bookings", "ended_at", "ALTER TABLE boardroom_bookings ADD COLUMN ended_at DATETIME NULL"),
            (
                "boardroom_bookings",
                "extended_minutes",
                "ALTER TABLE boardroom_bookings ADD COLUMN extended_minutes INT NOT NULL DEFAULT 0",
            ),
            ("boardroom_bookings", "course", "ALTER TABLE boardroom_bookings ADD COLUMN course VARCHAR(100) NULL"),
            ("boardroom_bookings", "booking_type", "ALTER TABLE boardroom_bookings ADD COLUMN booking_type VARCHAR(20) NOT NULL DEFAULT 'boardroom'"),
            ("boardroom_bookings", "hourly_rate", "ALTER TABLE boardroom_bookings ADD COLUMN hourly_rate DECIMAL(10,2) NOT NULL DEFAULT 250.00"),
            ("boardroom_bookings", "booked_by", "ALTER TABLE boardroom_bookings ADD COLUMN booked_by VARCHAR(100) NULL"),
            (
                "customer_sessions",
                "payment_method",
                "ALTER TABLE customer_sessions ADD COLUMN payment_method VARCHAR(50) NOT NULL DEFAULT 'cash'",
            ),
            (
                "transactions",
                "payment_method",
                "ALTER TABLE transactions ADD COLUMN payment_method VARCHAR(50) NOT NULL DEFAULT 'cash'",
            ),
            ("transactions", "collected_by", "ALTER TABLE transactions ADD COLUMN collected_by VARCHAR(100) NULL"),
            (
                "customer_sessions",
                "amount_tendered",
                "ALTER TABLE customer_sessions ADD COLUMN amount_tendered DECIMAL(10,2) NULL",
            ),
            (
                "transactions",
                "amount_tendered",
                "ALTER TABLE transactions ADD COLUMN amount_tendered DECIMAL(10,2) NULL",
            ),
            ("transactions", "discount_type", "ALTER TABLE transactions ADD COLUMN discount_type VARCHAR(20) NULL"),
            ("transactions", "discount_item_id", "ALTER TABLE transactions ADD COLUMN discount_item_id INT NULL"),
            ("transactions", "discount_amount", "ALTER TABLE transactions ADD COLUMN discount_amount DECIMAL(10,2) NOT NULL DEFAULT 0.00"),
            (
                "menu_items",
                "is_available",
                "ALTER TABLE menu_items ADD COLUMN is_available BOOLEAN DEFAULT TRUE",
            ),
            (
                "menu_items",
                "created_at",
                "ALTER TABLE menu_items ADD COLUMN created_at DATETIME NULL",
            ),
            (
                "menu_items",
                "updated_at",
                "ALTER TABLE menu_items ADD COLUMN updated_at DATETIME NULL",
            ),
            (
                "staff_performance_logs",
                "customers_served",
                "ALTER TABLE staff_performance_logs ADD COLUMN customers_served INT NOT NULL DEFAULT 0",
            ),
            (
                "receivables",
                "approved_by_staff",
                "ALTER TABLE receivables ADD COLUMN approved_by_staff VARCHAR(100) NULL",
            ),
            (
                "receivables",
                "paid_at",
                "ALTER TABLE receivables ADD COLUMN paid_at DATETIME NULL",
            ),
            (
                "receivables",
                "incurred_date",
                "ALTER TABLE receivables ADD COLUMN incurred_date DATE NULL",
            ),
            ("receivables", "notes", "ALTER TABLE receivables ADD COLUMN notes TEXT NULL"),
            ("receivables", "tab_id", "ALTER TABLE receivables ADD COLUMN tab_id INTEGER NULL"),
            ("receivable_payments", "payment_group_id", "ALTER TABLE receivable_payments ADD COLUMN payment_group_id VARCHAR(32) NULL"),
            ("expenses", "payment_method", "ALTER TABLE expenses ADD COLUMN payment_method VARCHAR(50) NULL"),
            ("expenses", "voided_at", "ALTER TABLE expenses ADD COLUMN voided_at DATETIME NULL"),
            ("expenses", "voided_by", "ALTER TABLE expenses ADD COLUMN voided_by INTEGER NULL"),
            ("expenses", "void_reason", "ALTER TABLE expenses ADD COLUMN void_reason VARCHAR(255) NULL"),
            ("expenses", "request_key", "ALTER TABLE expenses ADD COLUMN request_key VARCHAR(200) NULL"),
            ("expenses", "funding_source", "ALTER TABLE expenses ADD COLUMN funding_source VARCHAR(20) NULL"),
            ("expenses", "balance_before", "ALTER TABLE expenses ADD COLUMN balance_before DECIMAL(12,2) NULL"),
            ("expenses", "balance_after", "ALTER TABLE expenses ADD COLUMN balance_after DECIMAL(12,2) NULL"),
            ("expenses", "void_balance_before", "ALTER TABLE expenses ADD COLUMN void_balance_before DECIMAL(12,2) NULL"),
            ("expenses", "void_balance_after", "ALTER TABLE expenses ADD COLUMN void_balance_after DECIMAL(12,2) NULL"),
            ("payable_payments", "funding_source", "ALTER TABLE payable_payments ADD COLUMN funding_source VARCHAR(20) NULL"),
            ("payable_payments", "method_balance_before", "ALTER TABLE payable_payments ADD COLUMN method_balance_before DECIMAL(12,2) NULL"),
            ("payable_payments", "method_balance_after", "ALTER TABLE payable_payments ADD COLUMN method_balance_after DECIMAL(12,2) NULL"),
            ("finance_transactions", "payment_method", "ALTER TABLE finance_transactions ADD COLUMN payment_method VARCHAR(50) NULL"),
            ("finance_transactions", "actor_id", "ALTER TABLE finance_transactions ADD COLUMN actor_id INTEGER NULL"),
            ("finance_transactions", "request_key", "ALTER TABLE finance_transactions ADD COLUMN request_key VARCHAR(200) NULL"),
            ("daily_sales_reports", "total_collections", "ALTER TABLE daily_sales_reports ADD COLUMN total_collections DECIMAL(12,2) NOT NULL DEFAULT 0"),
            ("daily_sales_reports", "total_payables_paid", "ALTER TABLE daily_sales_reports ADD COLUMN total_payables_paid DECIMAL(12,2) NOT NULL DEFAULT 0"),
            ("daily_sales_reports", "total_other_income", "ALTER TABLE daily_sales_reports ADD COLUMN total_other_income DECIMAL(12,2) NOT NULL DEFAULT 0"),
            ("daily_sales_reports", "total_budget_spend", "ALTER TABLE daily_sales_reports ADD COLUMN total_budget_spend DECIMAL(12,2) NOT NULL DEFAULT 0"),
            ("daily_sales_reports", "total_refunds", "ALTER TABLE daily_sales_reports ADD COLUMN total_refunds DECIMAL(12,2) NOT NULL DEFAULT 0"),
            ("soft_balance_entries", "total_collections", "ALTER TABLE soft_balance_entries ADD COLUMN total_collections DECIMAL(12,2) NOT NULL DEFAULT 0"),
            ("soft_balance_entries", "total_payables_paid", "ALTER TABLE soft_balance_entries ADD COLUMN total_payables_paid DECIMAL(12,2) NOT NULL DEFAULT 0"),
            ("soft_balance_entries", "total_other_income", "ALTER TABLE soft_balance_entries ADD COLUMN total_other_income DECIMAL(12,2) NOT NULL DEFAULT 0"),
            ("soft_balance_entries", "total_budget_spend", "ALTER TABLE soft_balance_entries ADD COLUMN total_budget_spend DECIMAL(12,2) NOT NULL DEFAULT 0"),
            ("soft_balance_entries", "total_refunds", "ALTER TABLE soft_balance_entries ADD COLUMN total_refunds DECIMAL(12,2) NOT NULL DEFAULT 0"),
            (
                "menu_item_ingredients",
                "unit",
                "ALTER TABLE menu_item_ingredients ADD COLUMN unit VARCHAR(50) NULL",
            ),
            (
                "menu_item_ingredients",
                "conversion_ratio",
                "ALTER TABLE menu_item_ingredients ADD COLUMN conversion_ratio DECIMAL(10,4) NOT NULL DEFAULT 1.0000",
            ),
            # Checkout records snapshots, void status, and retained credit
            ("transactions", "billing_start_at", "ALTER TABLE transactions ADD COLUMN billing_start_at DATETIME NULL"),
            ("transactions", "billing_end_at", "ALTER TABLE transactions ADD COLUMN billing_end_at DATETIME NULL"),
            ("transactions", "customer_name_snapshot", "ALTER TABLE transactions ADD COLUMN customer_name_snapshot VARCHAR(100) NULL"),
            ("transactions", "space_name_snapshot", "ALTER TABLE transactions ADD COLUMN space_name_snapshot VARCHAR(100) NULL"),
            ("transactions", "service_mode_snapshot", "ALTER TABLE transactions ADD COLUMN service_mode_snapshot VARCHAR(16) NULL"),
            ("transactions", "number_of_people_snapshot", "ALTER TABLE transactions ADD COLUMN number_of_people_snapshot INT NULL"),
            ("transactions", "change_given", "ALTER TABLE transactions ADD COLUMN change_given DECIMAL(10,2) NULL"),
            ("transactions", "is_voided", "ALTER TABLE transactions ADD COLUMN is_voided BOOLEAN NOT NULL DEFAULT FALSE"),
            ("transactions", "credit_applied", "ALTER TABLE transactions ADD COLUMN credit_applied DECIMAL(10,2) NOT NULL DEFAULT 0.00"),
            ("transactions", "credit_refunded", "ALTER TABLE transactions ADD COLUMN credit_refunded DECIMAL(10,2) NOT NULL DEFAULT 0.00"),
            ("customer_sessions", "credit_balance", "ALTER TABLE customer_sessions ADD COLUMN credit_balance DECIMAL(10,2) NOT NULL DEFAULT 0.00"),
            ("customer_sessions", "credit_payment_method", "ALTER TABLE customer_sessions ADD COLUMN credit_payment_method VARCHAR(50) NULL"),
            ("customer_sessions", "retained_time_bill", "ALTER TABLE customer_sessions ADD COLUMN retained_time_bill DECIMAL(10,2) NULL"),
            ("customer_sessions", "voided_transaction_id", "ALTER TABLE customer_sessions ADD COLUMN voided_transaction_id INT NULL"),
        ]

        # Cache existing columns to minimize database queries
        table_columns = {}

        for table_name, column_name, ddl in checks:
            try:
                if table_name not in table_columns:
                    if inspector.has_table(table_name):
                        table_columns[table_name] = {col['name'] for col in inspector.get_columns(table_name)}
                    else:
                        table_columns[table_name] = set()

                if column_name in table_columns[table_name]:
                    continue

                db.session.execute(text(ddl))
                db.session.commit()
                # Update cache
                table_columns[table_name].add(column_name)
            except Exception as e:
                db.session.rollback()
                print(f"[WARNING] Column {column_name} on {table_name} skipped/failed: {e}")

        self._ensure_indexes(db, inspector)
        self._backfill_receivable_tabs()
        if db.engine.dialect.name == "mysql" and not any(
            "tab_id" in fk.get("constrained_columns", [])
            for fk in inspect(db.engine).get_foreign_keys("receivables")
        ):
            db.session.execute(text(
                "ALTER TABLE receivables ADD CONSTRAINT fk_receivables_tab "
                "FOREIGN KEY (tab_id) REFERENCES receivable_tabs(id)"
            ))
            db.session.commit()

    def _backfill_receivable_tabs(self) -> None:
        """Attach legacy debts without changing amounts or payment history."""
        db = self._db
        rows = Receivable.query.filter(
            (Receivable.tab_id.is_(None)) | (Receivable.incurred_date.is_(None))
        ).order_by(Receivable.id).all()
        if not rows:
            return
        before = (
            db.session.query(db.func.sum(Receivable.amount_owed)).scalar() or Decimal("0"),
            db.session.query(db.func.sum(Receivable.partial_paid)).scalar() or Decimal("0"),
            db.session.query(db.func.sum(ReceivablePayment.amount)).scalar() or Decimal("0"),
            db.session.query(func.sum(case((Receivable.paid.is_(False),
                                            Receivable.amount_owed - Receivable.partial_paid), else_=0))).scalar() or Decimal("0"),
        )
        open_tabs = {}
        try:
            for row in rows:
                if row.incurred_date is None:
                    row.incurred_date = manila_date(row.created_at) if row.created_at else manila_date(datetime.utcnow())
                if row.tab_id is not None:
                    continue
                name, contact, key = ReceivableTab.identity(row.customer_name, row.customer_contact)
                if not row.paid and row.amount_owed > row.partial_paid:
                    identity = (name, contact)
                    tab = open_tabs.get(identity)
                    if tab is None:
                        tab = ReceivableTab.query.filter_by(active_key=key).first() if key else None
                        if tab is None:
                            tab = ReceivableTab(customer_name=row.customer_name, customer_contact=row.customer_contact,
                                                normalized_name=name, normalized_contact=contact, active_key=key,
                                                opened_at=row.created_at or datetime.utcnow())
                            db.session.add(tab)
                            db.session.flush()
                        open_tabs[identity] = tab
                else:
                    # Old settled cycles cannot be reconstructed reliably; retain each as history.
                    tab = ReceivableTab(customer_name=row.customer_name, customer_contact=row.customer_contact,
                                        normalized_name=name, normalized_contact=contact,
                                        opened_at=row.created_at or datetime.utcnow(),
                                        closed_at=row.paid_at or row.created_at or datetime.utcnow())
                    db.session.add(tab)
                    db.session.flush()
                row.tab_id = tab.id
            db.session.flush()
            after = (
                db.session.query(db.func.sum(Receivable.amount_owed)).scalar() or Decimal("0"),
                db.session.query(db.func.sum(Receivable.partial_paid)).scalar() or Decimal("0"),
                db.session.query(db.func.sum(ReceivablePayment.amount)).scalar() or Decimal("0"),
                db.session.query(func.sum(case((Receivable.paid.is_(False),
                                                Receivable.amount_owed - Receivable.partial_paid), else_=0))).scalar() or Decimal("0"),
            )
            if before != after:
                raise RuntimeError("Receivable money totals changed during tab backfill")
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

    def _ensure_indexes(self, db, inspector) -> None:
        """Create performance indexes idempotently (MySQL/SQLite)."""
        indexes = [
            (
                "finance_transactions",
                "uq_finance_transactions_request_key",
                "CREATE UNIQUE INDEX uq_finance_transactions_request_key ON finance_transactions (request_key)",
            ),
            (
                "receivable_payments",
                "ix_receivable_payments_request_key",
                "CREATE INDEX ix_receivable_payments_request_key ON receivable_payments (request_key)",
            ),
            (
                "expenses",
                "uq_expenses_request_key",
                "CREATE UNIQUE INDEX uq_expenses_request_key ON expenses (request_key)",
            ),
            (
                "transactions",
                "idx_transactions_created_at",
                "CREATE INDEX idx_transactions_created_at ON transactions (created_at)",
            ),
            (
                "transactions",
                "idx_transactions_payment_method",
                "CREATE INDEX idx_transactions_payment_method ON transactions (payment_method)",
            ),
            (
                "customer_sessions",
                "idx_customer_sessions_time_in",
                "CREATE INDEX idx_customer_sessions_time_in ON customer_sessions (time_in)",
            ),
            (
                "orders",
                "idx_orders_session_status",
                "CREATE INDEX idx_orders_session_status ON orders (customer_session_id, status, id)",
            ),
            (
                "order_items",
                "idx_order_items_order_id",
                "CREATE INDEX idx_order_items_order_id ON order_items (order_id)",
            ),
            (
                "boardroom_bookings",
                "idx_bookings_status_end",
                "CREATE INDEX idx_bookings_status_end ON boardroom_bookings (status, expected_end_at)",
            ),
            (
                "receivables",
                "idx_receivables_paid_due",
                "CREATE INDEX idx_receivables_paid_due ON receivables (paid, due_date)",
            ),
            (
                "receivables",
                "idx_receivables_paid_paid_at",
                "CREATE INDEX idx_receivables_paid_paid_at ON receivables (paid, paid_at)",
            ),
            (
                "receivables",
                "idx_receivables_tab_date_id",
                "CREATE INDEX idx_receivables_tab_date_id ON receivables (tab_id, incurred_date, id)",
            ),
            (
                "receivables",
                "idx_receivables_incurred_id",
                "CREATE INDEX idx_receivables_incurred_id ON receivables (incurred_date, id)",
            ),
            (
                "expenses",
                "idx_expenses_date_cat",
                "CREATE INDEX idx_expenses_date_cat ON expenses (expense_date, category)",
            ),
            (
                "orders",
                "idx_orders_status_created",
                "CREATE INDEX idx_orders_status_created ON orders (status, created_at)",
            ),
            (
                "customer_sessions",
                "idx_sessions_status_timein",
                "CREATE INDEX idx_sessions_status_timein ON customer_sessions (status, time_in)",
            ),
            (
                "inventory_logs",
                "idx_inventory_logs_item_created",
                "CREATE INDEX idx_inventory_logs_item_created ON inventory_logs (inventory_item_id, created_at)",
            ),
            (
                "checkout_void_requests",
                "uq_checkout_void_requests_key",
                "CREATE UNIQUE INDEX uq_checkout_void_requests_key ON checkout_void_requests (request_key)",
            ),
            (
                "checkout_void_requests",
                "idx_checkout_void_requests_tx",
                "CREATE INDEX idx_checkout_void_requests_tx ON checkout_void_requests (transaction_id)",
            ),
        ]

        table_indexes = {}

        for table_name, index_name, ddl in indexes:
            try:
                if table_name not in table_indexes:
                    if inspector.has_table(table_name):
                        table_indexes[table_name] = {idx['name'] for idx in inspector.get_indexes(table_name)}
                    else:
                        table_indexes[table_name] = set()

                if index_name in table_indexes[table_name]:
                    continue

                db.session.execute(text(ddl))
                db.session.commit()
                # Update cache
                table_indexes[table_name].add(index_name)
                print(f"[OK] Created index {index_name} on {table_name}")
            except Exception as exc:
                db.session.rollback()
                print(f"[WARNING] Index {index_name} skipped: {exc}")
