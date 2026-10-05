from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from flask import current_app

from app.dto.serializers import serialize_user
from app.models import Admin, User
from app.repositories.admin_repository import AdminRepository, STAFF_RECOVERY_WINDOW


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

        existing_user = User.query.filter_by(username=username).first()
        if existing_user and existing_user.role == "staff" and not existing_user.is_active:
            cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - STAFF_RECOVERY_WINDOW
            if existing_user.deactivated_at and existing_user.deactivated_at > cutoff:
                return {"error": "This staff account is deactivated. Select Deactivated in the staff list to reactivate it."}, 409
            return {"error": "This username belongs to a former staff account and cannot be reused."}, 409
        if existing_user or Admin.query.filter_by(username=username).first():
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

    def list_users(self, page: int, per_page: int, *, active: bool = True):
        pagination = self.repo.list_staff_paginated(page, per_page, active=active)
        online_user_ids = self.active_staff_ids()
        return [
            {
                **serialize_user(u),
                "is_active": u.is_active,
                "is_online": u.id in online_user_ids,
                "reactivate_until": (u.deactivated_at + STAFF_RECOVERY_WINDOW).isoformat() + "Z"
                if u.deactivated_at and not u.is_active else None,
            }
            for u in pagination.items
        ]

    def active_staff_ids(self, leases=None) -> set[int]:
        lifetime = current_app.config["PERMANENT_SESSION_LIFETIME"]
        idle_seconds = lifetime.total_seconds() if hasattr(lifetime, "total_seconds") else float(lifetime)
        if current_app.config.get("SINGLE_SESSION_ENABLED"):
            active = leases if leases is not None else current_app.extensions["session_leases"].list_active()
            online_ids = {int(row["user_id"]) for row in active if row.get("identity", "").startswith("staff:")}
        else:
            online_ids = self.repo.list_online_staff_ids(idle_seconds)
        self.repo.close_inactive_staff_attendance(online_ids, idle_seconds)
        return online_ids

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
        self.repo.deactivate_staff(user, datetime.now(timezone.utc).replace(tzinfo=None))
        self.repo.save()
        return {"message": "Staff deactivated."}

    def reactivate_user(self, user_id: int):
        user = self.repo.get_staff_user(user_id, active=False)
        if not user:
            return {"error": "Deactivated staff not found."}, 404
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - STAFF_RECOVERY_WINDOW
        if not user.deactivated_at or user.deactivated_at <= cutoff:
            return {"error": "The 24-hour reactivation window has expired."}, 410
        user.is_active = True
        user.deactivated_at = None
        self.repo.save()
        return {"message": "Staff reactivated."}

    def customer_records(self):
        sessions = self.repo.list_customer_sessions()
        records = []
        for s in sessions:
            ordered_items = []
            for order in s.orders:
                for item in order.items:
                    ordered_items.append(f"{item.menu_item.name} x{item.quantity}")
            food_only = s.service_mode == "food_only"
            records.append(
                {
                    "id": s.id,
                    "name": s.customer_name,
                    "orders": ", ".join(ordered_items) if ordered_items else "No orders",
                    "room": s.space_type.name if s.space_type else "N/A",
                    "time_in": "Food only" if food_only else (s.time_in + timedelta(hours=8)).strftime("%Y-%m-%d %I:%M %p"),
                    "time_out": "Food only" if food_only else (
                        (s.time_out + timedelta(hours=8)).strftime("%Y-%m-%d %I:%M %p") if s.time_out else "Active"
                    ),
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
        self.active_staff_ids()
        shifts = self.repo.list_staff_shifts()
        logs = self.repo.list_staff_attendance()
        manual = [
            {
                "id": shift.id,
                "name": shift.user.full_name,
                "shift_role": shift.shift_role.title(),
                "time_in": (shift.time_in + timedelta(hours=8)).strftime("%Y-%m-%d %I:%M %p"),
                "time_out": (shift.time_out + timedelta(hours=8)).strftime("%Y-%m-%d %I:%M %p") if shift.time_out else "Open shift",
                "time_in_at": shift.time_in.isoformat(),
                "time_out_at": shift.time_out.isoformat() if shift.time_out else None,
                "time_in_date": (shift.time_in + timedelta(hours=8)).date().isoformat(),
                "time_out_date": (shift.time_out + timedelta(hours=8)).date().isoformat() if shift.time_out else None,
                "source": "Manual shift",
                "sort_at": shift.time_in,
            }
            for shift in shifts if shift.user and shift.user.role == "staff"
        ]
        legacy = [
            {
                "id": log.id,
                "name": log.user.full_name,
                "shift_role": "Not recorded",
                "time_in": (log.time_in + timedelta(hours=8)).strftime("%Y-%m-%d %I:%M %p") if log.time_in else "N/A",
                "time_out": (log.time_out + timedelta(hours=8)).strftime("%Y-%m-%d %I:%M %p") if log.time_out else "Active",
                "time_in_at": log.time_in.isoformat() if log.time_in else None,
                "time_out_at": log.time_out.isoformat() if log.time_out else None,
                "time_in_date": (log.time_in + timedelta(hours=8)).date().isoformat() if log.time_in else None,
                "time_out_date": (log.time_out + timedelta(hours=8)).date().isoformat() if log.time_out else None,
                "source": "Legacy login record",
                "sort_at": log.time_in,
            }
            for log in logs
            if log.user and log.user.role == "staff"
        ]
        rows = sorted(manual + legacy, key=lambda row: row["sort_at"] or datetime.min, reverse=True)
        for row in rows:
            del row["sort_at"]
        return rows

    def staff_attendance_events(self, target_date=None):
        events = []
        for row in self.staff_attendance():
            for action in ("time_in", "time_out"):
                at = row[f"{action}_at"]
                event_date = row[f"{action}_date"]
                if not at or target_date and event_date != target_date.isoformat():
                    continue
                events.append({
                    "id": f"{row['source']}:{row['id']}:{action}",
                    "record_id": row["id"],
                    "name": row["name"],
                    "shift_role": row["shift_role"],
                    "source": row["source"],
                    "event": "Time In" if action == "time_in" else "Time Out",
                    "event_date": event_date,
                    "event_at": at,
                    "time": row[action],
                    "paired_time": row["time_out" if action == "time_in" else "time_in"],
                })
        return sorted(events, key=lambda event: (event["event_at"], event["id"]), reverse=True)

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
        if space.name == "Take Out":
            return {"error": "Take Out has no seating capacity."}, 400
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
