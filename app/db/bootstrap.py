"""Database startup orchestration shared by local and production entrypoints."""

from __future__ import annotations

import logging

from app import db
from app.db.migrator import SchemaMigrator
from app.db.seeder import DatabaseSeeder


logger = logging.getLogger(__name__)


def initialize_database(app, *, strict: bool = False) -> bool:
    try:
        with app.app_context():
            SchemaMigrator(db, app).run()
            DatabaseSeeder(db, app).run()
    except Exception:
        logger.exception("Database initialization failed")
        if strict:
            raise
        return False
    return True
