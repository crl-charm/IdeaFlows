from datetime import datetime
from app import db

class Transaction(db.Model):
    __tablename__ = "transactions"

    id = db.Column(db.Integer, primary_key=True)

    session_id = db.Column(
        db.Integer,
        db.ForeignKey("customer_sessions.id"),
        nullable=False
    )

    time_bill = db.Column(db.Numeric(10,2), nullable=False)
    food_bill = db.Column(db.Numeric(10,2), nullable=False)
    total_bill = db.Column(db.Numeric(10,2), nullable=False)
    payment_method = db.Column(db.String(50), nullable=False, default="cash")
    collected_by = db.Column(db.String(100), nullable=True)
    amount_tendered = db.Column(db.Numeric(10, 2), nullable=True)
    discount_type = db.Column(db.String(20), nullable=True)
    discount_item_id = db.Column(db.Integer, nullable=True)
    discount_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    session = db.relationship("CustomerSession")
