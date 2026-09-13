"""Production WSGI entrypoint for the threaded Socket.IO server."""

from app import create_app, socketio
from app.db.bootstrap import initialize_database

app = create_app()

if app.config.get("AUTO_MIGRATE_ON_STARTUP", True):
    initialize_database(app, strict=app.config.get("FLASK_ENV") == "production")

# Flask-SocketIO wraps app.wsgi_app during init_app, so the Flask application is
# the WSGI callable Gunicorn must load. simple-websocket supplies WebSocket
# support to the threaded Gunicorn worker.
# Usage: gunicorn --worker-class gthread --threads 50 -w 1 wsgi:application
application = app

if __name__ == "__main__":
    # Direct execution is for development only.
    socketio.run(app, allow_unsafe_werkzeug=True)
