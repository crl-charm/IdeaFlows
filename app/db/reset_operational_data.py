"""One-time business-data reset. Run without --execute to preview row counts."""

from __future__ import annotations

import argparse
from decimal import Decimal

from sqlalchemy import func, inspect, select

from app import create_app, db
from app.core.cache import invalidate_menu_cache
from app.models import FinanceBudget, SpaceType
from app.models.menu_category import MenuCategory


ACCOUNT_TABLES = {"admins", "users"}
RESET_TABLES = {
    "boardroom_bookings",
    "customer_sessions",
    "daily_sales_reports",
    "expenses",
    "finance_budgets",
    "finance_transactions",
    "inventory_actions",
    "inventory_items",
    "inventory_logs",
    "lounge_bookings",
    "menu_categories",
    "menu_item_ingredients",
    "menu_items",
    "order_inventory_allocations",
    "order_items",
    "orders",
    "payables",
    "receivables",
    "receivable_payments",
    "soft_balance_entries",
    "space_price_history",
    "space_types",
    "staff_attendance",
    "staff_performance_logs",
    "transactions",
}


def preview_reset() -> dict[str, int]:
    """Fail closed if production has tables this reset has not been reviewed for."""
    expected = ACCOUNT_TABLES | RESET_TABLES
    mapped = set(db.metadata.tables)
    live = set(inspect(db.engine).get_table_names())
    if mapped != expected or live != expected:
        raise RuntimeError(
            f"Schema mismatch; reset cancelled. Unreviewed tables: {sorted((mapped | live) - expected)}; "
            f"missing mapped tables: {sorted(expected - mapped)}; missing database tables: {sorted(expected - live)}"
        )
    return {
        name: int(db.session.scalar(select(func.count()).select_from(db.metadata.tables[name])) or 0)
        for name in sorted(expected)
    }


def reset_operational_data(expected_database: str) -> None:
    """Delete every non-account table, then restore required empty-site defaults."""
    preview_reset()
    if not expected_database or (db.engine.url.database or ":memory:") != expected_database:
        raise ValueError("Database name does not match --expect-database; reset cancelled")

    try:
        for table in reversed(db.metadata.sorted_tables):
            if table.name in RESET_TABLES:
                db.session.execute(table.delete())

        db.session.expunge_all()

        db.session.add_all(
            [
                SpaceType(name="Regular Lounge", rate_per_minute=Decimal("0.1667"), capacity=30),
                SpaceType(name="Premium Lounge", rate_per_minute=Decimal("0.3333"), capacity=30),
                SpaceType(name="Boardroom", rate_per_minute=Decimal("4.1667")),
                SpaceType(name="Whole Hub", rate_per_minute=Decimal("8.3333")),
                FinanceBudget(_name="Main Budget", _total_budget=Decimal("0.00"), _allocated=Decimal("0.00")),
                MenuCategory(name="Main Dish"),
                MenuCategory(name="Snack"),
                MenuCategory(name="Beverages"),
            ]
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    invalidate_menu_cache()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Perform the reset after reviewing the preview")
    parser.add_argument("--expect-database", help="Exact database name required with --execute")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        print(f"Database: {db.engine.url.host or 'local'}/{db.engine.url.database or '(unnamed)'}")
        for name, count in preview_reset().items():
            print(f"{name}: {count} {'KEEP' if name in ACCOUNT_TABLES else 'DELETE'}")
        if args.execute:
            reset_operational_data(args.expect_database or "")
            print("Operational data cleared. Account rows preserved; default spaces, budget, and categories restored.")
        else:
            print("Preview only. No data changed.")


if __name__ == "__main__":
    main()
