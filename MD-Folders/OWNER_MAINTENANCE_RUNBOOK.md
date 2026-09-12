# IdeaFlow Owner Maintenance Runbook

This is the private operational checklist for maintaining IdeaFlow safely. It
contains no credentials and is safe to keep in the repository. Never paste
passwords, access keys, database URLs, backup contents, or the real `.env` file
into this document, Git, screenshots, or support chats.

Last reviewed: 2026-09-12

## 1. Current production map

| Component | Current location or purpose |
| --- | --- |
| Public site | `https://idea-flows.online` |
| Media domain | `https://media.idea-flows.online` |
| VPS application directory | `/var/www/pos` |
| VPS virtual environment | `/var/www/pos/venv` |
| VPS environment file | `/var/www/pos/.env` |
| Application service | `ideahub.service` |
| Web proxy | Nginx |
| Primary data | MySQL; this is the source of truth |
| Fast temporary data | Redis on `127.0.0.1`; cache, rate limits, and Socket.IO |
| Media storage | Cloudflare R2 bucket `ideaflow-media` |
| Media object prefix | `menu/` |
| Backup storage | Cloudflare R2 bucket `ideaflow-backups` plus Hostinger weekly backup |
| Admin edge protection | Cloudflare Access with an allowed-email policy |

Important: creating an R2 bucket does not automatically back up MySQL. A backup
only exists when a scheduled job successfully creates and uploads a database
dump. Confirm this by checking for recent, non-empty objects in the backup
bucket.

## 2. Rules that prevent accidents

- [ ] Make or confirm a recoverable database backup before every deployment,
      migration, bulk import, or destructive data operation.
- [ ] Never commit `.env`, database dumps, R2 keys, passwords, or private keys.
- [ ] Never show the contents of `/var/www/pos/.env` on screen or in a screenshot.
- [ ] Never run `redis-cli FLUSHALL`, `DROP DATABASE`, `rm -rf`, or
      `git reset --hard` during routine maintenance.
- [ ] Never update every Python package directly on production. Update the
      repository lock/list, test locally, back up, and deploy the tested version.
- [ ] Never change the firewall or SSH rules without keeping the current SSH
      session open and confirming a second session can connect.
- [ ] Do not treat Redis as permanent storage. Losing Redis should affect cache,
      rate-limit state, or live messages—not MySQL business records.
- [ ] Do not delete old backups until a newer backup has been verified and a
      restore test has succeeded.
- [ ] Record every production change in the maintenance log at the end of this file.

## 3. Quick health check

Run this after a deployment or whenever the site feels slow:

```bash
sudo systemctl status ideahub --no-pager
sudo systemctl status nginx --no-pager
sudo systemctl status mysql --no-pager
sudo systemctl status redis-server --no-pager
curl --fail --silent --show-error http://127.0.0.1:5000/health/live
curl --fail --silent --show-error http://127.0.0.1:5000/health/ready
df -h
free -h
```

Expected:

- `ideahub`, Nginx, MySQL, and Redis are active.
- `/health/live` succeeds.
- `/health/ready` succeeds and can reach required dependencies.
- The main disk stays below 80% usage.
- The server has available memory and is not continuously swapping.

Public checks:

- [ ] `https://idea-flows.online` loads without Cloudflare Access.
- [ ] `https://idea-flows.online/admin` shows Cloudflare Access in a private
      browser window before the IdeaFlow login.
- [ ] `https://media.idea-flows.online/test.jpg` or a known menu image loads.
- [ ] Login, check-in, ordering, checkout, expense logging, and image display
      work without browser console errors.

## 4. Daily checks (about 2 minutes)

- [ ] Open the public site and complete one normal page load.
- [ ] Confirm staff can log in and perform the main workflow.
- [ ] Check the newest menu images display correctly.
- [ ] Look for an unusual increase in failed logins, `500`, `502`, or `503` errors.
- [ ] Confirm there is no current Cloudflare, Hostinger, or R2 incident.
- [ ] If a backup ran today, confirm it reports success; do not assume success
      merely because a timer exists.

Useful log commands:

```bash
sudo journalctl -u ideahub --since today --priority warning --no-pager
sudo tail -n 100 /var/log/nginx/error.log
sudo journalctl -u redis-server --since today --priority warning --no-pager
sudo journalctl -u mysql --since today --priority warning --no-pager
```

## 5. Weekly checks (about 10 minutes)

- [ ] Confirm the latest Hostinger weekly backup completed and note its date.
- [ ] Open `ideaflow-backups` and confirm the newest database backup object is
      recent, non-zero in size, and located under the intended prefix.
- [ ] Confirm recent uploaded images exist in `ideaflow-media/menu/` and load
      through `media.idea-flows.online`.
- [ ] Review Cloudflare Access login events for unexpected emails or countries.
- [ ] Review repeated Flask login failures and account lockouts.
- [ ] Check disk space, memory, CPU load, and service restart counts.
- [ ] Check that Redis responds with `PONG`.
- [ ] Verify the backup job/timer itself is active.

```bash
redis-cli ping
redis-cli INFO memory
sudo systemctl list-timers --all
sudo systemctl show ideahub -p ActiveState -p SubState -p NRestarts
sudo du -sh /var/log/ideahub /var/log/nginx 2>/dev/null
```

If the R2 database backup is implemented with cron rather than a systemd timer,
also review it with `sudo crontab -l` and inspect its latest log. Do not edit a
schedule until its command and destination are understood.

## 6. Monthly owner checklist

### Application and user accounts

- [ ] Review admin and staff accounts; disable people who no longer need access.
- [ ] Confirm every administrator has a unique account and no credentials are shared.
- [ ] Test the account lockout with a dedicated test account, not the only admin.
- [ ] Test session expiry and logout on a private browser window.
- [ ] Test one create/update action in each important area: order, checkout,
      inventory, menu, expense, receivable, payable, and staff management.
- [ ] Confirm slow submissions show a busy state and cannot create duplicates.
- [ ] Confirm validation errors are understandable and do not expose tracebacks.

### Cloudflare DNS, TLS, and Access

- [ ] Confirm the apex and required web DNS records remain orange-cloud **Proxied**.
- [ ] Confirm `media.idea-flows.online` is still attached to `ideaflow-media`.
- [ ] Test `/admin` in an incognito/private window and verify Cloudflare Access
      appears before the Flask login.
- [ ] If Turnstile is enabled, confirm it appears on both `/` and `/login`, a
      login without a valid token is rejected, and Turnstile Analytics records
      server-side validations.
- [ ] Confirm the Access Allow policy contains only the intended email addresses.
- [ ] Remove former users immediately; do not wait for the monthly review.
- [ ] Confirm the Access application session duration is still 24 hours or less.
- [ ] Confirm there is no broad Bypass or Everyone rule.
- [ ] Review the following protected destinations:

```text
admin*
api/admin*
api/register
api/users
analytics*
api/analytics*
finance*
api/finance*
management*
api/management*
api/daily-sales
api/sales-summary
api/sales-compare
```

- [ ] Confirm `/`, `/login`, `/api/login`, customer ordering, and staff routes
      are not accidentally included in the Access application.
- [ ] Review Cloudflare Security Events for new attack patterns or false positives.
- [ ] Verify TLS mode and certificate health. If Certbot remains in use, run:

```bash
sudo certbot renew --dry-run
```

### VPS and operating system

- [ ] Review available Ubuntu security updates; schedule a maintenance window
      before installing anything requiring a restart.
- [ ] Confirm UFW is active, SSH remains reachable, and port 5000 is not public.
- [ ] Confirm only expected services are listening.
- [ ] Review failed SSH attempts and successful root logins.
- [ ] Check system clock synchronization.

```bash
sudo apt update
apt list --upgradable
sudo ufw status verbose
sudo ss -lntup
sudo journalctl -u ssh --since "30 days ago" --no-pager
timedatectl status
```

Do not run `apt upgrade` automatically after this check. Read the package list,
confirm backups, and choose a maintenance window first.

### MySQL and data integrity

- [ ] Confirm MySQL is active and the application readiness check succeeds.
- [ ] Check database size and free VPS disk space.
- [ ] Review MySQL warnings, aborted connections, and slow queries.
- [ ] Confirm the automated dump excludes no required tables.
- [ ] Verify the most recent dump is readable with a non-destructive listing or
      restore it into a separate temporary test database.
- [ ] Never restore over production as a test.

Example read-only checks after entering the MySQL client securely:

```sql
SHOW DATABASES;
SHOW TABLES;
SHOW TABLE STATUS;
```

Do not place a database password directly in a shell command because it may be
saved in shell history or visible to other processes.

### Redis

- [ ] Confirm `redis-cli ping` returns `PONG`.
- [ ] Check memory use, evictions, rejected connections, and recent errors.
- [ ] Confirm Redis listens only on localhost or a trusted private network.
- [ ] Confirm `REDIS_URL` is configured in production and the application is not
      silently falling back to per-process memory.
- [ ] Restart Redis only in a maintenance window; active Socket.IO clients and
      rate-limit/cache state may be interrupted.

```bash
redis-cli INFO memory
redis-cli INFO stats
sudo ss -lntp | grep 6379
sudo journalctl -u redis-server --since "30 days ago" --priority warning --no-pager
```

### R2 media and backups

- [ ] Upload a small test menu image through IdeaFlow and confirm it appears at
      `media.idea-flows.online/menu/...`.
- [ ] Update or delete a dedicated test item and confirm the application behaves
      correctly; never test deletion on a client's real menu item.
- [ ] Check R2 storage and request metrics for unexpected spikes.
- [ ] Confirm `ideaflow-media` has no expiration lifecycle rule.
- [ ] Confirm the backup bucket retention rule matches the intended retention.
- [ ] Confirm R2 API tokens have access only to the required buckets.
- [ ] Rotate an R2 token immediately if it was exposed; update `.env`, restart the
      app or backup job, verify success, and revoke the old token.

### Logs and monitoring

- [ ] Review application, security, Nginx, MySQL, Redis, Cloudflare, and backup logs.
- [ ] Confirm log rotation works and the disk is not filling with old logs.
- [ ] Review uptime, response time, `5xx` rate, and application restart alerts.
- [ ] Confirm monitoring alerts reach an email or phone that is actively checked.
- [ ] Investigate repeated failures; do not simply silence an alert.

```bash
sudo journalctl --disk-usage
sudo logrotate --debug /etc/logrotate.conf
sudo journalctl -u ideahub --since "30 days ago" --priority warning --no-pager
```

### Dependencies and source code

- [ ] Run tests and import validation locally on the exact commit intended for production.
- [ ] Scan Python dependencies for known vulnerabilities.
- [ ] Review outdated packages, but upgrade deliberately rather than all at once.
- [ ] Confirm `.env`, dumps, uploads, and local databases remain ignored by Git.
- [ ] Review repository changes before committing.

Local Windows commands:

```powershell
python scripts/validate_imports.py
python -m pytest -q tests
python -m pip install pip-audit
python -m pip_audit -r requirements.txt
python -m pip list --outdated
git status --short
git diff --check
git check-ignore .env
```

Installing `pip-audit` is a development/maintenance tool action. It does not need
to be installed into the production application's runtime unless intentionally
included in the deployment process.

## 7. Quarterly checks

- [ ] Perform a real restore drill into an isolated test database and record the result.
- [ ] Restore a sample R2 backup object and verify its checksum/readability.
- [ ] Review and rotate credentials that are due under the chosen policy.
- [ ] Confirm emergency contact information for Hostinger, Cloudflare, and the owner.
- [ ] Review firewall, Cloudflare Access, R2 token, database-user, and SSH permissions.
- [ ] Review the privacy and retention requirements for customer and employee data.
- [ ] Test a full VPS reboot during a planned window and confirm all services return.
- [ ] Review capacity trends: disk, RAM, CPU, MySQL connections, Redis memory,
      request latency, R2 usage, and backup growth.

## 8. Annual checks

- [ ] Confirm domain renewal and billing contacts are current.
- [ ] Confirm Hostinger service renewal and Cloudflare account recovery methods.
- [ ] Review disaster recovery targets: acceptable data loss and recovery time.
- [ ] Conduct a full disaster-recovery exercise on a separate host or test environment.
- [ ] Review all administrators, SSH keys, API tokens, recovery codes, and third-party apps.
- [ ] Review whether the current VPS size and architecture still fit actual usage.

## 9. Safe deployment procedure

Use a planned low-traffic window. The current production paths are
`/var/www/pos`, `/var/www/pos/venv`, and service `ideahub`.

### Before deployment

- [ ] Run the local tests and dependency scan.
- [ ] Review `git diff` and confirm no `.env`, database, or secret is included.
- [ ] Confirm a fresh database backup exists outside the VPS.
- [ ] Record the currently deployed Git commit.
- [ ] Read migration and dependency changes before applying them.

Read-only production checks:

```bash
cd /var/www/pos
git status --short
git rev-parse HEAD
sudo systemctl status ideahub --no-pager
```

If `git status` shows unexpected production changes, stop and investigate. Do not
discard them with reset or checkout.

### Deploy

Use the repository's approved deployment method. A typical update is:

```bash
cd /var/www/pos
git pull --ff-only
./venv/bin/pip install -r requirements.txt
sudo systemctl restart ideahub
```

Run migrations exactly once if the release requires them. Do not run concurrent
migrations from multiple application workers.

### Verify immediately

```bash
sudo systemctl status ideahub --no-pager
sudo journalctl -u ideahub -n 100 --no-pager
curl --fail http://127.0.0.1:5000/health/live
curl --fail http://127.0.0.1:5000/health/ready
```

Then manually test login, admin Access, order creation, checkout, one safe write,
and one R2-hosted menu image. Monitor errors and latency for at least 15 minutes.

## 10. Backup and restore policy

Use at least two independent backup locations. The Hostinger weekly backup and
the R2 database backup should not depend on the same VPS disk.

For every backup, record:

- Creation time in the correct timezone.
- Source database and application version/commit.
- File size and preferably a SHA-256 checksum.
- Encryption status.
- Upload destination and retention/expiry date.
- Job result and restore-test result.

Recommended minimum operating target:

- Daily encrypted MySQL dump to `ideaflow-backups`.
- Hostinger weekly VPS backup as an independent safety net.
- At least 30 days of daily database backups, adjusted for legal/business needs.
- Quarterly restore drill into an isolated database.

Treat a backup as **unverified** until it has been restored successfully. R2 media
objects are production files, not automatically historical backups; versioning or
a separate media backup policy is required if recovery of deleted media is needed.

## 11. Incident response

### Website is down or returns 502/503

1. Do not repeatedly restart services before collecting evidence.
2. Check Cloudflare status, DNS, VPS health, disk, memory, and service status.
3. Save the relevant timestamps and logs.
4. Restart only the failed component after identifying the likely cause.
5. Test health endpoints and the public workflow.
6. Record the incident and prevention action.

```bash
date -Is
df -h
free -h
sudo systemctl status ideahub nginx mysql redis-server --no-pager
sudo journalctl -u ideahub -n 200 --no-pager
sudo tail -n 200 /var/log/nginx/error.log
```

### Suspected credential leak

1. Identify the exact credential without posting it publicly.
2. Revoke or rotate it at the provider first.
3. Update `/var/www/pos/.env` securely.
4. Apply owner-only permissions and restart the affected service.
5. Test the application or backup job.
6. Review access logs from before and after the exposure.
7. If a secret entered Git history, rotating it is mandatory; deleting one file
   from the latest commit is not sufficient.

```bash
sudo chown root:root /var/www/pos/.env
sudo chmod 600 /var/www/pos/.env
sudo systemctl restart ideahub
```

### Suspected account compromise

1. Disable the affected IdeaFlow and Cloudflare Access identity.
2. End/revoke active sessions where supported.
3. Reset the password and require a unique strong replacement.
4. Review admin changes, exports, user creation, and data modifications.
5. Preserve logs and timestamps before cleanup.

### Data loss or corruption

1. Stop the action causing further writes; do not immediately overwrite production.
2. Preserve the current database and logs for investigation.
3. Identify the last known-good time and matching application commit.
4. Restore the selected backup into an isolated database first.
5. Validate counts and key business records with the owner.
6. Plan the production restore, downtime, and rollback before executing it.

## 12. One-time hardening backlog

These are improvements, not monthly commands. Plan and test them separately:

- [ ] Run `ideahub.service` as a dedicated unprivileged user instead of `root`.
- [ ] Add Cloudflare Tunnel or origin firewall restrictions so the VPS origin
      cannot bypass Cloudflare Access through its direct IP.
- [ ] Create the production Cloudflare Turnstile widget, configure its two keys
      in the VPS `.env`, deploy the prepared server-side integration, and verify
      both successful and rejected logins.
- [ ] Add alerting for uptime, `5xx` rate, latency, disk, memory, MySQL, Redis,
      service restarts, backup failure, and certificate expiry.
- [ ] Automate encrypted MySQL backups to `ideaflow-backups` if only the bucket
      exists today, and alert when a run or upload fails.
- [ ] Store backup encryption material separately from the backups and VPS.
- [ ] Document and test a rollback that does not discard unknown production changes.

## 13. Maintenance log template

Copy this block for every maintenance session:

```text
Date/time and timezone:
Operator:
Reason/ticket:
Pre-change backup object and timestamp:
Pre-change Git commit:
Checks performed:
Changes made:
Post-change Git commit:
Health-check results:
Manual workflow tested:
Errors observed:
Rollback performed or available:
Follow-up owner and due date:
```

## 14. Planned data-protection implementation

This plan must be completed before the next production code deployment:

1. Identify whether `/var/www/pos` uses MySQL or SQLite without printing credentials.
2. Create and verify a manual pre-change database backup.
3. If production uses SQLite, migrate it to MySQL before changing Git tracking.
4. Remove runtime database files from Git tracking without deleting live data.
5. Create encrypted MySQL dumps and upload them automatically to
   `ideaflow-backups` using a systemd service and timer.
6. Retain hourly backups for 7 days and daily backups for 30 days, subject to
   confirmed R2 lifecycle and bucket-lock rules.
7. Keep the independent Hostinger weekly VPS backup enabled.
8. Restore one backup into an isolated test database and compare important
   record counts before declaring the backup system ready.
9. Only after recovery is proven, create the read-only teacher database viewer
   behind Cloudflare Tunnel and its own Access policy.
10. Deploy the pending R2 media and Turnstile code with `.env` and database files
    excluded, then verify every critical POS workflow.
