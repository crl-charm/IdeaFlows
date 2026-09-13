import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db
from app.models.admin import Admin
from app.models.user import User


def safe_update_admin(username: str, password: str, ensure_shadow: bool = True):
    app = create_app()
    with app.app_context():
        admin = Admin.query.filter_by(username=username).first()
        if admin:
            print(f"Found Admin id={admin.id}, updating password and flags.")
            admin.set_password(password)
            admin.failed_login_attempts = 0
            admin.locked_until = None
            db.session.add(admin)
        else:
            print("No Admin found; creating new Admin.")
            admin = Admin(full_name="System Admin", username=username)
            admin.set_password(password)
            db.session.add(admin)

        db.session.commit()
        print(f"Admin '{username}' now exists (id={admin.id}).")

        if ensure_shadow:
            shadow = User.query.filter_by(username=username).first()
            if shadow:
                print(f"Found shadow User id={shadow.id}; updating attributes to match admin.")
                shadow.full_name = admin.full_name
                shadow.role = "admin"
                shadow.job_role = "admin"
                shadow.is_active = False
                shadow.password = admin.password
                db.session.add(shadow)
                db.session.commit()
                print(f"Updated shadow User id={shadow.id}.")
            else:
                print("No shadow User found; creating one.")
                shadow = User(
                    full_name=admin.full_name,
                    username=admin.username,
                    role="admin",
                    job_role="admin",
                    is_active=False,
                )
                shadow.password = admin.password
                db.session.add(shadow)
                db.session.commit()
                print(f"Created shadow User id={shadow.id} for admin mapping.")

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--username', default='admin')
    parser.add_argument('--password', default='Admin123321!@#$')
    parser.add_argument('--no-shadow', action='store_true')
    args = parser.parse_args()
    safe_update_admin(args.username, args.password, ensure_shadow=not args.no_shadow)
