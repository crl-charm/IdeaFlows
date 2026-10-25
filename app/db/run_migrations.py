"""Apply schema changes, seed data, and provision one-time production admins."""

import os
from pathlib import Path
import secrets

from app import create_app
from app import db
from app.db.bootstrap import initialize_database
from app.models import Admin, User


CLIENT_ADMINS = {
    "admin_gilbert": "Admin Gilbert",
    "admin3": "Admin 3",
}


def provision_client_admins(app, credentials_path: Path | None = None) -> bool:
    """Create both production accounts once, keeping plaintext outside Git."""
    if app.config.get("FLASK_ENV") != "production":
        return False

    with app.app_context():
        existing = {
            admin.username: admin
            for admin in Admin.query.filter(Admin.username.in_(CLIENT_ADMINS)).all()
        }
        existing_users = User.query.filter(User.username.in_(CLIENT_ADMINS)).all()
        if len(existing) == len(CLIENT_ADMINS):
            if (
                any(admin.full_name != CLIENT_ADMINS[name] for name, admin in existing.items())
                or any(user.role != "admin" or user.is_active for user in existing_users)
            ):
                raise RuntimeError("Client admin username belongs to a different account")
            print("[OK] Client admin accounts already exist; passwords unchanged")
            return False
        if existing or existing_users:
            raise RuntimeError("Client admin username already exists; inspect before provisioning")

        passwords = {
            username: f"Aa1!{index}{secrets.token_urlsafe(32)}"
            for index, username in enumerate(CLIENT_ADMINS, start=1)
        }
        path = Path(credentials_path) if credentials_path else Path.home() / ".ideaflow" / "client-admin-credentials.txt"
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                for username, password in passwords.items():
                    file.write(f"{username}: {password}\n")
                file.flush()
                os.fsync(file.fileno())
        except Exception:
            path.unlink(missing_ok=True)
            raise

        try:
            for username, full_name in CLIENT_ADMINS.items():
                admin = Admin(username=username, full_name=full_name)
                admin.set_password(passwords[username])
                db.session.add(admin)
            db.session.commit()
        except Exception:
            db.session.rollback()
            # Keep the file: a lost acknowledgement can follow a successful commit.
            raise

        print(f"[OK] Client admin accounts created; retrieve passwords from {path}")
        return True


def main() -> None:
    app = create_app()
    initialize_database(app, strict=True)
    provision_client_admins(app)
    print("Migration and seeding complete.")


if __name__ == "__main__":
    main()
