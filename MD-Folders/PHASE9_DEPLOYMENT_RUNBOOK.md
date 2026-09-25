# Phase 9 — Controlled Production Deployment

This release changes application code and Python dependencies. It must preserve the
production `.env`, MySQL database, R2 bucket, and every local uploaded file. Execute
one section at a time and stop immediately when an expected result is missing.

## Gate A — Prepare the Git release locally

Runtime data was historically tracked by Git. Before creating the release commit,
remove it from Git's index without deleting the files from the computer:

```bash
git rm -r --cached --ignore-unmatch instance static/uploads
git status --short
git check-ignore --no-index instance/ideahub_local.db static/uploads/menu/example.jpg
```

The final command must identify both paths as ignored. Review the staged deletions:
they mean “stop tracking,” not “delete production data.” Do not include `.env`, a
database file, uploaded media, credentials, or logs in the release commit. The owner
performs the commit and push; deployment must use that exact pushed commit.

## Gate B — Capture the production baseline

Run on the VPS before pulling code:

```bash
cd /var/www/pos
git status --short
git rev-parse HEAD
sudo systemctl is-active ideahub
sudo systemctl show ideahub -p ExecStart -p WorkingDirectory --no-pager
curl --fail --show-error http://127.0.0.1:5000/health/live
curl --fail --show-error http://127.0.0.1:5000/health/ready
sudo nginx -t
```

Save the output. Never reset or discard unexpected VPS changes. The existing service
command should still show the Phase 1 Eventlet worker at this point.

## Gate C — Create and verify fresh backups

Create a new MySQL dump and a local-files archive. `mysqldump` prompts for the
`pos_user` password and does not print it.

```bash
sudo install -d -m 700 /var/backups/ideaflow
sudo bash -c 'umask 077; mysqldump --single-transaction --routines --triggers --events --hex-blob -u pos_user -p pos_db > /var/backups/ideaflow/pos_db-phase9-$(date +%Y%m%d-%H%M%S).sql'
sudo tar -C /var/www/pos -czf /var/backups/ideaflow/files-phase9-$(date +%Y%m%d-%H%M%S).tar.gz static/uploads
```

Verify the newest backup files before continuing:

```bash
sudo find /var/backups/ideaflow -maxdepth 1 -type f -name '*-phase9-*' -printf '%TY-%Tm-%Td %TH:%TM  %s bytes  %p\n' | sort
sudo sha256sum /var/backups/ideaflow/pos_db-phase9-*.sql /var/backups/ideaflow/files-phase9-*.tar.gz
sudo grep -c '^CREATE TABLE' /var/backups/ideaflow/pos_db-phase9-*.sql
sudo tar -tzf "$(sudo find /var/backups/ideaflow -maxdepth 1 -type f -name 'files-phase9-*.tar.gz' -printf '%T@ %p\n' | sort -nr | head -n1 | cut -d' ' -f2-)" | wc -l
```

Do not continue if a file is empty, unreadable, or unexpectedly contains no tables
or uploaded files. Copy the database backup off the VPS before the release when
possible.

## Gate D — Preserve dirty runtime paths and pull the exact release

The baseline may show tracked production changes under `instance/` or
`static/uploads/`. Back them up in Gate C, then stash only those historical tracked
paths so Git can apply the commit that stops tracking them:

```bash
cd /var/www/pos
git diff -- config/config.py
git stash push -m phase9-runtime-tracked-files -- instance static/uploads
git status --short
git pull --ff-only origin master
```

If `config/config.py` or another code file is still modified, stop and review it;
do not stash or overwrite it blindly. After the pull, restore the uploaded-files
archive into `/var/www/pos`. Do not pop the historical runtime stash.

## Gate E — Install dependencies and inspect configuration

```bash
cd /var/www/pos
venv/bin/pip install -r requirements.txt -c constraints.txt
venv/bin/pip check
venv/bin/python -c 'import simple_websocket; from config import Config; print("ENVIRONMENT:", Config.FLASK_ENV); print("SOCKET.IO:", Config.SOCKETIO_ASYNC_MODE); print("REDIS:", bool(Config.REDIS_URL)); print("R2:", Config.R2_MEDIA_ENABLED); print("TURNSTILE:", Config.TURNSTILE_ENABLED); print("AUTO MIGRATION:", Config.AUTO_MIGRATE_ON_STARTUP)'
```

Expected: production, threading, Redis/R2/Turnstile true, and auto migration false.
This release contains no reviewed model/schema change, so Phase 9 does not run a
database migration. Never enable automatic migration as a substitute.

## Gate F — Install the threaded service override

```bash
sudo cp -p /etc/systemd/system/ideahub.service.d/override.conf /var/backups/ideaflow/override-before-phase9.conf
sudo cp /var/www/pos/deploy/phase7-threaded-socketio-override.conf /etc/systemd/system/ideahub.service.d/override.conf
sudo systemctl daemon-reload
sudo systemctl show ideahub -p ExecStart --no-pager
```

The effective command must show `gthread`, 50 threads, one worker, and
`127.0.0.1:5000`. It must not show Eventlet. Only then restart:

```bash
sudo systemctl restart ideahub
sudo systemctl is-active ideahub
curl --fail --show-error http://127.0.0.1:5000/health/live
curl --fail --show-error http://127.0.0.1:5000/health/ready
sudo journalctl -u ideahub --since "5 minutes ago" --no-pager
```

## Gate G — Browser and business smoke tests

Use an incognito window plus separate admin and staff sessions:

1. Confirm Cloudflare Access, one-time PIN, application login, and Turnstile.
2. Confirm one stable `/socket.io/` WebSocket and no reconnect loop.
3. Confirm anonymous Socket.IO is rejected and staff receives no admin finance event.
4. Open dashboard, menu, inventory, receivables, payables, analytics, and checkout.
5. Confirm Bootstrap, icons, charts, and R2 images render without CSP console errors.
6. Perform only explicitly recorded test writes: one order/checkout and reversible
   menu, inventory, expense, and receivable checks. Never reuse a real financial
   transaction as test data.
7. Confirm double-click/retry produces one business record and one stock deduction.

Compare database row counts and financial totals with the saved baseline, accounting
only for those intentional test records. Monitor for at least 15 minutes:

```bash
sudo journalctl -u ideahub --since "20 minutes ago" --no-pager | grep -Ei 'traceback|socket.io.*400|worker.*(exit|timeout)|HTTP/[0-9.]+ 5[0-9][0-9]' || echo 'No matching application errors'
```

## Rollback rule

Rollback the code, dependency set, and systemd override together. Do not restore the
database unless a reviewed deployment operation actually changed its schema or data.
Keep the new database and file backups even after a successful deployment.
