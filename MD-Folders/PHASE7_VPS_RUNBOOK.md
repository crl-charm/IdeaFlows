# Phase 7 VPS Runbook — Threaded Socket.IO

This runbook changes only the Python runtime dependencies and the IdeaFlow systemd
command. It does not copy or modify `.env`, MySQL data, uploaded files, or R2 objects.

## Preconditions

- A verified database and uploaded-files backup exists.
- The new release is present in `/var/www/pos`.
- `/var/www/pos/.env` is still the production file.
- `AUTO_MIGRATE_ON_STARTUP=false` remains set.

## Install and inspect before restart

```bash
cd /var/www/pos
venv/bin/pip install -r requirements.txt -c constraints.txt
venv/bin/pip check
venv/bin/python -c 'import simple_websocket; from config import Config; print(Config.SOCKETIO_ASYNC_MODE)'
```

The final command must print `threading`.

Install `deploy/phase7-threaded-socketio-override.conf` as the service drop-in,
then ask systemd to validate the effective command before restarting:

```bash
sudo cp -p /etc/systemd/system/ideahub.service.d/override.conf /var/backups/ideaflow/override-before-phase7.conf
sudo cp deploy/phase7-threaded-socketio-override.conf /etc/systemd/system/ideahub.service.d/override.conf
sudo systemctl daemon-reload
sudo systemctl show ideahub -p ExecStart --no-pager
```

The effective command must contain one `gthread` worker, 50 threads, and a bind to
`127.0.0.1:5000`. It must not contain `eventlet`.

## Restart and gate

```bash
sudo systemctl restart ideahub
sudo systemctl is-active ideahub
curl --fail --show-error http://127.0.0.1:5000/health/live
curl --fail --show-error http://127.0.0.1:5000/health/ready
sudo journalctl -u ideahub --since "5 minutes ago" --no-pager
```

Finally test an authenticated admin browser and staff browser simultaneously. Confirm
the browser uses the WebSocket transport, receives the permitted updates, and does
not repeatedly reconnect. Confirm an anonymous browser cannot establish an
application Socket.IO session.

## Rollback

Restore the saved drop-in and the previous code/dependency release together. Do not
restore only the Eventlet service command after Eventlet has been removed from the
environment.
