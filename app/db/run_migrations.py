"""
Run this script manually to apply schema changes and seed data.
Usage: python -m app.db.run_migrations
"""

from app import create_app
from app.db.bootstrap import initialize_database


def main() -> None:
    app = create_app()
    initialize_database(app, strict=True)
    print("Migration and seeding complete.")


if __name__ == "__main__":
    main()
