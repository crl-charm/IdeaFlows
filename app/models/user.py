from datetime import datetime, timedelta

import bcrypt
from flask import current_app

from app import db
from app.models.auth_account_mixin import AuthAccountMixin


class User(db.Model, AuthAccountMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(50), unique=True, nullable=False)
    role = db.Column(db.String(20), nullable=False, default="staff")
    job_role = db.Column(db.String(50), nullable=False, default="general")  # cashier, cook, general
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username} role={self.role}>"