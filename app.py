# eventlet.monkey_patch() MUST be the very first statement before any other
# import, including 'import os'. Even importing os creates threading.RLock
# objects that eventlet cannot re-green after the fact, causing
# RuntimeError: greenlet is being finalized.
import eventlet
eventlet.monkey_patch()

import os

from app import create_app, db, socketio
from app.db.migrator import SchemaMigrator
from app.db.seeder import DatabaseSeeder

app = create_app()

if not os.environ.get("VERCEL"):
    try:
        with app.app_context():
            SchemaMigrator(db, app).run()
            DatabaseSeeder(db, app).run()
    except Exception as err:
        print(f"Startup migration warning: {err}")


if __name__ == "__main__":
    # In production use: gunicorn --worker-class eventlet -w 1 wsgi:application
    # Direct python app.py is for development only.
    debug_mode = os.environ.get('FLASK_ENV') != 'production'
    socketio.run(app, host="0.0.0.0", port=5000, debug=debug_mode, allow_unsafe_werkzeug=True)


