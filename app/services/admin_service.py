from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from app.dto.serializers import serialize_user
from app.models import Admin, User
from app.repositories.admin_repository import AdminRepository


@dataclass(frozen=True)
class AdminService:
    repo: AdminRepository

    def register_staff(self, data: dict[str, Any]):
        full_name = data.get("full_name", "").strip()
        username = data.get("username", "").strip()
        role = "staff"
        job_role = data.get("job_role", "general").strip().lower()
        password = data.get("password", "")
        valid_job_roles = {"general", "cashier", "cook", "server"}

        # Enhanced validation
        if not full_name or not username or not password:
            return {"error": "All fields are required."}, 400

        if len(username) < 3:
            return {"error": "Username must be at least 3 characters."}, 400

        if len(full_name) < 2:
            return {"error": "Full name must be at least 2 characters."}, 400

        if job_role not in valid_job_roles:
            return {"error": "Invalid job role."}, 400

        if User.query.filter_by(username=username).first() or Admin.query.filter_by(username=username).first():
            return {"error": "Username already exists."}, 409

        # Password strength validation is handled in User model
        try:
            user = User(full_name=full_name, username=username, role=role, job_role=job_role)
            user.set_password(password)
        except ValueError as e:
            return {"error": str(e)}, 400

        self.repo.add(user)
        self.repo.save()
        return {"message": "Staff created successfully."}, 201

    def list_users(self, page: int, per_page: int):
        pagination = self.repo.list_staff_paginated(page, per_page)
        online_user_ids = self.repo.list_online_staff_ids()
        return [
            {**serialize_user(u), "is_online": u.id in online_user_ids}
            for u in pagination.items
        ]

    def edit_user(self, user_id: int, data: dict[str, Any]):
        user = self.repo.get_staff_user(user_id)
        if not user:
            return {"error": "Staff not found."}, 404
        if "full_name" in data:
            user.full_name = data["full_name"].strip()
        if "username" in data:
            if self.repo.username_exists_for_other(data["username"], user_id):
                return {"error": "Username already taken."}, 409
            user.username = data["username"].strip()
        if "job_role" in data:
            valid_job_roles = {"general", "cashier", "cook", "server"}
            jr = data["job_role"].strip().lower()
            if jr in valid_job_roles:
                user.job_role = jr
        if "password" in data and data["password"]:
            user.set_password(data["password"])
        self.repo.save()
        return {"message": "Staff updated."}

    def delete_user(self, user_id: int):
        user = self.repo.get_staff_user(user_id)
        if not user:
            return {"error": "Staff not found."}, 404
        self.repo.delete_staff_attendance(user_id)
        self.repo.clear_user_orders(user_id)
        from app import db

        db.session.delete(user)
        self.repo.save()
        return {"message": "Staff deleted."}

    def customer_records(self):
        sessions = self.repo.list_customer_sessions()
        records = []
        for s in sessions:
            ordered_items = []
            for order in s.orders:
                for item in order.items:
                    ordered_items.append(f"{item.menu_item.name} x{item.quantity}")
            records.append(
                {
                    "id": s.id,
                    "name": s.customer_name,
                    "orders": ", ".join(ordered_items) if ordered_items else "No orders",
                    "room": s.space_type.name if s.space_type else "N/A",
                    "time_in": (s.time_in + timedelta(hours=8)).strftime("%Y-%m-%d %I:%M %p") if s.time_in else "N/A",
                    "time_out": (s.time_out + timedelta(hours=8)).strftime("%Y-%m-%d %I:%M %p") if s.time_out else "Active",
                }
            )
        return records

    def customer_count(self) -> int:
        return self.repo.count_customer_sessions()

    def space_prices(self) -> list[dict[str, Any]]:
        data = []
        for space, last_changed in self.repo.list_spaces_with_latest_price_change():
            rate_per_minute = float(space.rate_per_minute or 0)
            data.append(
                {
                    "id": space.id,
                    "name": space.name,
                    "rate_per_minute": rate_per_minute,
                    "hourly_rate": rate_per_minute * 60,
                    "last_changed": last_changed.isoformat() if last_changed else "Never",
                    "description": space.description or "",
                }
            )
        return data

    def staff_attendance(self):
        logs = self.repo.list_staff_attendance()
        return [
            {
                "id": log.id,
                "name": log.user.full_name,
                "time_in": (log.time_in + timedelta(hours=8)).strftime("%Y-%m-%d %I:%M %p") if log.time_in else "N/A",
                "time_out": (log.time_out + timedelta(hours=8)).strftime("%Y-%m-%d %I:%M %p") if log.time_out else "Active",
            }
            for log in logs
            if log.user and log.user.role == "staff"
        ]

    def capacities(self):
        rows = self.repo.list_spaces_with_occupancy()
        result = []
        for row in rows:
            capacity = int(row.capacity) if row.capacity is not None else None
            occupied = int(row.occupied or 0)
            result.append(
                {
                    "id": row.id,
                    "name": row.name,
                    "capacity": capacity,
                    "occupied_seats": occupied,
                    "seats_left": (max(capacity - occupied, 0) if capacity is not None else None),
                }
            )
        return result

    def set_capacity(self, space_id: int, capacity):
        space = self.repo.get_space(space_id)
        if not space:
            return {"error": "Space not found."}, 404
        cap = int(capacity) if capacity not in (None, "", 0) else None
        space.capacity = cap
        self.repo.save()
        return {"message": "Capacity updated.", "capacity": space.capacity}

    def analytics(self):
        rows = self.repo.staff_analytics()
        result = [
            {
                "id": r.id,
                "name": r.full_name,
                "job_role": r.job_role or "general",
                "orders_count": int(r.orders_count or 0),
                "customers_count": int(r.customers_count or 0),
            }
            for r in rows
        ]
        result.sort(key=lambda r: (r["customers_count"], r["orders_count"]), reverse=True)
        return result
