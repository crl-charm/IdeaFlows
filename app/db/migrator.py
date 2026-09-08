from __future__ import annotations

from sqlalchemy import text, inspect
from app.models import Admin
from app.models.finance import FinanceBudget, FinanceTransaction
from app.models.soft_balance import SoftBalanceEntry
from app.models.space_price_history import SpacePriceHistory
from app.models.payable import Payable
from app.models.menu_category import MenuCategory


class SchemaMigrator:
    """Runs ALTER TABLE statements in an idempotent way."""

    def __init__(self, db, app) -> None:
        self._db = db
        self._app = app

    def run(self) -> None:
        db = self._db
        _ = (FinanceBudget, FinanceTransaction, SoftBalanceEntry, SpacePriceHistory, Payable, MenuCategory)
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

    def _ensure_indexes(self, db, inspector) -> None:
        """Create performance indexes idempotently (MySQL/SQLite)."""
        indexes = [
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
