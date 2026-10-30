# Daily R2 backup — VPS installation and checks

Updated: October 30, 2026. **Local implementation only; these VPS steps have not been run.**

Schedule: **11:30 p.m. Asia/Manila every day**. No application shutdown, automatic deletion, Telegram alerts, or independent missed-run monitor is included. No database migration is needed for this feature.

## 1. Preflight before installation

Deploy the reviewed backup files to `/var/www/pos` through the usual release procedure first. Check for existing backup timers and cron jobs; do not create duplicate schedules. Confirm time synchronization, root's unattended MySQL socket access, and that no migration or schema change overlaps the backup window.

Inventory media storage. This version includes all `pos_db` data plus local `static/uploads` and `static/images`. It does **not** copy images from a separate R2 media bucket, server configuration, or credentials. If external media is in use, arrange its separate versioned recovery before describing the backup as complete.

Review the destination's private permissions and these local directories before changing their modes:

```bash
sudo install -d -o root -g root -m 700 /etc/ideaflow /var/backups/ideaflow
```

Create the credential file **only if it does not already exist**:

```bash
sudo bash -c 'set -eu; if [ ! -e /etc/ideaflow/backup.env ]; then install -o root -g root -m 600 /var/www/pos/deploy/backup.env.example /etc/ideaflow/backup.env; fi'
sudo nano /etc/ideaflow/backup.env
```

Enter the R2 S3 endpoint, 32-character Access Key ID, and matching Secret Access Key directly in the editor. Use the three `IDEAFLOW_BACKUP_R2_*` names in the template and simple unquoted values. Use a credential scoped to the **private `ideaflow-backups` bucket**, with read/write object access. Never paste values into chat, shell commands, or Git.

Confirm root ownership and mode 600 without displaying its contents:

```bash
sudo stat -c '%U %a %n' /etc/ideaflow/backup.env
```

Run local prerequisites. It creates no database dump and makes no R2 requests; remote credentials/access are tested by the real upload:

```bash
sudo bash /var/www/pos/scripts/run_daily_backup.sh --preflight
```

Failures must be fixed before proceeding. This includes non-InnoDB tables, missing media directories, insufficient disk space, or a Git revision that cannot be recorded. Existing backups are preserved.

## 2. Install the reviewed units, without enabling the timer

```bash
sudo install -o root -g root -m 644 /var/www/pos/deploy/ideaflow-daily-backup.service /etc/systemd/system/ideaflow-daily-backup.service
sudo install -o root -g root -m 644 /var/www/pos/deploy/ideaflow-daily-backup.timer /etc/systemd/system/ideaflow-daily-backup.timer
sudo systemd-analyze verify /etc/systemd/system/ideaflow-daily-backup.service /etc/systemd/system/ideaflow-daily-backup.timer
systemd-analyze calendar '*-*-* 23:30:00 Asia/Manila'
sudo systemctl daemon-reload
```

The timer templates do not start or stop `ideahub`. The backup unit runs for at most 30 minutes. It is normally inactive after a successful run.

## 3. Controlled backup and isolated restore

Run the service once before enabling its schedule:

```bash
sudo systemctl start ideaflow-daily-backup.service
sudo systemctl show ideaflow-daily-backup.service -p Result -p ExecMainStatus
sudo journalctl -u ideaflow-daily-backup.service -n 60 --no-pager
sudo cat /var/backups/ideaflow/last-success.json
```

Require `Result=success`, `ExecMainStatus=0`, and a newly verified prefix. The unit associates the run with the latest due 11:30 p.m. schedule, so a daytime manual service test can refer to yesterday's scheduled date. Its folder and snapshot timestamps still reflect the real backup time.

In private R2, require both files and `manifest.json` in that prefix. The uploader has streamed the remote bytes back and compared their SHA-256 hashes. The manifest records the source revision, scope, scheduled date, actual timestamps, file hashes/sizes, and validation counts.

Download the set to a separate private restore-test directory. Match the downloaded hashes/sizes to the manifest, import into a **new isolated database**, and extract the archive into a **new isolated directory**. Check representative customer, checkout, expense, debt, inventory, and cash-history records plus media. Never restore over live `pos_db` or the live `static` directories as a test.

Also test a controlled failure without modifying production data, using a temporary test environment file with missing credentials and a separate backup root. Require a failure exit/result, a sanitized failed attempt, and no change to the real last-success record. No phone notification will arrive in this version.

## 4. Enable only after acceptance checks

```bash
sudo systemctl enable --now ideaflow-daily-backup.timer
sudo systemctl list-timers --all ideaflow-daily-backup.timer
```

Confirm the next run corresponds to **11:30 p.m. Philippine time** even if the server lists UTC. `Persistent=true` can start an immediate catch-up run if a scheduled time was missed; it does not recreate historical snapshots. Inspect the first actual scheduled run afterward using the checks above. A successful manual run alone does not verify scheduling.

## 5. Failure, retry, and pausing

Inspect both systemd and private status:

```bash
sudo systemctl show ideaflow-daily-backup.service -p Result -p ExecMainStatus
sudo journalctl -u ideaflow-daily-backup.service -n 80 --no-pager
sudo cat /var/backups/ideaflow/last-attempt.json
sudo cat /var/backups/ideaflow/last-success.json
```

If the run's `local_complete` is true and only upload/verification failed, retry its saved folder using the actual `auto-daily-*` path from the status:

```bash
sudo bash /var/www/pos/scripts/run_daily_backup.sh --retry-upload /var/backups/ideaflow/auto-daily-YYYYMMDD-HHMMSS-UNIQUE
```

The retry revalidates the saved files and their original hashes, acquires the same lock, and does not dump the current database again. An incomplete local dump/archive requires a new run instead. The service's 30-minute timeout applies to service runs; direct manual commands remain under operator supervision.

The uploader has bounded retries, but the timer does not automatically retry an exhausted failed job before the next day. Failed and successful backups are retained; monitor space manually until retention is agreed.

To pause future scheduled backups:

```bash
sudo systemctl disable --now ideaflow-daily-backup.timer
```

This leaves the business service, existing backups, and any already running backup intact. A VPS that is offline cannot log or notify at that time; no independent monitor is configured.
