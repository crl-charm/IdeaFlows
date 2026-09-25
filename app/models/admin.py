from __future__ import annotations

from datetime import datetime

from app import db
from app.models.auth_account_mixin import AuthAccountMixin


class Admin(db.Model, AuthAccountMixin):
    __tablename__ = "admins"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(50), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<Admin id={self.id} username={self.username}>"
