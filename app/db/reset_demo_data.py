"""Clear demo activity while keeping accounts, catalog, spaces, and prices.

Run without --execute to preview. Stop the app and verify a fresh backup before
executing this one-time client handoff command.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select

from app import create_app, db
from app.core.cache import invalidate_menu_cache
from app.db.reset_operational_data import ACCOUNT_TABLES, RESET_TABLES, preview_reset
from app.models import BoardroomBooking, CustomerSession, FinanceBudget, InventoryItem, LoungeBooking
from app.utils.dates import manila_date


SETUP_TABLES = {
    "finance_budgets", "inventory_items", "menu_categories", "menu_item_ingredients",
    "menu_items", "space_price_history", "space_types",
}
ACTIVITY_TABLES = {
    "boardroom_bookings", "booking_changes", "customer_sessions", "daily_sales_reports",
    "expenses", "finance_transactions", "inventory_actions", "inventory_logs",
    "lounge_bookings", "order_inventory_allocations", "order_items", "orders",
    "payables", "payable_payments", "receivables", "receivable_payments",
    "soft_balance_entries", "staff_attendance", "staff_shifts", "staff_performance_logs",
    "transactions",
}


def preview_demo_reset() -> tuple[dict[str, int], int, int]:
    """Count affected rows; reject any schema table without a reviewed action."""
    counts = preview_reset()
    expected = ACCOUNT_TABLES | RESET_TABLES
    if (ACCOUNT_TABLES | SETUP_TABLES | ACTIVITY_TABLES) != expected or (
        ACCOUNT_TABLES | SETUP_TABLES
    ) & ACTIVITY_TABLES:
        raise RuntimeError("Demo reset table list needs review before use.")

    active = int(db.session.scalar(
        select(func.count()).select_from(CustomerSession).where(CustomerSession.status == "active")
    ) or 0)
    today = manila_date(datetime.now(timezone.utc).replace(tzinfo=None))
    upcoming = sum(int(db.session.scalar(
        select(func.count()).select_from(model).where(model.date >= today)
    ) or 0) for model in (BoardroomBooking, LoungeBooking))
    return counts, active, upcoming


def reset_demo_data(expected_database: str, expected_delete_rows: int, *,
                    confirm_active_sessions=False, confirm_future_bookings=False) -> None:
    counts, active, upcoming = preview_demo_reset()
    if not expected_database or (db.engine.url.database or ":memory:") != expected_database:
        raise ValueError("Database name does not match --expect-database; reset cancelled.")
    if sum(counts[name] for name in ACTIVITY_TABLES) != expected_delete_rows:
        raise ValueError("Activity row count changed since preview; reset cancelled.")
    if active and not confirm_active_sessions:
        raise RuntimeError("Active customer sessions exist; review them and pass --confirm-active-sessions if they are demo data.")
    if upcoming and not confirm_future_bookings:
        raise RuntimeError("Upcoming bookings exist; review them and pass --confirm-future-bookings if they are demo data.")

    try:
        db.session.expunge_all()
        for table in reversed(db.metadata.sorted_tables):
            if table.name in ACTIVITY_TABLES:
                db.session.execute(table.delete())
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        db.session.execute(InventoryItem.__table__.update().values(stock_qty=Decimal("0.00"), updated_at=now))
        db.session.execute(FinanceBudget.__table__.update().values(
            total_budget=Decimal("0.00"), allocated=Decimal("0.00"), updated_at=now,
        ))
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    invalidate_menu_cache()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Clear demo activity after reviewing the preview")
    parser.add_argument("--expect-database", help="Exact database name required with --execute")
    parser.add_argument("--expect-delete-rows", type=int, help="Exact activity row count from the preview")
    parser.add_argument("--confirm-active-sessions", action="store_true", help="Confirm listed active sessions are demo data")
    parser.add_argument("--confirm-future-bookings", action="store_true", help="Confirm listed upcoming bookings are demo data")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        counts, active, upcoming = preview_demo_reset()
        print(f"Database: {db.engine.url.host or 'local'}/{db.engine.url.database or '(unnamed)'}")
        for name, count in counts.items():
            action = "KEEP" if name in ACCOUNT_TABLES or name in SETUP_TABLES else "DELETE"
            if name == "inventory_items":
                action = "KEEP ITEMS; ZERO STOCK"
            elif name == "finance_budgets":
                action = "KEEP BUDGETS; ZERO AMOUNTS"
            print(f"{name}: {count} {action}")
        print(f"Activity rows to delete: {sum(counts[name] for name in ACTIVITY_TABLES)}")
        print(f"Active customer sessions: {active}")
        print(f"Bookings today or later (Asia/Manila): {upcoming}")
        stock_with_amount = db.session.scalar(select(func.count()).select_from(InventoryItem).where(InventoryItem.stock_qty != 0)) or 0
        budgets_with_amount = db.session.scalar(select(func.count()).select_from(FinanceBudget).where(
            (FinanceBudget._total_budget != 0) | (FinanceBudget._allocated != 0)
        )) or 0
        print(f"Inventory items with nonzero stock: {stock_with_amount}")
        print(f"Budgets with nonzero amounts: {budgets_with_amount}")
        if args.execute:
            if args.expect_delete_rows is None or args.expect_delete_rows < 0:
                parser.error("--expect-delete-rows from the preview is required with --execute")
            reset_demo_data(args.expect_database or "", args.expect_delete_rows,
                            confirm_active_sessions=args.confirm_active_sessions,
                            confirm_future_bookings=args.confirm_future_bookings)
            print("Demo activity cleared; accounts and setup preserved; stock and budget amounts set to zero.")
        else:
            print("Preview only. No data changed.")


if __name__ == "__main__":
    main()
