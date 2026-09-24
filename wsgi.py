"""Production WSGI entrypoint for the threaded Socket.IO server."""

from app import create_app, socketio

app = create_app()

# Flask-SocketIO wraps app.wsgi_app during init_app, so the Flask application is
# the WSGI callable Gunicorn must load. simple-websocket supplies WebSocket
# support to the threaded Gunicorn worker.
# Usage: gunicorn --worker-class gthread --threads 50 -w 1 wsgi:application
application = app

if __name__ == "__main__":
    # Direct execution is for development only.
    socketio.run(app, allow_unsafe_werkzeug=True)
