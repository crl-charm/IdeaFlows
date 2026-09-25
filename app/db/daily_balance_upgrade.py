"""Add dated finance history without changing existing operational rows."""

import argparse

from sqlalchemy import inspect, text

from app import create_app, db
from app.models import PayablePayment


COLUMNS = (
    ("receivable_payments", "balance_before", "ALTER TABLE receivable_payments ADD COLUMN balance_before NUMERIC(10,2) NULL"),
    ("receivable_payments", "balance_after", "ALTER TABLE receivable_payments ADD COLUMN balance_after NUMERIC(10,2) NULL"),
    ("receivable_payments", "request_key", "ALTER TABLE receivable_payments ADD COLUMN request_key VARCHAR(200) NULL"),
    ("expenses", "payment_method", "ALTER TABLE expenses ADD COLUMN payment_method VARCHAR(50) NULL"),
    ("expenses", "voided_at", "ALTER TABLE expenses ADD COLUMN voided_at DATETIME NULL"),
    ("expenses", "voided_by", "ALTER TABLE expenses ADD COLUMN voided_by INTEGER NULL"),
    ("expenses", "void_reason", "ALTER TABLE expenses ADD COLUMN void_reason VARCHAR(255) NULL"),
    ("expenses", "request_key", "ALTER TABLE expenses ADD COLUMN request_key VARCHAR(200) NULL"),
    ("finance_transactions", "payment_method", "ALTER TABLE finance_transactions ADD COLUMN payment_method VARCHAR(50) NULL"),
    ("finance_transactions", "actor_id", "ALTER TABLE finance_transactions ADD COLUMN actor_id INTEGER NULL"),
    ("finance_transactions", "request_key", "ALTER TABLE finance_transactions ADD COLUMN request_key VARCHAR(200) NULL"),
    ("daily_sales_reports", "total_collections", "ALTER TABLE daily_sales_reports ADD COLUMN total_collections NUMERIC(12,2) NOT NULL DEFAULT 0"),
    ("daily_sales_reports", "total_payables_paid", "ALTER TABLE daily_sales_reports ADD COLUMN total_payables_paid NUMERIC(12,2) NOT NULL DEFAULT 0"),
    ("daily_sales_reports", "total_other_income", "ALTER TABLE daily_sales_reports ADD COLUMN total_other_income NUMERIC(12,2) NOT NULL DEFAULT 0"),
    ("daily_sales_reports", "total_budget_spend", "ALTER TABLE daily_sales_reports ADD COLUMN total_budget_spend NUMERIC(12,2) NOT NULL DEFAULT 0"),
    ("soft_balance_entries", "total_collections", "ALTER TABLE soft_balance_entries ADD COLUMN total_collections NUMERIC(12,2) NOT NULL DEFAULT 0"),
    ("soft_balance_entries", "total_payables_paid", "ALTER TABLE soft_balance_entries ADD COLUMN total_payables_paid NUMERIC(12,2) NOT NULL DEFAULT 0"),
    ("soft_balance_entries", "total_other_income", "ALTER TABLE soft_balance_entries ADD COLUMN total_other_income NUMERIC(12,2) NOT NULL DEFAULT 0"),
    ("soft_balance_entries", "total_budget_spend", "ALTER TABLE soft_balance_entries ADD COLUMN total_budget_spend NUMERIC(12,2) NOT NULL DEFAULT 0"),
)


def upgrade(engine):
    with engine.begin() as connection:
        for table, column, ddl in COLUMNS:
            if column not in {entry["name"] for entry in inspect(connection).get_columns(table)}:
                connection.execute(text(ddl))
        indexes = {entry["name"] for entry in inspect(connection).get_indexes("expenses")}
        unique_columns = {tuple(entry["column_names"]) for entry in inspect(connection).get_unique_constraints("expenses")}
        if "uq_expenses_request_key" not in indexes and ("request_key",) not in unique_columns:
            connection.execute(text("CREATE UNIQUE INDEX uq_expenses_request_key ON expenses (request_key)"))
        finance_indexes = {entry["name"] for entry in inspect(connection).get_indexes("finance_transactions")}
        finance_unique = {tuple(entry["column_names"]) for entry in inspect(connection).get_unique_constraints("finance_transactions")}
        if "uq_finance_transactions_request_key" not in finance_indexes and ("request_key",) not in finance_unique:
            connection.execute(text("CREATE UNIQUE INDEX uq_finance_transactions_request_key ON finance_transactions (request_key)"))
        receivable_indexes = {entry["name"] for entry in inspect(connection).get_indexes("receivable_payments")}
        if "ix_receivable_payments_request_key" not in receivable_indexes:
            connection.execute(text("CREATE INDEX ix_receivable_payments_request_key ON receivable_payments (request_key)"))
        PayablePayment.__table__.create(bind=connection, checkfirst=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    from config import Config

    Config.AUTO_MIGRATE_ON_STARTUP = False
    app = create_app()
    with app.app_context():
        inspector = inspect(db.engine)
        print(f"Database: {db.engine.url.host or 'local'}/{db.engine.url.database or '(unnamed)'}")
        for table, column, _ in COLUMNS:
            present = column in {entry["name"] for entry in inspector.get_columns(table)}
            print(f"{table}.{column}: {'ready' if present else 'missing'}")
        print(f"payable_payments: {'ready' if inspector.has_table('payable_payments') else 'missing'}")
        print(f"expenses.request_key unique index: {'ready' if ('request_key',) in {tuple(i['column_names']) for i in inspector.get_unique_constraints('expenses')} or 'uq_expenses_request_key' in {i['name'] for i in inspector.get_indexes('expenses')} else 'missing'}")
        if args.apply:
            upgrade(db.engine)
            print("Daily Balance history schema ready.")
        else:
            print("Preview only. No data changed.")


if __name__ == "__main__":
    main()
