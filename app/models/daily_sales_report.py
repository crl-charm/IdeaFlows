from datetime import datetime, date
from decimal import Decimal
from app import db


class DailySalesReport(db.Model):
    __tablename__ = "daily_sales_reports"

    id = db.Column(db.Integer, primary_key=True)
    report_date = db.Column(db.Date, nullable=False, unique=True)
    total_revenue = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    total_expenses = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    total_collections = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    total_payables_paid = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    total_other_income = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    total_budget_spend = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    net_balance = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    total_orders = db.Column(db.Integer, nullable=False, default=0)
    total_sessions = db.Column(db.Integer, nullable=False, default=0)
    generated_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    generated_at = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text, nullable=True)

    generated_by_user = db.relationship("User", backref="daily_sales_reports")
