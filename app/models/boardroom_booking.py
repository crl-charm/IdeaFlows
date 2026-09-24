from datetime import datetime
from app import db

class BoardroomBooking(db.Model):
    __tablename__ = "boardroom_bookings"

    id = db.Column(db.Integer, primary_key=True)

    customer_name = db.Column(db.String(100), nullable=False)

    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)

    number_of_people = db.Column(db.Integer, nullable=False)
    course = db.Column(db.String(100), nullable=True)
    purpose = db.Column(db.String(255), nullable=True)
    booking_type = db.Column(db.String(20), nullable=False, default="boardroom")
    hourly_rate = db.Column(db.Numeric(10, 2), nullable=False, default=250)

    status = db.Column(db.String(20), default="booked")
    session_id = db.Column(db.Integer, db.ForeignKey("customer_sessions.id"), nullable=True)
    started_at = db.Column(db.DateTime, nullable=True)
    expected_end_at = db.Column(db.DateTime, nullable=True)
    ended_at = db.Column(db.DateTime, nullable=True)
    extended_minutes = db.Column(db.Integer, nullable=False, default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    session = db.relationship("CustomerSession", backref="boardroom_booking", uselist=False)
