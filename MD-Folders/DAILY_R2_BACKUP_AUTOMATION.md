# Daily 11:30 p.m. backup to Cloudflare R2 — revised implementation plan

Updated: October 30, 2026.

**Status: source implementation complete; VPS acceptance is in progress.** On October 30, the private credential file and the base preflight checks passed. The owner then requested copies of the 29 externally stored menu images; this source release adds that coverage. Install/test the image-aware version and complete the restore/failure checks before enabling the timer. **Telegram alerts and independent missed-run monitoring remain deferred.**

Installation and operational commands: [VPS setup and acceptance guide](DAILY_R2_BACKUP_SETUP.md). No database migration is needed for these scripts.

## 1. What the owner will get

Every day at **11:30 p.m. Philippine time, Asia/Manila**, the VPS starts a backup, uploads it to the private **`ideaflow-backups`** R2 bucket, and records whether it succeeded. No open laptop, signed-in browser, or nightly password entry is needed after the one-time setup.

The confirmed business hours are **8:00 a.m. to 8:00 p.m.** The backup starts three and a half hours after closing. For this version, failures appear in the systemd journal and private local status files. **There are no phone/email/Telegram notifications.**

Example: the October 30 run starts at 11:30 p.m. on October 30, so its normal backup folder is dated October 30. It takes a full backup, including older records, through the actual snapshot time; it is not an export of only that day's transactions. Changes after the snapshot belong to a later backup. An upload that finishes after midnight still keeps its original run folder and actual timestamps.

The intended daily operation keeps IdeaFlow available. Confirm transactional database tables and the file-copy conditions before promising an online backup; see section 5.

## 2. What is verified already, and what is still unknown

| Item | Current evidence |
| --- | --- |
| Manual R2 backup | Successful uploads have been reported in this conversation. |
| Repository uploader | Preserves manual prompts; supports `--non-interactive`, bounded retries, streamed remote SHA-256 verification, and a completion manifest. |
| Existing automation document | Was a draft, not evidence of an installed job. The user now selected 23:30 instead of the previous midnight plan. |
| Existing VPS timer or cron job | October 30 checks found no IdeaFlow backup timer and no matching cron entry. The named timer was not installed at the start of acceptance. |
| VPS prerequisites | Root-owned mode-700 backup folder, mode-600 credentials, synchronized UTC clock, and base local preflight passed. MySQL is 8.4.11; the schedule explicitly uses Asia/Manila. |
| External menu images | 29 references use `media.idea-flows.online`. The owner requested that each automated backup include their file bytes too. |
| Restore from the proposed automated backup | Not tested yet. Required before calling the new workflow verified. |
| Telegram alerts / independent monitor | Deferred. No bot, sender, external monitor, or alert unit is included in this implementation. |

Changes to the earlier draft:

- Schedule 11:30 p.m. explicitly in Asia/Manila, with the timezone inside `OnCalendar`. Do not use the earlier standalone `Timezone=` timer setting.
- Add a strict unattended mode instead of allowing a scheduled process to wait for terminal input.
- Create private files from the start, use a shared job lock, and retain failed attempts for investigation.
- Verify remote contents, not only their lengths; write a completion manifest last.
- Remove the draft's custom automatic-deletion script. Retention needs an agreed policy and a separate enablement step.

## 3. Smallest implementation that fits the current system

Use a **VPS systemd service and daily timer**, the existing MySQL tools, and the existing Python/boto3 uploader. This does not need a Flask background thread, a browser timer, a new worker framework, or a Codex recurring task.

| File / location | Local implementation |
| --- | --- |
| `scripts/upload_backup_to_r2.py` | Preserve manual prompting by default. Add explicit unattended credentials, manifest support, bounded network retries/timeouts, and streamed remote SHA-256 verification. |
| `scripts/run_daily_backup.sh` | Thin private-umask wrapper invoking the existing VPS Python environment. |
| `scripts/run_daily_backup.py` | Linux `flock`, credential/tool/database/space preflight, dump, public menu-image capture, archive validation, upload, private atomic status, and `--retry-upload`. No Flask import or app stop. |
| `deploy/ideaflow-daily-backup.service` | New reviewed service template using the current `/var/www/pos` installation. |
| `deploy/ideaflow-daily-backup.timer` | New 11:30 p.m. Asia/Manila timer template. |
| `deploy/backup.env.example` | Empty credential template; the real `backup.env` is ignored by Git. |
| `/etc/ideaflow/backup.env` on the VPS | Root-owned secret configuration, mode `600`, outside Git. |
| `/var/backups/ideaflow/` on the VPS | Private staging folders, failed-attempt evidence, and last-success metadata. |
| Targeted tests | Cover unattended mode, failures, verification, and completion ordering without production credentials. |

Deploying these files alone does not install or activate the timer. Follow the separate VPS acceptance steps; inspect actual systemd status before describing the job as live.

## 4. Backup contents and destination

Each automated run gets a unique prefix, for example:

```text
ideaflow-backups/
  auto-daily-20261030-233000-<unique-id>/
    pos_db.sql
    production-files.tar.gz
    manifest.json
```

The unique ID prevents a manual retry from overwriting an earlier run. Existing manual `daily-*` and `pre-*` backups stay separate.

| Object | Contents |
| --- | --- |
| `pos_db.sql` | All application tables/data in `pos_db`, plus routines, triggers, and events. This is not an export of MySQL system accounts. |
| `production-files.tar.gz` | Local `static/uploads` and `static/images`, plus `external-media/files/<menu-item-id>.bin` and an `external-media/manifest.json` index when remote menu images are referenced. The index maps each copy to its saved image URL, content type, byte size and SHA-256. |
| `manifest.json` | Run ID, scheduled backup date in Manila time, actual start/completion times in UTC and Manila time, application Git revision, file sizes and SHA-256 hashes, image inventory, scope, and verification outcome. No backup credentials are added. |

The image-aware runner inventories menu image references directly from MySQL. It fetches external images only from `https://media.idea-flows.online`, refuses redirects, streams at most 20 MiB per image, and validates every saved copy's size/hash against the archive index. Other external hosts fail preflight for review rather than silently losing coverage. Local image paths remain covered by the existing local archive directories. Unreferenced objects elsewhere in a media bucket are outside this scope.

Public image retrieval does not need a second R2 credential. The private backup-bucket credential still provides upload and read-back verification. The menu image bucket is never modified by this job. Image references are checked around the dump/download window; a changed reference, missing image, invalid response or incomplete download prevents completion. Upload retry reuses the already saved image snapshot, not the current live catalog.

Application code can be restored from its recorded Git revision. Configuration, credentials, database grants, and server setup need a separately maintained secure recovery record. Do not silently add plaintext `.env`, SSH keys, or R2 secrets to this archive. Redis login leases are transient and do not belong in a business-data restore.

## 5. Run sequence and consistency

1. Acquire an exclusive `flock` lock. Both scheduled runs and manual invocations of the new wrapper use this lock. An old hand-written backup command outside the wrapper does not automatically share it.
2. Set `umask 077`; require a root-owned mode-700 backup directory and root-owned private credentials. Check tools, local media directories, MySQL access, required tables, menu image addresses, all base-table engines, Git revision, and available space. Budget the larger of 1 GiB or four times estimated database bytes plus local media, two maximum-size copies of each external image, and 256 MiB of reserve. This is conservative and does not guarantee against concurrent disk use. Create a unique private staging folder.
3. Dump `pos_db` with the established flags plus streaming rows:

   ```text
   mysqldump --single-transaction --quick --routines --triggers --events --hex-blob --no-tablespaces --result-file=<private-folder>/pos_db.sql pos_db
   ```

4. Copy the inventoried public menu images into private temporary staging and build their address/hash index. Archive these copies together with the local media directories. Retry a changing-file archive within a bounded limit without redumping or redownloading the saved images.
5. Require successful tool exits, non-empty files, a completed SQL dump, expected schema presence, a readable gzip/tar archive, and matching external image inventory/bytes/checksums. Record diagnostic table/archive/image counts without hard-coding a permanently fixed table count. An INSERT-statement count is not a row count.
6. Compute SHA-256 and sizes for the two local files, then upload them to the new R2 prefix.
7. Read back each remote object as a stream and compute its SHA-256. Require matching size and hash. Do not treat an ETag or a user-supplied hash metadata field as an independent verification of the uploaded bytes.
8. Upload `manifest.json` last, only after both data objects pass verification. Read back and validate the small manifest as well. A missing/invalid manifest means an incomplete backup set.
9. Atomically update local `last-success.json` only after remote verification and record `last-attempt.json` plus the run folder's `run.json`. Failed backups keep their files and do not advance last success. Each complete local set has saved sizes/hashes: `--retry-upload` checks those again and reuses that dump. An already completed remote set is verified again instead of overwritten. No files are automatically deleted.

For the live database, `--single-transaction` provides a consistent snapshot for InnoDB tables; migrations and schema-changing maintenance must not overlap the dump. Check table engines first. Nontransactional tables need a different consistency strategy. [MySQL documentation](https://dev.mysql.com/doc/refman/8.4/en/mysqldump.html#option_mysqldump_single-transaction).

The database snapshot starts when its dump transaction begins, which may be slightly after 23:30:00. The database dump and media archive are separate operations, not one atomic cross-storage snapshot. For exact database/media matching, coordinate destructive media changes with the backup lock or use a suitable storage snapshot/window; do not silently stop the business app. Preserve the actual timestamps instead of claiming an exact 11:30 p.m. snapshot or recreating a past day after an outage. A delayed catch-up run uses its actual start date in its folder; its manifest also identifies the missed scheduled date, without claiming that the data is a historical snapshot.

## 6. Unattended credentials

The root-run service loads `/etc/ideaflow/backup.env` through systemd's `EnvironmentFile=`. Direct runner invocations also read that protected file using the already installed `python-dotenv` package, with interpolation disabled. Use simple unquoted values. Existing process environment variables take precedence. The uploader's `--non-interactive` mode reads backup-specific variables:

- `IDEAFLOW_BACKUP_R2_ENDPOINT`
- `IDEAFLOW_BACKUP_R2_ACCESS_KEY_ID`
- `IDEAFLOW_BACKUP_R2_SECRET_ACCESS_KEY`

The optional future Telegram settings would belong in protected configuration, with real values entered only on the VPS. **Do not configure them for this version; no sender is implemented.**

```ini
IDEAFLOW_BACKUP_TELEGRAM_BOT_TOKEN=<BOT_TOKEN>
IDEAFLOW_BACKUP_TELEGRAM_CHAT_ID=<PRIVATE_CHAT_ID>
```

These are separate from the R2 credentials. The bot token authorizes Telegram messages; the chat ID selects the approved recipient. The bot does not need R2 access keys in its messages.

Keep the private backup bucket distinct from any public media bucket. Use a token scoped to the backup bucket with the object read/write access needed for upload and read-back verification. Enter values directly in the protected VPS file during setup, not in chat, source code, command-line arguments, or shell-history assignments.

Use existing local MySQL root socket authentication only after verifying that it works unattended. The service runs as root, so the wrapper should call `mysqldump` directly rather than nesting `sudo` or allowing a password prompt. If a database credential file is required, protect it separately outside Git.

Missing credentials, refused access, or an interactive prompt in scheduled mode must fail promptly with a sanitized error. Logs must not include secret values.

## 7. Proposed service and 11:30 p.m. timer

These are templates for review and later installation, not commands executed by this document.

`ideaflow-daily-backup.service`:

```ini
[Unit]
Description=IdeaFlow database and media backup to private R2
Wants=network-online.target
After=network-online.target mysql.service

[Service]
Type=oneshot
User=root
WorkingDirectory=/var/www/pos
UMask=0077
EnvironmentFile=/etc/ideaflow/backup.env
Environment=PYTHONUNBUFFERED=1
ExecStart=/usr/bin/bash /var/www/pos/scripts/run_daily_backup.sh --scheduled
TimeoutStartSec=30min
TimeoutStopSec=30s
Nice=10
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
```

Use `/var/www/pos/venv/bin/python` inside the wrapper. Confirm these installation and database service paths on the VPS before installing. Set a bounded boto3 network retry policy, and fail on exhausted retries without regenerating a different dump for each upload retry.

`ideaflow-daily-backup.timer`:

```ini
[Unit]
Description=IdeaFlow daily backup at 11:30 p.m. Philippine time

[Timer]
OnCalendar=*-*-* 23:30:00 Asia/Manila
AccuracySec=1s
RandomizedDelaySec=0
Persistent=true

[Install]
WantedBy=timers.target
```

The explicit calendar timezone avoids dependence on the server's displayed timezone. `Persistent=true` allows a catch-up run after missed downtime; it does not reconstruct missed historical snapshots or retry an already failed backup. Scheduling targets 11:30 p.m. with a one-second accuracy window; load and clock readiness can delay execution. [Calendar syntax](https://www.freedesktop.org/software/systemd/man/latest/systemd.time.html#Calendar%20Events), [timer behavior](https://www.freedesktop.org/software/systemd/man/259/systemd.timer.html).

A successful oneshot service normally finishes and becomes inactive. Check its result/exit status and manifest. The timer should remain active and waiting for the next run; the backup service itself does not need to stay active all day.

## 8. Failure handling and visibility

| Failure | Required behavior |
| --- | --- |
| Database or archive fails | Keep the partial attempt private, report the failed stage, and do not publish a completion manifest. |
| Missing R2 credentials | Exit promptly; do not wait for input. |
| Network/R2 failure | Retry within configured limits, then fail; retain local files for a later retry. |
| Remote size/hash mismatch | No completion manifest and no last-success update. |
| Disk space insufficient | Fail before starting where detectable; never delete the only successful backup to make room. |
| Another wrapper run holds the lock | Record that this attempt did not create a backup; do not mark a new success. |
| VPS unavailable at 11:30 p.m. | Catch up after recovery and record the actual backup time. |

Check stage/status logs in the systemd journal and the private JSON status files. Last-success metadata identifies the last remotely verified prefix and time, not merely the last attempted start. Tool/provider error bodies are suppressed to avoid leaking secrets or database contents. A missing environment file, process kill, or failure before Python starts is visible through systemd's result/exit status; JSON can still show an earlier attempt or interrupted `running` stage. **Check both systemd and JSON. No notification is sent.**

### 8.1 Deferred: future Telegram setup

1. Create a dedicated backup-alert bot through the official [BotFather](https://t.me/BotFather). Store its token directly in the protected VPS file.
2. Open that bot's private chat in Telegram and press **Start**. Enable notifications for that chat on the recipient's phone.
3. Retrieve that chat's numeric ID with a one-time setup helper using the official API, and store only the intended private chat ID. Do not use a public chat-ID discovery service or paste a token-bearing URL into shell/browser history. A permanent incoming webhook or running chat-command bot is unnecessary for outbound alerts.
4. During the authorized setup, send one clearly labelled test alert and confirm that it reaches the intended chat. Do not call notifications configured until this delivery check passes.

Bot creation and interaction are described in the [Telegram bot guide](https://core.telegram.org/bots/features#botfather). The sender will use HTTPS `sendMessage` with a fixed configured chat ID, plain text, a short timeout, and response validation. An HTTP response alone is insufficient: require the API's successful `ok` result. Respect `retry_after` for rate limits within bounded retry limits. [Telegram Bot API](https://core.telegram.org/bots/api#sendmessage).

### 8.2 Deferred: what would trigger a message

| Event | Telegram behavior |
| --- | --- |
| A backup ultimately fails after its applicable retries | Send a failure alert with the failed stage, Manila time, run ID, last verified backup time, and whether a completed local copy is available. |
| A temporary upload error recovers within its retries | No failure alert for each retry. Keep the details in the journal. |
| The next backup is remotely verified after an unresolved failure | Send a recovery message naming the newly verified run. |
| An ordinary successful nightly run with no unresolved incident | No routine success message by default. |
| The scheduled day's expected verified backup is missing after its completion deadline | An independent monitor sends a distinct missed-backup alert; see section 8.4. |

Example failure message, using illustrative times:

```text
IdeaFlow backup FAILED
Run: 2026-10-30 23:30 Philippine time
Stage: R2 upload — retries exhausted
Last verified backup: 2026-10-29 23:34 Philippine time
Completed local copy available: Yes
Action: check the backup service logs and retry the saved set.
```

Messages must exclude database contents, customer names, sales totals, passwords, keys, and raw exception/HTTP URLs. Do not attach backup files. Do not claim the application is healthy unless its health was actually checked; this alert reports backup status.

A future failure service would use `OnFailure=` so unit startup errors and timeouts can reach the sender too. This version has no failure-alert service. If the runner did not save stage metadata, inspect the backup unit's failure result and last verified time. [systemd failure handlers](https://www.freedesktop.org/software/systemd/man/259/systemd.unit.html#OnFailure=).

### 8.3 Deferred: delivery errors and repeat control

- Persist the run/incident ID and delivery result so normal repeated handlers do not flood the recipient with the same alert. Do not promise exactly-once delivery when an API acknowledgment is lost.
- Retry temporary Telegram connection/server errors within a short total timeout. A rejected token or blocked chat needs configuration/recipient correction, not an endless retry loop.
- Never print the bot token, token-bearing request URL, or raw network exception that may contain it. Read credentials in-process rather than putting them in command arguments.
- Failed message delivery leaves a sanitized journal entry and a pending notification status for a later retry/recovery summary. It does not silently become a delivered alert.
- A notification failure must not turn a verified backup into a failed backup, rerun the database dump, or alter the successful manifest. Preserve the original backup failure status when the backup itself failed.

### 8.4 Deferred: detecting a missed run or an unavailable VPS

A notifier running only on this VPS cannot send an alert while the VPS is off or its outbound network is unavailable. Immediate failure alerts and missed-run monitoring therefore cover different cases.

Recommended second layer: an independent scheduled check, outside this VPS, looks for the expected day's valid completion manifest in the private R2 bucket. A small Cloudflare Worker is a candidate using the existing Cloudflare platform; its deployment, private storage binding, alert state, and secrets are still planned, not created.

- Proposed deadline: **12:15 a.m. Philippine time the following day**, allowing the backup's 30-minute timeout plus a 15-minute margin. For example, the October 30 11:30 p.m. backup is checked by October 31 at 12:15 a.m. against the **October 30 scheduled date**. Reassess that limit after measuring a real run.
- If the expected manifest is absent, invalid, or the required objects are missing, notify Telegram that the backup could not be confirmed. If R2 itself cannot be read, say verification is unavailable rather than asserting the VPS is down.
- Recheck unresolved incidents periodically, suppress routine repeat alerts by incident/day, and send a recovery message when a qualifying verified set appears. Keep the monitor's state separate from backup sets and their expiration rules.
- The checker validates the run's actual timestamps, expected scheduled Manila date, manifest schema/completion status, and referenced object presence/sizes; at the 12:15 a.m. check, the expected scheduled date is the previous Manila calendar day. An old unrelated successful backup must not satisfy that check. This is a freshness check of a previously verified set, not a replacement for upload-time content verification or restore testing.
- Store the monitor's Telegram token as a platform secret. Never make the backup bucket public to support monitoring. Cloudflare schedules use UTC, so any chosen schedule must be converted and checked against Asia/Manila dates. [Cloudflare scheduled triggers](https://developers.cloudflare.com/workers/configuration/cron-triggers/).

If only the VPS sender is installed initially, explicitly record that VPS-offline/missed-run alerts are not yet covered. Neither Telegram delivery nor any independent monitoring service has been configured or activated by writing this plan, and no external messages have been sent.

## 9. Retention

Initial implementation: **no automatic deletion** of existing local or R2 backups. Monitor disk space during validation.

Proposed later policy, requiring an agreed retention period:

- Keep 7 days of remotely verified automated backups locally.
- Keep 30 days of automated backups in R2.
- Preserve existing manual/pre-deployment backups outside the automated prefix.
- Use a prefix-scoped R2 lifecycle rule instead of a new custom deletion program. [Cloudflare lifecycle documentation](https://developers.cloudflare.com/r2/buckets/object-lifecycles/).

Failed local attempts and incomplete remote prefixes need their own reviewed cleanup rule. An age-based R2 lifecycle rule does not understand whether a backup has a valid manifest. Never apply a whole-bucket expiration rule merely to clean up this new job.

## 10. Implementation and acceptance plan

### Phase A — local implementation and isolated checks

Local image-extension evidence (October 30): **44 backup checks passed**, with one native Linux `flock` test skipped on Windows. Tests cover the existing uploader/failure paths plus a real native tar containing local and downloaded images, per-image hash validation, retry without redownloading, rejected external addresses/redirects, incomplete/oversized/HTML responses, and changed image references. Tests use synthetic data and fake R2/HTTP clients. The base release's Linux CI also passed. The image-aware VPS upload, isolated restore, controlled failure and first scheduled run must be verified separately.

- Extend the existing uploader and add the wrapper/unit templates listed above.
- Keep manual upload usage compatible.
- Test missing credentials, no terminal input, retries, dump/archive errors, simulated disk exhaustion, corrupted remote bytes, interrupted uploads, and overlapping wrapper runs.
- Assert that a manifest is written only after verification, failure does not advance last-success, and logs redact secrets.
- Telegram tests and implementation are deferred with notifications. This version tests secret redaction, failure status, and preserving the last verified backup locally.
- Review script quoting, private permissions, path handling, and Linux unit syntax.

### Phase B — read-only VPS preflight

- Inspect the effective existing timers/cron schedules before adding another job.
- Confirm `/var/www/pos`, its `venv`, MySQL socket authentication, table engines, media storage, disk headroom, and time synchronization.
- Validate the schedule on the actual server with `systemd-analyze calendar '*-*-* 23:30:00 Asia/Manila'` and validate unit files with `systemd-analyze verify`.
- Confirm that no deployment/migration or conflicting maintenance task is scheduled for the same backup window.
- Record that notifications and independent missed-run monitoring are deferred, so backup status needs manual checking.

### Phase C — controlled test, then enablement

- Install the reviewed files and protected secret configuration without changing the business app's code, credentials, or service state as part of the backup job.
- Run the backup service manually once with no interactive input.
- Verify the two data objects and completion manifest in the private R2 bucket.
- Download that set, verify hashes, restore into an isolated database, and inspect representative customer, checkout, debt, expense, inventory, and cash-history records plus extracted media. Never test a restore by importing over `pos_db`.
- Simulate a backup failure safely without damaging real data. Confirm the nonzero service result, sanitized journal entry, preserved last-success record, and a successful saved-set upload retry. Telegram and an alert handler are outside this version.
- Enable the daily timer only after these checks pass, then confirm the next trigger is 11:30 p.m. Manila time.
- Verify the first real 11:30 p.m. run afterwards; a successful manual test alone does not prove the schedule fired.

### Phase D — deferred: independent missed-run coverage

- If this layer is included, prepare and review its small implementation locally before any external deployment or secret configuration.
- Test an absent, stale, malformed, and incomplete backup set, a read failure, and an eventually valid manifest. Confirm correct local-date handling, one incident's normal repeat suppression, and recovery behavior.
- Verify that a simulated unavailable VPS still results in a missed-backup Telegram alert without changing the live business service.
- Record the external schedule, expected-run cutoff, state location, secret ownership, and health-check procedure. Until deployed and tested, do not claim this coverage exists.

At VPS acceptance, record the installed revision, timer schedule, last successful prefix, verification/restore evidence, and chosen retention/alert settings in this file. Local implementation alone does not mean the job is deployed or its real schedule has fired.

## 11. Operational limits and recovery

A daily backup can leave roughly a day of changes since the last successful run; failures can make that gap longer. More frequent recovery needs would require an additional strategy such as transaction-log recovery, outside this daily-job scope.

To pause the future automation, disable its timer and investigate its logs. Leave the application and existing verified backups intact. Continue using the established manual backup process while automation is repaired. A VPS/system snapshot remains useful for server recovery but is separate from this application database/media backup.
