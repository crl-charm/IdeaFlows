"""Inventory-only upgrade. Default is a read-only report; --apply adds schema."""
import argparse
import json

from sqlalchemy import inspect, text

from app import create_app, db
from app.models.inventory import InventoryAction, OrderInventoryAllocation


def upgrade(engine):
    with engine.begin() as connection:
        columns = {column["name"] for column in inspect(connection).get_columns("menu_items")}
        if "inventory_mode" not in columns:
            connection.execute(text("ALTER TABLE menu_items ADD COLUMN inventory_mode VARCHAR(16) NULL"))
        InventoryAction.__table__.create(connection, checkfirst=True)
        OrderInventoryAllocation.__table__.create(connection, checkfirst=True)
        allocation_columns = {column["name"] for column in inspect(connection).get_columns("order_inventory_allocations")}
        for name, ddl in (
            ("menu_item_id", "INTEGER NULL"),
            ("ordered_units", "INTEGER NULL"),
            ("updated_at", "DATETIME NULL"),
        ):
            if name not in allocation_columns:
                connection.execute(text(f"ALTER TABLE order_inventory_allocations ADD COLUMN {name} {ddl}"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    app = create_app()
    with app.app_context():
        rows = db.session.execute(text("""
            SELECT m.id, m.name, m.category,
                (SELECT COUNT(*) FROM menu_item_ingredients r WHERE r.menu_item_id=m.id) AS recipes,
                (SELECT COUNT(*) FROM inventory_items i WHERE i.menu_item_id=m.id) AS stock_rows,
                (SELECT MIN(i.stock_qty) FROM inventory_items i WHERE i.menu_item_id=m.id) AS stock
            FROM menu_items m WHERE m.status != 'deleted' ORDER BY m.id
        """)).mappings().all()
        report = [dict(row, inferred_mode="recipe" if row["recipes"] else "direct" if row["stock_rows"] else "untracked") for row in rows]
        print(json.dumps(report, indent=2, default=str))
        if any(row["stock_rows"] > 1 for row in rows):
            raise SystemExit("Duplicate inventory rows found. Reconcile them before upgrading.")
        db.session.rollback()
        if args.apply:
            upgrade(db.engine)
            print("Inventory schema ready. Existing choices remain inferred until the owner reviews them.")


if __name__ == "__main__":
    main()
