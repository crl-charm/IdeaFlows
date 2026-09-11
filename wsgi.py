# eventlet.monkey_patch() MUST be the very first statement before any other
# import, including 'import os'. Even importing os creates threading.RLock
# objects that eventlet cannot re-green after the fact, causing
# RuntimeError: greenlet is being finalized.
import eventlet
eventlet.monkey_patch()

from app import create_app
from app.db.bootstrap import initialize_database

app = create_app()

if app.config.get("AUTO_MIGRATE_ON_STARTUP", True):
    initialize_database(app, strict=app.config.get("FLASK_ENV") == "production")

# Flask-SocketIO wraps app.wsgi_app during init_app, so the Flask application is
# the WSGI callable Gunicorn must load.
# Usage: gunicorn --worker-class eventlet -w 1 wsgi:application
application = app

if __name__ == "__main__":
    # For production: gunicorn --worker-class eventlet -w 1 wsgi:application
    # Direct python wsgi.py is for development only.
    app.run()
