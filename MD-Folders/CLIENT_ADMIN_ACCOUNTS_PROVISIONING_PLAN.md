# Provision two client admin accounts

## Status and scope

**Localhost complete; production untouched.** On 2026-10-25, the two accounts below were created in the local SQLite database only. A one-time account migration is now prepared locally. The live VPS will receive the accounts only when the updated code is deployed and `python -m app.db.run_migrations` is run against production MySQL after a fresh backup. The existing admin account was not changed.

| Person | Display name | Login username | Access |
| --- | --- | --- | --- |
| Client | Admin Gilbert | `admin_gilbert` | Full admin |
| Client's son | Admin 3 | `admin3` | Full admin |

Each account gets a different randomly generated password. The current limit of **two simultaneous devices per admin account** stays unchanged. These are separate accounts, so actions and login leases remain attributable to the username used.

## Local execution, 2026-10-25

- Confirmed the running local Flask configuration uses `instance/ideahub_local.db`, not the production MySQL database, and that neither username existed locally.
- Made a consistent SQLite backup in `instance/backups/` and verified its integrity before inserting the accounts.
- Created `admin_gilbert` and `admin3` with separate random bcrypt-hashed passwords. The current credentials are in a private file outside this repository; no plaintext password or hash is recorded in this plan.
- Verified each account can sign in, open `/admin`, and log out. First login created the expected admin shadow user. The original admin password hash was unchanged.
- The local Redis lease/device limit was not exercised because Redis is unavailable in this local configuration. No VPS, R2, Cloudflare Access, or production account was changed.
- Added the one-time production provision to `app/db/run_migrations.py`. It generates **new production passwords**, which will differ from the localhost passwords, and writes them to `~/.ideaflow/client-admin-credentials.txt` on the machine that runs the migration. The file is created with mode `0600`, outside Git; the migration prints only its path.
- If both named admin accounts already exist, a repeat run leaves their passwords unchanged. A partial account collision or existing credentials file blocks provisioning for inspection rather than overwriting anything.

## What the code supports today

- Admin login authenticates against the `admins` table. On first login, the existing login path creates a matching inactive `users` shadow row for role checks.
- The Admin Panel's **Add User** form and `/api/register` create **staff accounts only**. They must not be used to create these admins.
- `scripts/safe_update_admin.py` must not be used here: it can overwrite an existing admin password and has a built-in default password.
- The Admin Panel can view and revoke other active login sessions. It currently has no self-service workflow for creating admin accounts or resetting their passwords.

## Future production provisioning steps

1. **Preflight, read only.** On the VPS, confirm the deployed revision, the existing admin, and whether either new username already exists in `admins` or `users`. Review Cloudflare Access rules: each person needs their own permitted identity there if Access protects the site.
2. **Back up before writing.** Create a fresh MySQL dump and production-files archive using the established R2 procedure. Verify the files and both uploads. Record only the backup identifier in the change log.
3. **Deploy and run the migration on the VPS.** After the updated code is pulled, run `sudo venv/bin/python -m app.db.run_migrations` from `/var/www/pos`. The account provision is wired to this explicit command, so a code pull or service restart alone will not create the accounts. The migration checks for collisions, creates both rows in one transaction, and prints the private credentials file path without printing passwords.
4. **Hand over the new production passwords.** Read the printed file path in the VPS terminal, save the credentials in a password manager, and give each person only their own credential through a secure direct channel. Do not paste the passwords into Git, Codex, logs, or a shared message. Remove the plaintext file after secure handoff.
5. **Verify without business writes.** Sign in separately as `admin_gilbert` and `admin3`; confirm each reaches `/admin` and that the original admin still works. Confirm the first login creates the expected admin shadow `User` row and that the existing two-device limit applies per account. Log out of test sessions.
6. **Record completion.** Note the date, usernames, operator, backup identifier, and login-check results in the maintenance log. Do not record passwords.

## Recovery and limits

- If a username already exists, stop and inspect it; do not reset or reuse the existing account automatically.
- If the credential file already exists while the accounts are absent, stop and inspect it; the migration will not overwrite it. If database commit fails, the private file is kept because a lost commit acknowledgement could still mean the rows were created. Inspect before retrying.
- If an account must be withdrawn later, revoke its active leases and perform a controlled account change after checking whether it has audit/history references. Do not restore an old full database backup over newer live sales.
- Two extra admins provide independent access but do **not** replace the Android Back/relaunch fix. That fix still needs deployment and a check on the client's phone.
- Because the app has no admin password-reset UI today, these accounts alone do not give the client full self-service credential management. That would be a separate feature if required.
