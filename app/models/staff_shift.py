from datetime import datetime

from app import db


class StaffShift(db.Model):
    __tablename__ = "staff_shifts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    shift_role = db.Column(db.String(50), nullable=False)
    time_in = db.Column(db.DateTime, nullable=False)
    time_out = db.Column(db.DateTime, nullable=True)
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    time_out_recorded_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User", backref="manual_shifts")
