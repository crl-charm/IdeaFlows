# Daily midnight backup to Cloudflare R2 — revised implementation plan

Updated: October 26, 2026.

**Status: planned; not implemented or enabled by this documentation update.** This replaces the earlier draft in this file. It is the current plan, subject to the VPS preflight checks below.

## 1. What the owner will get

Every day at **12:00 a.m. Philippine time, Asia/Manila**, the VPS starts a backup, uploads it to the private **`ideaflow-backups`** R2 bucket, and records whether it succeeded. No open laptop, signed-in browser, or nightly password entry is needed after the one-time setup.

The confirmed business hours are **8:00 a.m. to 8:00 p.m.** Midnight is four hours after closing. **Telegram is the selected notification channel** for backup failures and recovery; the bot and delivery destination have not been configured yet.

Example: the October 27 midnight run takes a full backup of the system as the new day begins. It contains older records too; it does not export only October 26 transactions. Starting at midnight does not mean uploading finishes at midnight.

The intended daily operation keeps IdeaFlow available. Confirm transactional database tables and the file-copy conditions before promising an online backup; see section 5.

## 2. What is verified already, and what is still unknown

| Item | Current evidence |
| --- | --- |
| Manual R2 backup | Successful uploads have been reported in this conversation. |
| Repository uploader | `scripts/upload_backup_to_r2.py` currently prompts for endpoint/key/secret and explicitly verifies object size. It cannot yet run unattended as written. |
| Existing automation document | Was a draft, not evidence of an installed job. Its 23:30 schedule did not match midnight. |
| Existing VPS timer or cron job | Not inspected in this task. Check before installing anything, to avoid duplicate jobs. |
| Restore from the proposed automated backup | Not tested yet. Required before calling the new workflow verified. |
| Telegram alerts | Selected by the user. Bot credentials, destination, delivery tests, and any independent missed-run monitor remain to be set up. |

Changes to the earlier draft:

- Schedule midnight explicitly in Asia/Manila, with the timezone inside `OnCalendar`. Do not use the earlier standalone `Timezone=` timer setting.
- Add a strict unattended mode instead of allowing a scheduled process to wait for terminal input.
- Create private files from the start, use a shared job lock, and retain failed attempts for investigation.
- Verify remote contents, not only their lengths; write a completion manifest last.
- Remove the draft's custom automatic-deletion script. Retention needs an agreed policy and a separate enablement step.

## 3. Smallest implementation that fits the current system

Use a **VPS systemd service and daily timer**, the existing MySQL tools, and the existing Python/boto3 uploader. This does not need a Flask background thread, a browser timer, a new worker framework, or a Codex recurring task.

| File / location | Planned change |
| --- | --- |
| `scripts/upload_backup_to_r2.py` | Preserve manual prompting by default. Add explicit unattended credentials, manifest support, bounded network retries/timeouts, and streamed remote SHA-256 verification. |
| `scripts/run_daily_backup.sh` | New wrapper: lock, preflight, dump, archive, validate, invoke uploader, record result. |
| `scripts/notify_backup.py` | New small Telegram sender using Python's standard library, protected configuration, sanitized messages, and bounded delivery retries. |
| `deploy/ideaflow-daily-backup.service` | New reviewed service template using the current `/var/www/pos` installation. |
| `deploy/ideaflow-daily-backup.timer` | New midnight Asia/Manila timer template. |
| `deploy/ideaflow-backup-alert.service` | New failure handler for the backup unit, including failures outside the wrapper's normal error handling. |
| `/etc/ideaflow/backup.env` on the VPS | Root-owned secret configuration, mode `600`, outside Git. |
| `/var/backups/ideaflow/` on the VPS | Private staging folders, failed-attempt evidence, and last-success metadata. |
| Targeted tests | Cover unattended mode, failures, verification, and completion ordering without production credentials. |

Only the document is changed now. These scripts and units are deliverables for the later implementation step.

## 4. Backup contents and destination

Each automated run gets a unique prefix, for example:

```text
ideaflow-backups/
  auto-daily-20261027-000000-<unique-id>/
    pos_db.sql
    production-files.tar.gz
    manifest.json
```

The unique ID prevents a manual retry from overwriting an earlier run. Existing manual `daily-*` and `pre-*` backups stay separate.

| Object | Contents |
| --- | --- |
| `pos_db.sql` | All application tables/data in `pos_db`, plus routines, triggers, and events. This is not an export of MySQL system accounts. |
| `production-files.tar.gz` | Current local `static/uploads` and `static/images`, matching the established manual backup scope. Confirm any additional mutable asset paths before finalizing the archive list. |
| `manifest.json` | Run ID, actual start/completion times in UTC and Manila time, application Git revision, file sizes and SHA-256 hashes, scope, and verification outcome. No passwords or tokens. |

Inventory media storage during preflight. Images already stored in a separate R2 media bucket are not captured by a local tar archive; if production uses those assets, include a versioned backup copy/export of the referenced media before claiming complete media recovery.

Application code can be restored from its recorded Git revision. Configuration, credentials, database grants, and server setup need a separately maintained secure recovery record. Do not silently add plaintext `.env`, SSH keys, or R2 secrets to this archive. Redis login leases are transient and do not belong in a business-data restore.

## 5. Run sequence and consistency

1. Acquire an exclusive `flock` lock. Both scheduled runs and manual invocations of the new wrapper use this lock. An old hand-written backup command outside the wrapper does not automatically share it.
2. Set `umask 077`; check tool paths, source directories, database access, credentials, and available disk space. Create a unique private staging folder.
3. Dump `pos_db` with the established flags plus streaming rows:

   ```text
   mysqldump --single-transaction --quick --routines --triggers --events --hex-blob --no-tablespaces --result-file=<private-folder>/pos_db.sql pos_db
   ```

4. Archive the confirmed mutable local media directories. A failed or changing-file archive is not accepted as a successful backup; retry the archive within a bounded limit or fail visibly.
5. Require successful tool exits, non-empty files, a completed SQL dump, expected schema presence, and a readable gzip/tar archive. Record diagnostic table/archive counts without hard-coding a permanently fixed table count. An INSERT-statement count is not a row count.
6. Compute SHA-256 and sizes for the two local files, then upload them to the new R2 prefix.
7. Read back each remote object as a stream and compute its SHA-256. Require matching size and hash. Do not treat an ETag or a user-supplied hash metadata field as an independent verification of the uploaded bytes.
8. Upload `manifest.json` last, only after both data objects pass verification. Read back and validate the small manifest as well. A missing/invalid manifest means an incomplete backup set.
9. Atomically update local last-success metadata and emit one clear success log line. All other outcomes retain the last successful record and produce a nonzero result.

For the live database, `--single-transaction` provides a consistent snapshot for InnoDB tables; migrations and schema-changing maintenance must not overlap the dump. Check table engines first. Nontransactional tables need a different consistency strategy. [MySQL documentation](https://dev.mysql.com/doc/refman/8.4/en/mysqldump.html#option_mysqldump_single-transaction).

The database snapshot starts when its dump transaction begins, which may be slightly after 00:00:00. The database dump and media archive are separate operations, not one atomic cross-storage snapshot. For exact database/media matching, coordinate destructive media changes with the backup lock or use a suitable storage snapshot/window; do not silently stop the business app. Preserve the actual timestamps instead of claiming an exact midnight snapshot or recreating a past day after an outage.

## 6. Unattended credentials

The root-run service loads `/etc/ideaflow/backup.env` through systemd's `EnvironmentFile=`. The uploader's proposed `--non-interactive` mode reads backup-specific variables:

- `IDEAFLOW_BACKUP_R2_ENDPOINT`
- `IDEAFLOW_BACKUP_R2_ACCESS_KEY_ID`
- `IDEAFLOW_BACKUP_R2_SECRET_ACCESS_KEY`

The same protected file will hold the Telegram settings, with real values entered only on the VPS:

```ini
IDEAFLOW_BACKUP_TELEGRAM_BOT_TOKEN=<BOT_TOKEN>
IDEAFLOW_BACKUP_TELEGRAM_CHAT_ID=<PRIVATE_CHAT_ID>
```

These are separate from the R2 credentials. The bot token authorizes Telegram messages; the chat ID selects the approved recipient. The bot does not need R2 access keys in its messages.

Keep the private backup bucket distinct from any public media bucket. Use a token scoped to the backup bucket with the object read/write access needed for upload and read-back verification. Enter values directly in the protected VPS file during setup, not in chat, source code, command-line arguments, or shell-history assignments.

Use existing local MySQL root socket authentication only after verifying that it works unattended. The service runs as root, so the wrapper should call `mysqldump` directly rather than nesting `sudo` or allowing a password prompt. If a database credential file is required, protect it separately outside Git.

Missing credentials, refused access, or an interactive prompt in scheduled mode must fail promptly with a sanitized error. Logs must not include secret values.

## 7. Proposed service and midnight timer

These are templates for review and later installation, not commands executed by this document.

`ideaflow-daily-backup.service`:

```ini
[Unit]
Description=IdeaFlow database and media backup to private R2
Wants=network-online.target
After=network-online.target mysql.service
OnFailure=ideaflow-backup-alert.service

[Service]
Type=oneshot
User=root
WorkingDirectory=/var/www/pos
UMask=0077
EnvironmentFile=/etc/ideaflow/backup.env
ExecStart=/usr/bin/bash /var/www/pos/scripts/run_daily_backup.sh
TimeoutStartSec=30min
Nice=10
```

Use `/var/www/pos/venv/bin/python` inside the wrapper. Confirm these installation and database service paths on the VPS before installing. Set a bounded boto3 network retry policy, and fail on exhausted retries without regenerating a different dump for each upload retry.

`ideaflow-daily-backup.timer`:

```ini
[Unit]
Description=IdeaFlow daily backup at midnight Philippine time

[Timer]
OnCalendar=*-*-* 00:00:00 Asia/Manila
AccuracySec=1s
RandomizedDelaySec=0
Persistent=true

[Install]
WantedBy=timers.target
```

The explicit calendar timezone avoids dependence on the server's displayed timezone. `Persistent=true` allows a catch-up run after missed downtime; it does not reconstruct missed historical snapshots or retry an already failed backup. Scheduling targets midnight with a one-second accuracy window; load and clock readiness can delay execution. [Calendar syntax](https://www.freedesktop.org/software/systemd/man/latest/systemd.time.html#Calendar%20Events), [timer behavior](https://www.freedesktop.org/software/systemd/man/259/systemd.timer.html).

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
| VPS unavailable at midnight | Catch up after recovery and record the actual backup time. |

Keep detailed stage/status logs in the systemd journal. Last-success metadata must identify the last remotely verified prefix and time, not merely the last attempted start. Telegram delivery status is tracked separately from backup verification status.

### 8.1 Telegram setup — once, during implementation

1. Create a dedicated backup-alert bot through the official [BotFather](https://t.me/BotFather). Store its token directly in the protected VPS file.
2. Open that bot's private chat in Telegram and press **Start**. Enable notifications for that chat on the recipient's phone.
3. Retrieve that chat's numeric ID with a one-time setup helper using the official API, and store only the intended private chat ID. Do not use a public chat-ID discovery service or paste a token-bearing URL into shell/browser history. A permanent incoming webhook or running chat-command bot is unnecessary for outbound alerts.
4. During the authorized setup, send one clearly labelled test alert and confirm that it reaches the intended chat. Do not call notifications configured until this delivery check passes.

Bot creation and interaction are described in the [Telegram bot guide](https://core.telegram.org/bots/features#botfather). The sender will use HTTPS `sendMessage` with a fixed configured chat ID, plain text, a short timeout, and response validation. An HTTP response alone is insufficient: require the API's successful `ok` result. Respect `retry_after` for rate limits within bounded retry limits. [Telegram Bot API](https://core.telegram.org/bots/api#sendmessage).

### 8.2 What will trigger a message

| Event | Telegram behavior |
| --- | --- |
| A backup ultimately fails after its applicable retries | Send a failure alert with the failed stage, Manila time, run ID, last verified backup time, and whether a completed local copy is available. |
| A temporary upload error recovers within its retries | No failure alert for each retry. Keep the details in the journal. |
| The next backup is remotely verified after an unresolved failure | Send a recovery message naming the newly verified run. |
| An ordinary successful nightly run with no unresolved incident | No routine success message by default. |
| Today's expected verified backup is missing after the completion deadline | An independent monitor sends a distinct missed-backup alert; see section 8.4. |

Example failure message, using illustrative times:

```text
IdeaFlow backup FAILED
Run: 2026-10-27 00:00 Philippine time
Stage: R2 upload — retries exhausted
Last verified backup: 2026-10-26 00:04 Philippine time
Completed local copy available: Yes
Action: check the backup service logs and retry the saved set.
```

Messages must exclude database contents, customer names, sales totals, passwords, keys, and raw exception/HTTP URLs. Do not attach backup files. Do not claim the application is healthy unless its health was actually checked; this alert reports backup status.

The failure service uses `OnFailure=` so unit startup errors and timeouts can reach the sender too. If the wrapper did not save stage metadata, use the unit failure result and last verified time instead. [systemd failure handlers](https://www.freedesktop.org/software/systemd/man/259/systemd.unit.html#OnFailure=).

### 8.3 Delivery errors and repeat control

- Persist the run/incident ID and delivery result so normal repeated handlers do not flood the recipient with the same alert. Do not promise exactly-once delivery when an API acknowledgment is lost.
- Retry temporary Telegram connection/server errors within a short total timeout. A rejected token or blocked chat needs configuration/recipient correction, not an endless retry loop.
- Never print the bot token, token-bearing request URL, or raw network exception that may contain it. Read credentials in-process rather than putting them in command arguments.
- Failed message delivery leaves a sanitized journal entry and a pending notification status for a later retry/recovery summary. It does not silently become a delivered alert.
- A notification failure must not turn a verified backup into a failed backup, rerun the database dump, or alter the successful manifest. Preserve the original backup failure status when the backup itself failed.

### 8.4 Detecting a missed run or an unavailable VPS

A notifier running only on this VPS cannot send an alert while the VPS is off or its outbound network is unavailable. Immediate failure alerts and missed-run monitoring therefore cover different cases.

Recommended second layer: an independent scheduled check, outside this VPS, looks for the expected day's valid completion manifest in the private R2 bucket. A small Cloudflare Worker is a candidate using the existing Cloudflare platform; its deployment, private storage binding, alert state, and secrets are still planned, not created.

- Proposed deadline: **12:45 a.m. Philippine time**, allowing the backup's 30-minute timeout plus a 15-minute margin. Reassess that limit after measuring a real run.
- If the expected manifest is absent, invalid, or the required objects are missing, notify Telegram that the backup could not be confirmed. If R2 itself cannot be read, say verification is unavailable rather than asserting the VPS is down.
- Recheck unresolved incidents periodically, suppress routine repeat alerts by incident/day, and send a recovery message when a qualifying verified set appears. Keep the monitor's state separate from backup sets and their expiration rules.
- The checker validates the run's actual timestamps, expected local date, manifest schema/completion status, and referenced object presence/sizes; an old unrelated successful backup must not satisfy today's check. This is a freshness check of a previously verified set, not a replacement for upload-time content verification or restore testing.
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

- Extend the existing uploader and add the wrapper/unit templates listed above.
- Keep manual upload usage compatible.
- Test missing credentials, no terminal input, retries, dump/archive errors, simulated disk exhaustion, corrupted remote bytes, interrupted uploads, and overlapping wrapper runs.
- Assert that a manifest is written only after verification, failure does not advance last-success, and logs redact secrets.
- Test Telegram success/rejection/timeout/rate-limit responses, secret redaction, repeat suppression, and recovery messages. A failed notification must preserve the backup's actual outcome.
- Review script quoting, private permissions, path handling, and Linux unit syntax.

### Phase B — read-only VPS preflight

- Inspect the effective existing timers/cron schedules before adding another job.
- Confirm `/var/www/pos`, its `venv`, MySQL socket authentication, table engines, media storage, disk headroom, and time synchronization.
- Validate the schedule on the actual server with `systemd-analyze calendar '*-*-* 00:00:00 Asia/Manila'` and validate unit files with `systemd-analyze verify`.
- Confirm that no deployment/migration or conflicting maintenance task is scheduled for the same backup window.
- Confirm the intended Telegram recipient and whether the independent missed-run monitor will be included in initial enablement.

### Phase C — controlled test, then enablement

- Install the reviewed files and protected secret configuration without changing the business app's code, credentials, or service state as part of the backup job.
- Run the backup service manually once with no interactive input.
- Verify the two data objects and completion manifest in the private R2 bucket.
- Download that set, verify hashes, restore into an isolated database, and inspect representative customer, checkout, debt, expense, inventory, and cash-history records plus extracted media. Never test a restore by importing over `pos_db`.
- Verify a labelled Telegram test, then simulate a backup failure safely without damaging real data. Confirm the failure alert and the recovery message following a verified retry. Verify the service failure-handler path as well as the wrapper's normal error path.
- Enable the daily timer only after these checks pass, then confirm the next trigger is midnight Manila time.
- Verify the first real midnight run afterwards; a successful manual test alone does not prove the schedule fired.

### Phase D — independent missed-run coverage

- If this layer is included, prepare and review its small implementation locally before any external deployment or secret configuration.
- Test an absent, stale, malformed, and incomplete backup set, a read failure, and an eventually valid manifest. Confirm correct local-date handling, one incident's normal repeat suppression, and recovery behavior.
- Verify that a simulated unavailable VPS still results in a missed-backup Telegram alert without changing the live business service.
- Record the external schedule, expected-run cutoff, state location, secret ownership, and health-check procedure. Until deployed and tested, do not claim this coverage exists.

At completion, record the installed revision, timer schedule, last successful prefix, verification/restore evidence, and chosen retention/alert settings in this file. Until those steps occur, the feature remains planned rather than deployed.

## 11. Operational limits and recovery

A daily backup can leave roughly a day of changes since the last successful run; failures can make that gap longer. More frequent recovery needs would require an additional strategy such as transaction-log recovery, outside this daily-job scope.

To pause the future automation, disable its timer and investigate its logs. Leave the application and existing verified backups intact. Continue using the established manual backup process while automation is repaired. A VPS/system snapshot remains useful for server recovery but is separate from this application database/media backup.
