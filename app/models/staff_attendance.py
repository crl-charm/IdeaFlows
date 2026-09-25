from datetime import datetime
from app import db


class StaffAttendance(db.Model):
    __tablename__ = "staff_attendance"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    time_in = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    time_out = db.Column(db.DateTime, nullable=True)
    last_activity_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User", backref="attendance_records")
