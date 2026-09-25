"""Add booking and checkout actor columns without running data seeders."""

import argparse

from sqlalchemy import inspect, text

from app import create_app, db


COLUMNS = (
    ("boardroom_bookings", "booked_by", "ALTER TABLE boardroom_bookings ADD COLUMN booked_by VARCHAR(100) NULL"),
    ("transactions", "collected_by", "ALTER TABLE transactions ADD COLUMN collected_by VARCHAR(100) NULL"),
)


def upgrade(engine):
    with engine.begin() as connection:
        for table, column, ddl in COLUMNS:
            if column not in {entry["name"] for entry in inspect(connection).get_columns(table)}:
                connection.execute(text(ddl))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    from config import Config

    Config.AUTO_MIGRATE_ON_STARTUP = False
    app = create_app()
    with app.app_context():
        print(f"Database: {db.engine.url.host or 'local'}/{db.engine.url.database or '(unnamed)'}")
        for table, column, _ in COLUMNS:
            present = column in {entry["name"] for entry in inspect(db.engine).get_columns(table)}
            print(f"{table}.{column}: {'ready' if present else 'missing'}")
        if args.apply:
            upgrade(db.engine)
            print("Financial actor columns ready.")
        else:
            print("Preview only. No data changed.")


if __name__ == "__main__":
    main()
