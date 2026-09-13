# IdeaHub production scaling

The application is prepared for safe horizontal scaling, but the supplied VPS
service intentionally starts one threaded Gunicorn process. Scale only after the
shared dependencies below are in place.

## Current production topology

`Nginx -> Gunicorn/gthread -> Flask -> MySQL`, with Redis shared by Socket.IO
and Flask-Limiter. Nginx serves static files directly. `/health/live` checks the
process and `/health/ready` checks the database connection.

Redis also holds short-lived serialized menu/catalogue reads. Menu creates,
updates, availability changes, and deletes invalidate the whole menu namespace
after the database commit. Orders, sessions, inventory deductions, and finance
records are deliberately never served from cache.

## Scaling rules

1. Set the same `SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`, and upload storage for
   every application instance.
2. Run `python -m app.db.run_migrations` exactly once per release. Set
   `AUTO_MIGRATE_ON_STARTUP=false` on serving instances.
3. Keep one threaded worker per Gunicorn process. Add more processes/hosts behind
   an upstream load balancer instead of increasing `-w` in a single Socket.IO
   command.
4. Enable sticky sessions for Socket.IO clients at the load balancer. Redis
   distributes broadcasts between instances.
5. Put uploads on shared object storage or a shared filesystem before adding a
   second host. The local upload folder is only safe for a single host.
6. Budget MySQL connections across the fleet:
   `(DB_POOL_SIZE + DB_MAX_OVERFLOW) * application_processes` must remain below
   the database connection limit with headroom for migrations and operations.
7. Drain an instance using the readiness check, then send Gunicorn `SIGQUIT` for
   graceful shutdown. Never run schema changes concurrently from every worker.

## Release verification

Run these before routing traffic to a new release:

```bash
python scripts/validate_imports.py
python -m pytest -q tests
python -m app.db.run_migrations
curl --fail http://127.0.0.1:5000/health/live
curl --fail http://127.0.0.1:5000/health/ready
```

Monitor HTTP error rate, p95 latency, MySQL pool saturation, Redis availability,
process restarts, disk space, and the rotating logs in `LOG_DIR`.
