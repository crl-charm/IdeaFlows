# Daily Cloudflare R2 Backup Guide

**Updated:** October 30, 2026 (Asia/Manila).

**Current VPS method:** manual backups remain available. The deployed uploader also supports unattended credentials and streamed remote SHA-256 verification. The daily 11:30 p.m. timer needs separate VPS acceptance and activation. The image-aware automation release adds referenced public menu images to the files archive. Telegram alerts remain deferred.

## Latest verified backup — October 27, 2026

This is the backup completed in the guided session. The folder timestamp is its creation time, not a claim that the database snapshot or upload completed at exactly that second.

| Item | Verified result |
| --- | --- |
| Local folder | `/var/backups/ideaflow/daily-20261027-000649-hcWrnO` |
| Private R2 bucket | `ideaflow-backups` |
| R2 prefix | `daily-20261027-000649-hcWrnO/` |
| Database file | `pos_db.sql` — **372,163 bytes** |
| SQL table definitions | **34** |
| SQL INSERT sections | **25**; this is a statement count, not a row count |
| Local files archive | `production-files.tar.gz` — **17,989,876 bytes** |
| Archive entries | **132** |
| Local verification | Both files non-empty; dump-completion marker found; archive readable; SHA-256 recorded |
| R2 verification | Both objects uploaded; remote byte sizes matched the local files |
| Restore test | Not performed as part of this run |
| Application stop / deployment | Neither was part of this backup procedure |

Recorded local SHA-256 checksums:

```text
277152130d1ab4839b447dba6609bb68f39a06fc914776cb32746771753a0232  pos_db.sql
a7d3584ea8944fbe354c0cf929e4cda12c2ce49f2d12590d1189a0f53835e63b  production-files.tar.gz
```

Final output received:

```text
UPLOADED AND VERIFIED: daily-20261027-000649-hcWrnO/pos_db.sql (372163 bytes)
UPLOADED AND VERIFIED: daily-20261027-000649-hcWrnO/production-files.tar.gz (17989876 bytes)
DAILY R2 BACKUP COMPLETE
```

The current helper's `UPLOADED AND VERIFIED` message means it checked the uploaded object's **byte size**. It does not mean it downloaded and compared SHA-256 hashes or tested a restore. The hashes above were calculated locally.

## Verified manual procedure — use a new folder for each backup

Run the command blocks below **inside the VPS SSH session**, one step at a time. Do not run them in the Windows terminal before connecting to the VPS. Copy command blocks, not the example output.

This procedure uses the working installation paths:

- Application: `/var/www/pos`
- Python environment: `/var/www/pos/venv/bin/python`
- Database: `pos_db`
- Backup parent directory: `/var/backups/ideaflow`
- Uploader: `/var/www/pos/scripts/upload_backup_to_r2.py`

MySQL, the existing Python/boto3 installation, and the private R2 bucket must be available. No package install, Git pull, migration, or application restart is needed for the normal backup steps.

### 1. Create a fresh private directory and print its path

```bash
backup_dir="$(sudo mktemp -d "/var/backups/ideaflow/daily-$(TZ=Asia/Manila date +%Y%m%d-%H%M%S)-XXXXXX")" && printf 'BACKUP DIRECTORY: %s\n' "$backup_dir"
```

This must print `BACKUP DIRECTORY:` followed by a new absolute path. Keep the SSH session open: the later commands use its `backup_dir` variable.

If no path appears, do not assume the step succeeded or continue with an empty variable. Inspect today's directories, substituting the current Manila date for `YYYYMMDD`:

```bash
sudo find /var/backups/ideaflow -maxdepth 1 -type d -name 'daily-YYYYMMDD-*' -print
```

Do not automatically reuse whichever old folder appears. Check which attempt it belongs to before continuing. The dump/archive commands below refuse to overwrite existing files.

If the backup parent directory is missing, stop and check the installation before continuing; that is not an R2 credential problem.

### 2. Save the MySQL database

The following is the successful database command used in the session, with the directory passed through the checked variable:

```bash
sudo bash -c 'set -euo pipefail; umask 077; set -o noclobber; mysqldump --single-transaction --quick --routines --triggers --events --hex-blob --no-tablespaces pos_db > "$1/pos_db.sql"; echo "DATABASE BACKUP COMPLETE"' _ "${backup_dir:?Create or set backup_dir first}"
```

Proceed only after **`DATABASE BACKUP COMPLETE`** appears with no error. This uses the working local MySQL authentication through `sudo`; it does not ask for an R2 key.

The private file is created with restrictive permissions from the start. `noclobber` prevents replacing an existing `pos_db.sql` at that path. If the dump fails, keep the partial attempt for review and use a fresh directory for a new complete attempt.

For InnoDB tables, `--single-transaction` takes a consistent database snapshot while the application continues running. Do not overlap schema migrations or table-changing maintenance with the dump. This does not promise consistent online copies of nontransactional tables or a single atomic database-and-media snapshot. [MySQL backup option reference](https://dev.mysql.com/doc/refman/8.4/en/mysqldump.html#option_mysqldump_single-transaction).

### 3. Archive uploaded files and site images

```bash
sudo bash -c 'set -euo pipefail; umask 077; set -o noclobber; tar -C /var/www/pos -czf - static/uploads static/images > "$1/production-files.tar.gz"; echo "FILES ARCHIVE COMPLETE"' _ "${backup_dir:?Create or set backup_dir first}"
```

Proceed only after **`FILES ARCHIVE COMPLETE`** appears with no warning or error. A `file changed as we read it` warning is not a clean result; investigate/retry rather than silently calling that archive verified.

This manual tar command covers local uploads/images. Along with the database dump, it is not a whole-server backup and does not include `.env`, SSH keys, MySQL system accounts or separate R2 media objects. The image-aware automated runner additionally copies referenced menu images from `media.idea-flows.online` into `external-media/` inside its files archive. That extra capture does not happen merely by running this manual tar command. Keep server/configuration recovery information separately and protect credentials.

### 4. Verify the local backup before uploading

```bash
sudo bash -c 'set -euo pipefail; test -s "$1/pos_db.sql"; test -s "$1/production-files.tar.gz"; grep -q "^-- Dump completed" "$1/pos_db.sql"; tar -tzf "$1/production-files.tar.gz" >/dev/null; stat -c "%n: %s bytes" "$1/pos_db.sql" "$1/production-files.tar.gz"; printf "TABLE DEFINITIONS: "; grep -c "^CREATE TABLE" "$1/pos_db.sql"; printf "DATA SECTIONS: "; grep -c "^INSERT INTO" "$1/pos_db.sql"; printf "ARCHIVE ENTRIES: "; tar -tzf "$1/production-files.tar.gz" | wc -l; sha256sum "$1/pos_db.sql" "$1/production-files.tar.gz"; echo "LOCAL BACKUP VERIFIED"' _ "${backup_dir:?Create or set backup_dir first}"
```

Proceed only when **`LOCAL BACKUP VERIFIED`** appears. Record the output without sharing SQL contents or customer records.

Today's observed counts were 34 table definitions, 25 INSERT sections, and 132 archive entries. Future backups may have different counts and sizes. These are diagnostics, not permanently fixed expected values. In the current populated production database, zero table definitions or no INSERT sections needs investigation; the command stops on those zero-match checks.

### 5. Upload the verified files to private R2

```bash
sudo /var/www/pos/venv/bin/python /var/www/pos/scripts/upload_backup_to_r2.py "${backup_dir:?Create or set backup_dir first}"
```

Enter credentials **only in the VPS terminal**:

| Prompt | What to enter |
| --- | --- |
| `Paste S3 endpoint:` | Your account's R2 S3 endpoint, in the form `https://<ACCOUNT_ID>.r2.cloudflarestorage.com` |
| `Paste Access Key ID:` | The full R2 **Access Key ID**, not the token name, Account ID, or account password |
| `Paste Secret Access Key:` | The matching **Secret Access Key** from the same saved R2 credential pair |

The standard Access Key ID used for this backup is **32 characters**. The failed attempt received only 22 characters; retrying with the correct full pair succeeded. The Access Key ID and Secret Access Key inputs are hidden by the helper, so blank-looking terminal input is normal.

If `sudo` first asks for authentication, that is the VPS authentication step, separate from the later R2 prompts. Reaching the R2 prompts means `sudo` already allowed the script to start.

Use the saved backup-bucket credential pair with **Object Read & Write** access scoped to `ideaflow-backups`. Keep the bucket private. Do not put actual credentials in this guide, Git, chat, or shell command arguments. If the saved secret has been lost, create a new bucket-scoped pair through R2's API-token management rather than guessing values or changing unrelated production/media credentials. [Cloudflare R2 authentication](https://developers.cloudflare.com/r2/api/tokens/).

### 6. Confirm completion

The uploader must print both `UPLOADED AND VERIFIED` lines and **`DAILY R2 BACKUP COMPLETE`**. Compare their byte sizes with the local `stat` results from step 4.

One successful object followed by an error is an incomplete upload. Keep the verified local files and retry step 5 after correcting the cause.

You can also open Cloudflare → **R2 object storage** → **ideaflow-backups** → **Objects**, find the folder prefix printed for this run, and check that its `pos_db.sql` and `production-files.tar.gz` objects are present with the expected sizes. Use the current run's prefix, not a hard-coded older date.

A downloaded checksum comparison or an isolated MySQL restore is additional verification. Neither is implied by the current size-check message. Never test a restore by importing over the live `pos_db` database.

The updated uploader prints `SHA-256 matched`, reads remote file bytes back, and publishes `manifest.json` last. Its normal manual prompts stay available. That stronger verification still does not replace an isolated restore test; historical backups made with the older helper were checked by size only.

### 7. Record the result and retain the local copy

Record the date, prefix, byte sizes, local SHA-256 values, diagnostic counts, final upload status, and whether any download/restore test was performed. Do not record secret values or customer rows.

The completed local backup remains in `/var/backups/ideaflow/`. No deletion or retention cleanup is part of this procedure. Agree a retention policy separately and do not remove the only known-good backup to make space.

## Resuming an interrupted SSH session or retrying an upload

If you reconnect, the shell variable will be gone. Set it to the **existing verified backup directory** before repeating verification/upload only. For the completed October 27 run, that is:

```bash
backup_dir='/var/backups/ideaflow/daily-20261027-000649-hcWrnO'
```

This assignment does not create or overwrite files. For an upload retry, use steps 4–6 with that directory. For a new database/files backup, return to step 1 and create a new directory; do not rerun dump/archive into the completed set.

## Troubleshooting based on observed behavior

| Symptom | Meaning and next action |
| --- | --- |
| No folder path appears | Verify the command ran and inspect the current date's directories before continuing. |
| `Create or set backup_dir first` | The variable is missing/empty, often after reconnecting. Set the intended verified path for a retry, or create a new folder for a new backup. |
| `cannot overwrite existing file` | The file already exists. The guard is working. Resume verification/upload of a known verified set, or create a new folder for a fresh full attempt. |
| `sudo: Authentication failed` | VPS authentication failed on that attempt; this is separate from R2 credentials. Do not paste the password into chat. |
| MySQL `Access denied` | The dump failed. Check local MySQL authentication/permissions before proceeding. Do not upload the partial dump as a completed backup. |
| `tar: Cannot stat`, changing-file warning, or archive read failure | The archive is not accepted as verified. Check paths and concurrent changes, then make a clean new attempt. |
| Filesystem full | Stop, inspect available space, and preserve known-good backups. |
| `Credential access key has length 22, should be 32` | Wrong/incomplete Access Key ID. Re-enter the full saved R2 Access Key ID and its matching secret; reuse the already verified local backup for the upload retry. |
| R2 `AccessDenied` or signature error | Check the matching key pair, endpoint/account, and bucket scope. Do not rotate unrelated working credentials without identifying the cause. |
| One upload-success line followed by an error | The pair is not complete in R2. Retain both local files and retry the upload after correcting the cause. |
| `UPLOADED AND VERIFIED` for both files plus final completion line | Upload and remote byte-size checks passed. This does not itself prove a downloaded hash comparison or successful restore. |
| Downloaded SHA-256 differs from the recorded local hash | Do not accept that downloaded copy as matching; check the exact prefix/file and investigate before relying on it. |

## Automation remains a separate task

The deployed helper used here prompts interactively for R2 credentials. Merely writing `/etc/ideaflow/backup.env` does not make this current script unattended or create a schedule.

The **11:30 p.m. Asia/Manila** schedule, unattended credentials, and stronger upload verification are implemented locally as described in [Daily R2 Backup Automation](DAILY_R2_BACKUP_AUTOMATION.md). Normal runs start and are dated on the same business day. Follow the [VPS setup and acceptance checks](DAILY_R2_BACKUP_SETUP.md) before enabling it; it is not active just because the files exist. Telegram alerts and independent missed-run monitoring are deferred.

Related operational references: [Owner Maintenance Runbook](OWNER_MAINTENANCE_RUNBOOK.md) and [VPS Deployment Guide](VPS_DEPLOY_GUIDE.md). Use this guide for the verified manual backup flow; use deployment instructions only when a deployment is separately requested.
