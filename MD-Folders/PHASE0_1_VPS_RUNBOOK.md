# Phase 0–1 VPS Runbook

This runbook stabilizes Socket.IO only. It does not deploy application code, run
migrations, edit `.env`, modify MySQL rows, or change R2 objects.

## Verified public baseline (2026-09-13)

- `GET /health/live`: HTTP 200; `Server-Timing` application duration 0.4 ms.
- `GET /health/ready`: HTTP 200; `Server-Timing` application duration 412.5 ms.
- Direct WebSocket handshake: HTTP 101.
- Twelve Engine.IO polling handshakes reached HTTP 200, but all twelve follow-up
  connect requests returned HTTP 400.

This proves the public proxy can upgrade WebSockets, while the polling session is
not stable across the current application workers.

## 1. Capture active configuration (read-only except backup files)

Run on the VPS:

```bash
cd /var/www/pos
stamp="$(date +%Y%m%d-%H%M%S)"
backup_dir="/var/backups/ideaflow/phase01-$stamp"
sudo install -d -m 700 "$backup_dir"
sudo systemctl cat ideahub | sudo tee "$backup_dir/ideahub.service.before.txt" >/dev/null
sudo systemctl show ideahub -p User -p Group -p WorkingDirectory -p EnvironmentFiles -p ExecStart --no-pager | sudo tee "$backup_dir/ideahub.properties.before.txt" >/dev/null
sudo nginx -T 2>&1 | sudo tee "$backup_dir/nginx.before.txt" >/dev/null
sudo cp -a /etc/systemd/system/ideahub.service "$backup_dir/ideahub.service.before" 2>/dev/null || true
echo "CONFIG BACKUP: $backup_dir"
```

Confirm the active Socket.IO proxy is present:

```bash
sudo nginx -T 2>&1 | grep -n -A16 -B2 'location /socket.io/'
```

Required lines include `proxy_http_version 1.1`, `Upgrade`, and `Connection`.

## 2. Create a fresh MySQL recovery point

The command prompts for the `pos_user` database password. It does not print it.

```bash
sudo bash -c 'umask 077; mysqldump --single-transaction --routines --triggers --events --hex-blob -u pos_user -p pos_db > /var/backups/ideaflow/pos_db-phase01-$(date +%Y%m%d-%H%M%S).sql'
```

Find and verify the newest dump:

```bash
db_backup="$(sudo find /var/backups/ideaflow -maxdepth 1 -type f -name 'pos_db-phase01-*.sql' -printf '%T@ %p\n' | sort -nr | head -n1 | cut -d' ' -f2-)"
sudo test -n "$db_backup"
sudo test -s "$db_backup"
echo "BACKUP: $db_backup"
sudo stat -c 'SIZE: %s bytes' "$db_backup"
echo "TABLE DEFINITIONS: $(sudo grep -c '^CREATE TABLE' "$db_backup")"
echo "DATA SECTIONS: $(sudo grep -c '^INSERT INTO' "$db_backup")"
sudo sha256sum "$db_backup"
```

Stop if the path is empty, the file size is zero, or table definitions are zero.

## 3. Install the minimal systemd override

If the new override file has been copied with the codebase, run:

```bash
sudo install -d -m 755 /etc/systemd/system/ideahub.service.d
sudo install -m 644 /var/www/pos/deploy/phase1-socketio-override.conf /etc/systemd/system/ideahub.service.d/phase1-socketio.conf
sudo systemctl daemon-reload
sudo systemd-analyze verify ideahub.service
sudo systemctl show ideahub -p ExecStart --no-pager
```

Before restarting, confirm the displayed command contains all of these values:

- `/var/www/pos/venv/bin/gunicorn`
- `--worker-class eventlet`
- `--workers 1`
- `--bind 127.0.0.1:5000`
- `wsgi:application`

Do not restart if any value is different.

## 4. Restart and verify

```bash
sudo systemctl restart ideahub
sudo systemctl is-active ideahub
sudo systemctl status ideahub --no-pager -l
curl -fsS http://127.0.0.1:5000/health/live
curl -fsS http://127.0.0.1:5000/health/ready
sudo journalctl -u ideahub --since '-5 minutes' --no-pager -n 200
```

Required results:

- Service is `active`.
- Both health responses are successful.
- No import, Redis, R2, database, or worker boot error appears.
- Exactly one Gunicorn worker is started.

Then test in an incognito browser:

1. Sign in through Cloudflare Access and IdeaFlow.
2. Open DevTools Network and filter for `socket.io`.
3. Keep the page open for ten minutes.
4. Confirm one WebSocket connection remains open and there are no HTTP 400 loops.
5. Open menu/inventory in a second authenticated browser and verify one update is
   received after a test mutation.

## 5. Rollback if any gate fails

Removing this override restores the previous ExecStart from the base service:

```bash
sudo rm -f /etc/systemd/system/ideahub.service.d/phase1-socketio.conf
sudo systemctl daemon-reload
sudo systemctl restart ideahub
sudo systemctl status ideahub --no-pager -l
```

This rollback does not restore or modify the database because Phase 1 makes no
database or schema changes.

## Stop point

Stop after the ten-minute Socket.IO verification. Do not begin Phase 2 or run the
application in debug mode. Debug-mode validation is reserved for the controlled
Phase 9 completion workflow and must not expose the production server.
