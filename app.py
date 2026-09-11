import os

from app import create_app, socketio
from app.db.bootstrap import initialize_database

app = create_app()

if app.config.get("AUTO_MIGRATE_ON_STARTUP", True):
    initialize_database(app, strict=app.config.get("FLASK_ENV") == "production")


if __name__ == "__main__":
    # Development uses Flask-SocketIO's threading mode. Production keeps its
    # eventlet monkey patch isolated in wsgi.py for the current Gunicorn unit.
    debug_mode = os.environ.get('FLASK_ENV') != 'production'
    socketio.run(app, host="0.0.0.0", port=5000, debug=debug_mode, allow_unsafe_werkzeug=True)


#add lg kay kasabad sng git
