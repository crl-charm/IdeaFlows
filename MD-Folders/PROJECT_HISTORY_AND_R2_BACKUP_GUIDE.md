# IdeaHub / IdeaFlow project history and Cloudflare R2 backup guide

**Compiled:** 2026-10-08 (Asia/Singapore). **Business dates:** Asia/Manila.
**Repository:** `C:\Users\hi\OneDrive\Desktop\vercelIdeahub`. **Public product:** IdeaFlow at `https://idea-flows.online`.

This is the handoff for an owner or a new AI working on the project. It combines the accessible project chats, the repository's 93 commits from April 28 through October 6, 2026, the code and plans present on October 8, and the owner runbook. It is a synthesis, not a verbatim transcript. Some older conversations may not be accessible; their work is represented only where Git or repository documents verify it. **A plan, a local change, a GitHub push, and a VPS deployment are four different states.** Recheck each before describing a feature as live.

Do not put passwords, private keys, the real `.env`, database URLs, customer data, or backup contents into this file or Git. The bucket names and public domain below are identifiers, not credentials.

## 1. Read this first: current handoff

1. The app is a Flask POS and operations system for a coworking space and cafe. It manages staff, customer time sessions, food orders, inventory, bookings, receivables, payables, expenses, checkout, Daily Balance, exports, and analytics.
2. **Production is documented and previously verified as MySQL database `pos_db` on a Hostinger VPS.** Local development and isolated tests may use SQLite. A local `.env` or SQLite test process does not mean production was switched to SQLite.
3. The VPS checkout is `/var/www/pos`, its Python environment is `/var/www/pos/venv`, the app service is `ideahub.service`, and Nginx fronts Gunicorn. Redis supports temporary login leases, rate limits, caching, and real-time behavior. Check the live configuration before acting on any of these assumptions.
4. Cloudflare protects and serves the site. `ideaflow-media` stores production menu media; **`ideaflow-backups` is a separate private R2 bucket** for backup objects. Having either bucket does not make a MySQL backup automatically.
5. The last committed local revision observed for this guide is `022f288` (October 6, 2026), on `master` with no ahead/behind indication relative to the local `origin/master` tracking ref. This is **not** a fresh verification of GitHub or the VPS revision.
6. As of this guide, the main working tree has **27 modified tracked files and seven untracked files** from cash-box, owner-funding, Expense, Payable, and Daily Balance work. The plan calls this **implemented locally**. It is not confirmed pushed or deployed. Preserve those changes. See [the cash-box plan](MD-Folders/PETTY_CASH_CASH_BOXES_OWNER_FUNDING_PLAN.md).
7. A verified **October 7, 2026** backup was recorded in the accessible chat: `daily-20261007-K7iXmi/pos_db.sql` (210,528 bytes) and `production-files.tar.gz` (17,989,876 bytes) uploaded to R2 with matching remote sizes. This does not prove an October 8 backup or a successful restore drill.
8. The October 7 code audit identified five locally reproduced defects and two additional risks. They are recorded in section 7. Do not assume the public site has those exact defects until its deployed revision is checked.
9. For **every money operation**, follow [AGENTS.md](AGENTS.md): accurate queryable history, actor, payment method, business date, related entity, and before/after balance detail; no duplicates on retries; Daily Balance and exports must reconcile from the same records using Asia/Manila days.
10. The working daily backup procedure is in section 9. The existing uploader is **interactive** and verifies remote file sizes. A daily systemd timer is an unimplemented improvement unless the VPS itself has since been configured independently.

### What “done” means here

| Label | Meaning |
| --- | --- |
| Committed | Present in repository commit history. Still check whether pushed and deployed. |
| Local uncommitted | Present only in the current checkout/worktree. Do not reset, overwrite, or call it live. |
| Previously verified on VPS | A past chat recorded successful VPS checks at that time. The VPS may have changed since. |
| Plan | A Markdown design or task list. It does not prove implementation. |
| Unknown | Requires GitHub, VPS, Cloudflare dashboard, or real-device inspection. |

## 2. Why the project exists and what users do

The product joins a workspace timer and cafe POS. Staff check customers into Regular/Premium lounge or other spaces, place food and drink orders, collect payment, and check customers out. Admins manage prices, menu, employees, inventory, bookings, money owed by customers, money owed to suppliers, reports, and cash. Public visitors see the promotional website and can install the PWA; the private application uses authenticated staff/admin screens.

Typical operating flow:

1. Staff sign in and record their own Time In / Time Out shift. Customer Time In is a separate action.
2. Staff check in one Regular/Premium person, or use the appropriate Boardroom, Whole Hub, or Food Order/Take Out flow. Space capacity and booking rules apply. Regular/Premium time can be paused and resumed where the committed feature applies.
3. The kitchen or staff enter actual raw ingredient quantities and meal serving counts. Orders reduce the applicable meal availability and keep order history. Inventory adjustments retain the actor and reason.
4. At checkout, the app calculates time, cafe items, eligible discounts, credit, payment, and change. Receipts and checkout records retain the result. A mistake is corrected through a controlled void/reversal path, not by erasing money history.
5. If a customer owes money, Receivables keeps a customer tab and payment history. A collection must appear in Daily Balance under its real payment method without being counted again as new checkout revenue.
6. Expenses and Payables record different events: an Expense is a cost already incurred/paid; a Payable is an amount owed with later settlement history. Recording the same payment in both places duplicates outflow.
7. At closing, staff/admin use Daily Balance, method reconciliation, dated reports, and physical cash counts. A report snapshot is not a replacement for the underlying transaction history.

These steps describe the intended product flow. Actual permissions and current UI should be verified in the routes, tests, and deployed build before changing operations.

## 3. Chronological work record

The dates below are historical evidence from Git and accessible chats, not a guarantee that each item remains active in today's production build. Commit IDs are entry points for `git show <id>`.

| Period | Work and decisions | Evidence/status |
| --- | --- | --- |
| Apr 28–May 1 | Initial Flask app, Vercel configuration, and Railway/MySQL connectivity. The old repository name still contains `vercelIdeahub`. | Early commits `a778341` through `4eae21d`; later deployment strategy changed. |
| May 7 | Refactored toward thin routes plus services and repositories, added migration/index scaffolding, improved mobile tables, separated migration/seeding startup behavior. | Phase 0–4 commits `d290400` through `b924dd1`. |
| May–June | Built out admin panel, menu, responsive UI, database changes, security fixes, and setup documentation. | Commits from `89dc2d8` through `5f84256`; use Git for exact diff. |
| July–August | Inventory/security work, MySQL performance tuning and indexes, connection pooling/pagination, deployment startup work, exact cash change, and menus. Earlier Render/Aiven/Vercel experiments were superseded. | Commits `111812e` through `8b1fda7`; production target later became Hostinger VPS. |
| Sept 7–11 | Prepared Hostinger VPS deployment with systemd, Nginx, Gunicorn, config/seeding, logging, bot defense, and billing/finance integration. The site was reported deployed September 9. | Commits `3852abc` through `56cb893`; [VPS guide](MD-Folders/VPS_DEPLOY_GUIDE.md). |
| Sept 12–13 | Added Cloudflare Access/Turnstile/R2 media integration and owner maintenance guidance. Reliability phases addressed failed Socket.IO upgrades, repeated requests, duplicate submissions, real-time authorization, and moved from Eventlet to threaded Gunicorn/simple-websocket. Created a **private** R2 backup bucket and interactive upload helper. Removed Git tracking from runtime database/uploads. | Commits `a2da1d0`, `e4e4676`, `c1331ad`; [maintenance runbook](MD-Folders/OWNER_MAINTENANCE_RUNBOOK.md). Past chat recorded VPS health and WebSocket 101. |
| Sept 14–15 | Added UI motion/loading skeletons and one-active-login-per-account enforcement with Redis. The database viewer experiment was removed. A previous chat reported single-session behavior active on VPS. | Commits `73c0cd1`, `3549a72`; [single-session plan](MD-Folders/SINGLE_SESSION_PLAN.md). |
| Sept 19–20 | Launched responsive promotional landing page, installable PWA, offline/update behavior, local SEO, sitemap/robots fixes, and Google Search Console steps. Security scans were reviewed without treating generic scanner alerts as proven breaches. | Commits `0676d1b` through `12ca188`; [PWA plan](MD-Folders/INSTALLABLE_PWA_PLAN.md). |
| Sept 21–24 | Extensive inventory iterations: recipe entry, stock and unit handling, menu availability, then the owner chose **manual meal servings separate from raw ingredient stock** for day-to-day operation. Added receivable tab collection, Whole Hub/booking updates, active-session tracking, and account-safe operational reset. Fixed hard-coded space IDs after reset. | Commits `e80dff7` through `1c2e1a6`; check current code before relying on intermediate plans because the inventory design changed more than once. |
| Sept 25–27 | Reconciled Daily Balance live totals, generated reports, breakdowns, and exports from dated financial records. Corrected mobile Daily Sales tables, inventory asset caching, discounts, inventory units/conversions and per-meal history. Drafted budget guidance. | Commits `4f0ebf6` through `e2e35ec`; [budget guide](MD-Folders/BUDGET_SPENDING_GUIDE_AND_PLAN.md). |
| Sept 28 | Added payment-method/funding decisions for Expenses and Payables; staff finance access; dated Receivables. A client-handoff cleanup was reported on the VPS: dummy activity removed while accounts/menu/spaces remained. **Do not rerun cleanup without new authorization and fresh backup.** | Commit `ff802a3`; [cleanup guide](MD-Folders/CLIENT_HANDOFF_DATA_CLEANUP.md). |
| Sept 29–30 | Added manual staff shifts, guarded cleanup, Food Orders without a lounge timer, checkout void corrections, one-person Regular/Premium Time In, meal daily servings audit, staff Inventory/finance flows, and POS updates. One prior chat recorded deployment of `ec9c2d8` on Sept 30 after an R2 backup. | Commits `0cc3130`, `057a7ea`, `ec9c2d8`. |
| Oct 1 | Fixed staff pages that failed to load data when real-time startup failed (`/staff/undefined/...` on an iPad). Preserved the one-device staff login rule. A prior chat recorded deployment of `eee1f8b` and ready health check. | Commit `eee1f8b`; live behavior still needs real-device recheck after any new release. |
| Oct 5–6 | Added Regular/Premium pause/resume, Cowork/Cafe split in Daily Balance, Manila-date checkout and staff-shift views, receivable customer suggestions and actor capture, and 24-hour staff reactivation. A separate uncommitted cash-box/owner-funding implementation started. | Committed `022f288`; cash-box work remains local as recorded on Oct 8. |
| Oct 7–8 | October 7 R2 database/files upload was size-verified. Code audit found financial and security defects. The user requested this full handoff and daily R2 guide. | Chat record and current working tree; no new VPS inspection was performed for this document. |

**Inventory design note:** Several September plans discuss recipe-derived servings and raw-ingredient deductions. Later requirements separated raw stock from manually entered meal serving counts. For a change today, inspect [inventory service](app/services/inventory_service.py), [order service](app/services/order_service.py), the latest tests, and the committed diff before adopting any older plan verbatim.

## 4. Current feature map and code map

| Area | User-visible behavior/history | Main places to inspect |
| --- | --- | --- |
| Application startup/config | Flask app factory, blueprint registration, SQLAlchemy, Socket.IO, security headers, startup checks. | [app factory](app/__init__.py), [config](config/config.py), [entry point](wsgi.py), [migrator](app/db/migrator.py). |
| Login, staff, and shifts | Admin/staff permissions, login leases, Active Sessions, 1-hour idle expectation, manual staff shift, deactivation/recovery. | [auth routes](app/routes/auth_routes.py), [admin routes](app/routes/admin_routes.py), [session leases](app/core/session_leases.py), [shift routes](app/routes/staff_shifts.py). |
| Customer time and space | Check-in, timed sessions, pause/resume, boardroom/whole-hub booking, walk-ins, cancellation. | [session routes](app/routes/session_routes.py), [session service](app/services/session_service.py), [booking service](app/services/booking_service.py), [billing](app/utils/billing.py). |
| Cafe POS and checkout | Menu, orders, modifiers, discounts, cash change, checkout/receipts, void corrections. | [order routes](app/routes/order_routes.py), [order service](app/services/order_service.py), [checkout-void tests](tests/test_checkout_void.py), [payment utilities](app/utils/payment.py). |
| Inventory | Raw stock, measurement units/conversions, daily meal servings, sold-out state, adjustment and order history. | [inventory routes](app/routes/inventory.py), [inventory service](app/services/inventory_service.py), [meal audit](app/services/meal_daily_audit.py), [inventory tests](tests/test_inventory_ui.py). |
| Debts and expenses | Customer receivable tabs/collections, supplier/owner payables, Expenses, source and method histories. | [receivable service](app/services/receivable_service.py), [payable service](app/services/payable_service.py), [expense service](app/services/expense_service.py). |
| Daily Balance | Dated ledger, live totals, generated/soft reports, method breakdowns, exports, cash-box work. | [sales repository](app/repositories/sales_repository.py), [sales service](app/services/sales_service.py), [balance routes](app/routes/sales_balance.py), [export service](app/services/daily_balance_export_service.py), [ledger tests](tests/test_daily_balance_ledger.py). |
| Public site/PWA | Landing page, contact draft, SEO, install/offline/update shell. | [templates](app/templates/), root `static/`, [PWA plan](MD-Folders/INSTALLABLE_PWA_PLAN.md). |
| Deployment/data safety | VPS service/Nginx, health checks, schema changes, uploads, R2. | [deployment guide](MD-Folders/VPS_DEPLOY_GUIDE.md), [owner runbook](MD-Folders/OWNER_MAINTENANCE_RUNBOOK.md), [R2 uploader](scripts/upload_backup_to_r2.py). |

The architecture is a modular Flask monolith: HTTP routes/controllers parse requests and enforce roles; services apply business rules; repositories query/store SQLAlchemy models; Jinja templates plus JavaScript render the screens. `app/__init__.py` wires the application. Tests use isolated SQLite and disable external services through [tests/conftest.py](tests/conftest.py). For a narrow change, run its focused pytest target. A change crossing several money domains needs the full suite and a ledger-to-Daily-Balance test.

Production-specific facts and limits:

- The **MySQL database** is the source of truth for sales, sessions, debts, expenses, payments, inventory, bookings, and staff records. Redis is temporary state, not a backup of those records.
- The VPS checkout may have local changes, especially production images and a config backup. Past deployment chats repeatedly preserved them before Git pulls. Do not run `git reset --hard` or overwrite them casually.
- `static/uploads` and `static/images` may contain VPS-local files. R2-hosted images in `ideaflow-media/menu/` are separate objects and are **not** captured by a tar of the VPS.
- Local SQLite development data and production MySQL data are different. A migration tested on SQLite still needs a careful MySQL preview/apply and production backup before deployment.
- A GitHub push changes repository code, not the running VPS. Check commit, migrations, service state, health, and an actual user flow after each deployment.

## 5. Money rules agreed with the owner

These rules are mandatory design constraints, not optional reporting polish:

- **Revenue** is the final amount of completed checkouts for a business day: cowork/time plus cafe minus checkout discounts. It is not profit and does not mean physical cash held. Refunds and voids need their own dated adjustments.
- A **receivable collection** is cash or digital value received today for an older debt. Its payment method affects today's collection and cash/method movement; it should not be counted a second time as a new sale.
- A **supplier payable payment** reduces the appropriate method balance when actually paid. Creating a payable records what is owed, not a cash outflow. Retain partial-payment history and remaining balance.
- An **Expense** is recorded once with real method, date, actor, funding source, and history. Recording the same purchase again as a Finance/Budget transaction causes duplicate Daily Balance outflow. The [budget guide](MD-Folders/BUDGET_SPENDING_GUIDE_AND_PLAN.md) documents this existing risk and a proposed budget-as-plan design; do not treat that proposal as shipped.
- **Petty cash** and **Customer cash** are two physical boxes in the local uncommitted work. Enter an opening count for each box only for money physically there at tracking start. For example, ₱300 in petty and ₱0 in customer means ₱300 total, not ₱600. Opening count is not revenue or today's inflow. Unused cash carries forward.
- Owner top-ups add to a cash box but are **not sales**. Each top-up asks whether the business must repay the owner. If yes, create one linked owner payable; later reimbursement pays that payable once rather than creating another Expense. A cash withdrawal is not automatically an Expense.
- Cash checkouts and cash debt collections go to Customer cash. A cash Expense/Payable chooses Petty or Customer cash; an owner-paid-direct Expense leaves business cash boxes unchanged. Historic entries lacking a box must remain “unknown,” not be guessed.
- Live Daily Balance, payment breakdown, saved reports, CSV/PDF/Excel, and filters must use the same ledger records and Asia/Manila business-day boundaries. Backdated entries should retain actual entry time and explain any difference from earlier report snapshots. The [cash-box plan](MD-Folders/PETTY_CASH_CASH_BOXES_OWNER_FUNDING_PLAN.md) gives worked examples and tests.
- Every money action must retain an audit trail that can be opened from its relevant screen: amount, method, business date/time, actor, related customer/order/session/booking/account, and enough before/after or remaining-balance detail to explain the result. Retries must not make duplicate financial records.

## 6. Deployment and owner operating pattern

The observed safe release sequence is: inspect Git and CI; confirm the exact commit to deploy; inspect VPS-only changes; take and verify a fresh off-VPS backup; schedule a low-traffic window; fast-forward the exact release; run required migration with the real production DB; restart; verify both health endpoints and a real workflow; watch errors. See the [owner runbook](MD-Folders/OWNER_MAINTENANCE_RUNBOOK.md) for the full checklist. Do not infer that a Git commit is on the VPS merely because it is on `master`.

Useful read-only VPS checks after SSH:

```bash
cd /var/www/pos
git status --short --branch
git rev-parse --short HEAD
sudo systemctl is-active ideahub nginx mysql redis-server
curl --fail --silent --show-error http://127.0.0.1:5000/health/live
curl --fail --silent --show-error http://127.0.0.1:5000/health/ready
sudo journalctl -u ideahub --since '15 minutes ago' --priority warning --no-pager
```

The service can report `active` before Gunicorn is ready to answer HTTP. Retry the health endpoints after a short startup interval before diagnosing a failure. The public site, authenticated staff path, Daily Balance data, checkout, and a known media image are the practical checks after an update. Never paste the real `.env` or credentials into a chat to troubleshoot.

## 7. Open work and risks as of October 8

### Local uncommitted cash-box/owner-funding work

The main checkout currently has 27 modified tracked files and seven untracked files for cash-box events, routes, service, UI, tests, Expense/Payable source fields, and Daily Balance/export changes. The [plan](MD-Folders/PETTY_CASH_CASH_BOXES_OWNER_FUNDING_PLAN.md) says “implemented locally.” One accessible chat reported a full test run with 285 passes during that implementation, followed by further corrections; **this guide did not rerun tests or inspect a live deployment**. Before committing or deploying, review the whole diff and the plan's acceptance cases, run focused tests and the full suite, and verify a fresh production backup and MySQL migration path. Do not discard this working tree to “clean up” the repo.

### October 7 local code audit

An audit in a separate chat reported these findings against the then-current local working tree. They should be reproduced against the exact revision being fixed and checked against the VPS commit before claiming a live impact:

1. **Stored XSS path (high):** staff-saved menu text reached Analytics `innerHTML`; menu HTML/attribute interpolation had related sinks. Render user text safely and test the route-to-browser path.
2. **Invalid payment method becomes cash (high):** [payment normalization](app/utils/payment.py) still visibly falls back to `cash` for an unknown explicit value such as `gcsh`. Reject an invalid submitted method instead of misclassifying the ledger entry.
3. **Analytics versus Daily Balance day/revenue mismatch (high):** Analytics grouped naive UTC dates while Daily Balance uses Manila dates and its own void handling; a synthetic case showed ₱10 versus ₱110 for one Manila day. Reuse the same ledger rules.
4. **Still to Collect overstates active-session debt (medium):** retained customer credit was not deducted from an active bill; a ₱10 bill with ₱50 credit showed ₱10 to collect while checkout shortfall was ₱0.
5. **Repeated Daily Balance ledger scans (medium performance):** a 15-second poll made overlapping dated ledger queries. Reuse one request's result before considering a more complex balance checkpoint; measure impact on production-sized data.

Two more risks need targeted checks: concurrent boardroom booking requests might pass the overlap check before either commits, and a receivable due-date query used server-local `date.today()` rather than Manila date. The audit did not prove those two in production. The scanner overview later reported two medium/other alerts but did not include the actual finding evidence; it was not proof of a breach. See [security analysis](MD-Folders/ANALYSIS_SUMMARY.md), but treat older audit documents as leads to verify, not automatically current defects.

### Other status boundaries

- A separate staff-account chat discussed additional reactivation UI and Sentry changes in another checkout. The committed `022f288` already contains staff recovery; reconcile each worktree and `git status` before assuming the extra changes are in this main checkout or in production.
- A manual R2 backup path is documented and was used. This repository does **not** contain a scheduled backup timer/service. The actual VPS could have one added outside Git; inspect `systemctl list-timers --all` and `sudo crontab -l` before adding another.
- The budget proposal, some design plans, and older inventory plans remain planning/reference documents. Read the current code and latest tests before implementing or describing their status.
- Local test success does not verify the iPad, cash drawer count, live MySQL migration, Cloudflare configuration, or a successful restore. Record those observations separately.

## 8. Backup scope: what a daily copy must protect

A “daily backup” means a **complete snapshot taken today**, not only records entered today. Keep each dated backup separate so an error discovered later can be recovered from an earlier point.

| Data | Where it lives | Current manual procedure below | Remaining protection |
| --- | --- | --- | --- |
| Sales, customers, sessions, bookings, stock, debts, payments, staff | Production MySQL `pos_db` | `mysqldump` to `pos_db.sql`, uploaded to private `ideaflow-backups` | Restore test; daily scheduling/alerts if desired. |
| VPS-local uploads and images | `/var/www/pos/static/uploads`, `/var/www/pos/static/images` | `production-files.tar.gz`, uploaded beside SQL | Confirm any other runtime file paths before calling the file set complete. |
| Menu media served from Cloudflare | `ideaflow-media/menu/` | **Not included** by the SQL dump or VPS tar | Separate dated copy/export of the media bucket; test a sample restore. |
| Application code and migrations | Git repository / deployed commit | Git history, **not** included in the two-file uploader | Keep GitHub/repository access and know the deployed commit. |
| Runtime configuration and secrets | VPS `.env`, systemd/Nginx configuration, password manager | Deliberately **not** uploaded by the manual helper | Maintain a separate secure recovery record; never commit or put secrets in a public R2 bucket. |
| Redis sessions/cache | VPS Redis | Not backed up as business data | Users may need to log in again after recovery; MySQL is authoritative. |

The existing two-file backup is valuable, but it is **not a full account-level disaster recovery copy** while R2-hosted media and secure configuration recovery are separate. Keep Hostinger's independent VPS backup enabled. A second copy outside the same Cloudflare account is preferable for protection from account-level mistakes or compromise.

## 9. How to make and upload today's backup to Cloudflare R2

This is the current **manual** procedure that matches the existing [uploader](scripts/upload_backup_to_r2.py) and the successful October 7 flow. Run Linux blocks **inside your SSH session on the VPS**, not in Windows CMD/PowerShell. Schedule it after closing or at a quiet time. It does not require stopping the app for ordinary InnoDB writes, but do not run it during a schema migration or bulk data reset. MySQL documents that `--single-transaction` gives a consistent InnoDB snapshot while concurrent DDL can break it: [mysqldump reference](https://dev.mysql.com/doc/refman/8.4/en/mysqldump.html).

### 9.1 One-time Cloudflare setup or check

1. Sign in to the **correct Cloudflare account**. Open **R2 object storage**. Confirm the private bucket `ideaflow-backups` exists and public access is **off**. This is separate from the public/media bucket `ideaflow-media`. If the backup bucket is missing, create it in R2 before continuing.
2. In R2, open **Manage R2 API tokens** and create a token with **Object Read & Write** scoped only to `ideaflow-backups`. Keep its Access Key ID and Secret Access Key in a password manager. Cloudflare shows the secret only when the token is created. The backup helper needs read as well as write because it calls `head_object` after upload. [Cloudflare CLI setup](https://developers.cloudflare.com/r2/get-started/cli/) and [R2 token guide](https://developers.cloudflare.com/r2/api/tokens/).
3. Record the account's **S3 endpoint** in the password manager: `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`. Use the endpoint, not the public media URL, in the uploader. Never paste the endpoint together with the secret into chat, a shell command, or Git.
4. Confirm `/var/www/pos/venv/bin/python` can run [the uploader](scripts/upload_backup_to_r2.py). `boto3` is in [requirements.txt](requirements.txt). If the helper is missing on the VPS, check the deployed commit rather than copying an unreviewed script into production.
5. A bucket and token alone do **not** schedule backups. Check R2 Objects for a recent dated prefix and keep the daily procedure below until a job is actually installed, logged, and tested.

### 9.2 Connect and identify the live system

From your own computer, use your usual SSH identity and host. Do not share a password or private key:

```text
ssh <your-vps-user>@<your-vps-host>
```

After the prompt changes to the VPS, run:

```bash
cd /var/www/pos
pwd
git rev-parse --short HEAD
sudo systemctl is-active ideahub mysql
df -h /var/backups /var/www/pos
```

Stop if `/var/www/pos` is not the application checkout, MySQL is not active, or the disk cannot hold a database dump plus image archive. If the live DB name or path has changed, verify it **without printing the database password** and update the commands before proceeding. The rest of this section assumes the previously verified `pos_db` setup.

### 9.3 Create a unique private folder labeled in Manila time

Stay in the **same SSH shell** for the following commands: `backup_dir` is a shell variable. If you disconnect, use the exact directory path printed below rather than expecting the variable to persist.

```bash
sudo install -d -m 700 /var/backups/ideaflow
backup_dir="$(sudo mktemp -d "/var/backups/ideaflow/daily-$(TZ=Asia/Manila date +%Y%m%d-%H%M%S)-XXXXXX")"
echo "BACKUP DIRECTORY: $backup_dir"
```

`mktemp` makes a new folder for every run, so a retry does not overwrite yesterday's backup. The Manila timestamp labels the business date even if the VPS clock uses UTC.

### 9.4 Export the MySQL database

Use the root socket-auth form below **if `sudo mysqldump` works on this VPS** (it did in the October 7 recorded run):

```bash
sudo bash -c 'umask 077; mysqldump --single-transaction --routines --triggers --events --hex-blob --no-tablespaces --result-file="$1/pos_db.sql" pos_db' _ "$backup_dir"
echo "DUMP EXIT: $?"
```

If root socket authentication is unavailable, use the database account **instead of rerunning with a made-up password**. This variant prompts for the `pos_user` password without putting it in shell history:

```bash
sudo bash -c 'umask 077; mysqldump --single-transaction --routines --triggers --events --hex-blob --no-tablespaces -u pos_user -p --result-file="$1/pos_db.sql" pos_db' _ "$backup_dir"
echo "DUMP EXIT: $?"
```

Use only **one successful variant**. Stop if `DUMP EXIT` is not `0`; a partial `.sql` file may still exist after failure. Do not upload it. Do not run a migration, `ALTER TABLE`, data reset, or cleanup while the dump is running.

### 9.5 Archive changing VPS files

The October 7 backup included both local uploads and site images. First confirm the paths exist, then archive them:

```bash
sudo test -d /var/www/pos/static/uploads && sudo test -d /var/www/pos/static/images && sudo tar -C /var/www/pos -czf "$backup_dir/production-files.tar.gz" static/uploads static/images
echo "TAR EXIT: $?"
```

Stop if either directory is missing or `TAR EXIT` is not `0`. Determine the current runtime file locations instead of silently creating an empty archive. After a successful tar, restrict both files:

```bash
sudo chmod 600 "$backup_dir/pos_db.sql" "$backup_dir/production-files.tar.gz"
```

R2 media objects are a separate backup task in section 9.9.

### 9.6 Verify the local files before uploading

```bash
sudo stat -c '%n: %s bytes' "$backup_dir/pos_db.sql" "$backup_dir/production-files.tar.gz"
sudo test -s "$backup_dir/pos_db.sql" && echo 'DATABASE FILE: NON-EMPTY'
sudo test -s "$backup_dir/production-files.tar.gz" && echo 'FILES ARCHIVE: NON-EMPTY'
echo "TABLE DEFINITIONS: $(sudo grep -c '^CREATE TABLE' "$backup_dir/pos_db.sql")"
echo "DATA SECTIONS: $(sudo grep -c '^INSERT INTO' "$backup_dir/pos_db.sql")"
echo "ARCHIVE ENTRIES: $(sudo tar -tzf "$backup_dir/production-files.tar.gz" | wc -l)"
sudo sha256sum "$backup_dir/pos_db.sql" "$backup_dir/production-files.tar.gz"
```

Both files must be nonempty; table definitions and archive entries should be greater than zero. The SQL `INSERT` count is a useful clue, not a substitute for a restore test; a sparse but valid database can have fewer data sections. Compare counts with the previous known-good backup and investigate large unexpected changes. Record the date, directory, sizes, counts, and SHA-256 hashes in the maintenance log. Do **not** paste the SQL itself or customer data into chat.

### 9.7 Upload to the private R2 bucket

```bash
cd /var/www/pos
sudo venv/bin/python scripts/upload_backup_to_r2.py "$backup_dir"
```

At the prompts, enter the S3 endpoint, backup-bucket Access Key ID, and Secret Access Key. The secret is entered invisibly. The script uploads only `pos_db.sql` and `production-files.tar.gz` under a prefix equal to the backup folder's name. It then asks R2 for each object's size. Success is exactly two `UPLOADED AND VERIFIED` lines followed by `DAILY R2 BACKUP COMPLETE`.

If either upload fails, keep the local files and retry after fixing the network, token, or bucket issue. A partially uploaded prefix is **not** a completed backup. The helper's size check does not prove cryptographic identity or restorable SQL.

### 9.8 Confirm in Cloudflare and record it

Open Cloudflare Dashboard → **R2 object storage** → **`ideaflow-backups`** → **Objects**. Open today's `daily-YYYYMMDD-HHMMSS-XXXXXX/` prefix. Confirm exactly the two expected names and nonzero sizes matching `stat` and the uploader output. Keep the bucket private. Record the outcome in [the maintenance log template](MD-Folders/OWNER_MAINTENANCE_RUNBOOK.md#13-maintenance-log-template). Do not delete the VPS copy solely because the upload finished.

For comparison, the October 7 record was:

| Object | Size | Local SHA-256 recorded in chat |
| --- | ---: | --- |
| `daily-20261007-K7iXmi/pos_db.sql` | 210,528 bytes | `7e02c97602711b17d5555ff6f20cdf21f9bbb8e83ea549b0797118987df44e5d` |
| `daily-20261007-K7iXmi/production-files.tar.gz` | 17,989,876 bytes | `a7d3584ea8944fbe354c0cf929e4cda12c2ce49f2d12590d1189a0f53835e63b` |

Those are **historical example values**, not expected sizes or checksums for later days. The recorded checks found 33 table definitions, 25 data sections, and 132 archive entries. The October 7 upload was size-verified, not a documented download-and-restore test.

### 9.9 Back up R2-hosted menu media separately

The app's `ideaflow-media/menu/` images live in R2, so neither the MySQL dump nor `static/uploads` tar includes them. To make a recovery copy, arrange a dated **copy**, not a destructive sync, from `ideaflow-media/menu/` to a private backup destination. Cloudflare documents [rclone for bulk R2 operations](https://developers.cloudflare.com/r2/examples/rclone/).

A safe future operator workflow is:

1. Configure an rclone **read-only** remote for `ideaflow-media` and a separate **read/write** remote for `ideaflow-backups`, each with a token limited to its bucket. Protect the rclone config; it contains secrets. Do not reuse the public site's media-upload key for the backup job.
2. Copy `menu/` into a date-specific path such as `media-20261008/menu/` in the private bucket. `rclone copy` does not delete older destination objects; avoid `rclone sync` for historical backups.
3. Compare source/destination counts and sizes, download a sample image, and check it opens. Keep at least one copy outside the Cloudflare account for account-level recovery.
4. Add the media result to the same daily maintenance record. Only then call the day's **database + local files + R2 media** backup complete.

After those two remotes are configured and tested, the copy and count commands would be:

```bash
media_day="$(TZ=Asia/Manila date +%Y%m%d)"
rclone copy media-read:ideaflow-media/menu/ "backup-write:ideaflow-backups/media-$media_day/menu/" --progress
rclone size media-read:ideaflow-media/menu/
rclone size "backup-write:ideaflow-backups/media-$media_day/menu/"
```

`media-read` and `backup-write` are example rclone remote names. Check their endpoint, bucket scopes, and config-file permissions before running the block. An empty source or mismatched count needs investigation, not a success entry.

This extra media copy is **not** performed by `scripts/upload_backup_to_r2.py`, and this document did not configure rclone or execute the copy. If the media bucket is small, the Cloudflare dashboard can be used to inspect or download individual objects, but a repeatable bulk workflow is needed for dependable daily coverage.

## 10. How to know a backup can actually restore

The most important proof is a restore into a **separate, private test environment**, never straight over `pos_db`. The [owner runbook](MD-Folders/OWNER_MAINTENANCE_RUNBOOK.md#10-backup-and-restore-policy) calls for a quarterly drill. Do one before relying on any new automatic retention rule.

1. Pick a dated R2 prefix in `ideaflow-backups`. Download `pos_db.sql` and `production-files.tar.gz` from the private Cloudflare dashboard to a secure machine, or use a bucket-scoped CLI with read permission. Cloudflare documents [R2 downloads](https://developers.cloudflare.com/r2/get-started/cli/). Keep customer/staff data private.
2. Compare each downloaded file's SHA-256 with the hash recorded when the backup was made. On Windows PowerShell: `Get-FileHash -Algorithm SHA256 .\pos_db.sql` and similarly for the tar. On Linux: `sha256sum pos_db.sql production-files.tar.gz`. If the recorded hashes are unavailable, document that full remote integrity was not verified; at least compare sizes and test readability.
3. Check the archive without extracting over production: `tar -tzf production-files.tar.gz | head`. It should list expected `static/uploads/` and `static/images/` paths. Extract it only into a temporary test directory when testing file recovery.
4. In an **isolated test MySQL instance**, create a new, uniquely named database. Before import, inspect the SQL for `CREATE DATABASE`/`USE` statements; the documented `mysqldump pos_db` form normally targets the database selected on import, but a different dump option could change that. A sample using an admin account with local socket access is below. Replace the date in the test database name with the drill date, confirm it does not already exist, and run it only on the test instance:

   ```bash
   grep -nE '^(CREATE DATABASE|USE )' pos_db.sql | head
   sudo mysql -e 'CREATE DATABASE ideaflow_restore_20261008 CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;'
   sudo mysql ideaflow_restore_20261008 < pos_db.sql
   sudo mysql -D ideaflow_restore_20261008 -e 'SHOW TABLES;'
   ```

   If that first check shows a production `USE pos_db` directive, stop and prepare a different isolated restore method. A test-only MySQL account with suitable privileges can be used in place of `sudo mysql`.
5. Verify tables and representative counts: `transactions`, orders, receivable payments, payable payments, expenses, bookings, and inventory. Compare with counts recorded at backup time, allowing for the exact snapshot moment. Run the application against that test DB only if its secrets and outbound integrations are disabled.
6. Record date, backup prefix, checksum results, table/count results, who tested it, and any failure. Retain the last known-good backup until a newer one has passed this drill. Plan an actual production restore separately, with downtime and rollback, if ever needed.

Do not rely on the SQL file being nonempty, `head_object` returning the right size, or a successful upload banner as proof of restorable business history. A real restore also needs code at a compatible migration level and access to any required media and configuration.

## 11. Daily automation, retention, security, and cost

### What exists now

The repository's [uploader](scripts/upload_backup_to_r2.py) prompts interactively for credentials, so putting that exact command in cron/systemd would hang. The runbook describes automation as planned. Before creating a job, inspect the VPS for an existing timer/cron entry and recent logs so two jobs do not overlap or produce misleading success records.

### What an automatic job must do before it can replace the manual routine

1. Run once per Manila business day after closing, plus a fresh backup before deployments or destructive migrations. Use a unique immutable-looking prefix per run; never overwrite the only good backup.
2. Acquire a lock so two backups cannot run together. Check disk space. Dump MySQL and archive local files with root-only permissions. Fail immediately on any command error or empty/invalid output.
3. Obtain a narrowly scoped backup-bucket token from a protected, root-readable secret file **outside Git**, or another secure secret store. Never put credentials in a unit file, shell history, logs, or this guide. A noninteractive uploader is required; the current prompt-based helper is for manual use.
4. Upload and verify both objects remotely. Preserve checksums in a manifest or log and periodically download to verify them. Add the separate R2-media copy path if the goal is full operational recovery.
5. Log a clear success/failure with backup prefix, sizes, and timing, without logging secrets or customer rows. Alert the owner when a daily run fails or no successful backup exists for the expected business day.
6. Install a systemd service/timer (or one understood cron job), enable it, run it manually once, verify the R2 objects, then observe the next scheduled run. Test recovery before ending the manual routine.

### Retention and deletion

The runbook proposes **at least 30 days of daily database backups** and quarterly restore drills. This is a target, not confirmation that a rule is configured. In Cloudflare R2, open `ideaflow-backups` → **Settings** → **Object Lifecycle Rules** → **Add rule** to set an expiry only after deciding the desired retention and checking a restore; Cloudflare's [lifecycle guide](https://developers.cloudflare.com/r2/buckets/object-lifecycles/) describes the current UI. A [bucket lock](https://developers.cloudflare.com/r2/buckets/bucket-locks/) can prevent overwrite/deletion for a chosen period and takes precedence over lifecycle expiry. Configure a lock carefully because it also blocks intended cleanup during that period. Never apply a short expiry to every backup prefix before verifying that longer-term recovery points are protected. Keep Hostinger's separate weekly backup and, ideally, an off-Cloudflare copy.

Cloudflare R2 bills for storage and operations after its included allowance; check [current official pricing](https://developers.cloudflare.com/r2/pricing/) and bucket usage before setting retention. The October 7 two-file example was about 18 MB, so thirty copies of that same size would be roughly 0.54 GB **before growth, media copies, older backups, and other bucket use**. Actual usage and pricing can differ. [R2 encrypts stored objects and transfer](https://developers.cloudflare.com/r2/reference/data-security/), but this manual process does **not** add client-side encryption; keep the backup bucket private, scope tokens, and consider separate encryption before storing sensitive SQL long term.

## 12. Troubleshooting the daily backup

| Symptom | Meaning / next check |
| --- | --- |
| `mysqldump: Access denied` | Confirm the live DB name and the account method. Use the prompted `pos_user` variant if root socket auth is unavailable; do not put a password on the command line. |
| `DUMP EXIT` nonzero | Treat that SQL file as incomplete. Keep it for diagnosis if needed but do not upload it as a valid backup. Fix the cause and create a **new** dated folder. |
| `tar: Cannot stat` or archive count 0 | Production file paths changed or are missing. Identify the actual upload/image paths; do not silently accept a partial file backup. |
| Filesystem full | Free space only after preserving verified backups and identifying the files. Do not delete the only local recovery point. |
| R2 `AccessDenied` | Check token's bucket scope and Object Read & Write permission. Do not use the media bucket token or make the backup bucket public. |
| Uploader prints one success line then fails | One R2 object may exist, but the daily prefix is incomplete. Keep local files, fix the issue, and retry; verify **both** names and sizes. |
| File sizes match but checksum differs after download | Treat the remote copy as failed/corrupt or mismatched. Recheck the exact prefix and local source, then investigate before relying on it. |
| Service `active` but health check fails after deployment | Allow Gunicorn startup time, retry, then inspect `journalctl -u ideahub` and MySQL state. Backup success alone does not prove the app is healthy. |

## 13. Starting checklist for the next AI

1. Read [AGENTS.md](AGENTS.md) and follow its financial-audit rule. For coding in this repo, use the `ponytail` skill; for an explicit code review use the repository's `ponytail-review-code` skill.
2. Run `git status --short --branch`, `git log -1 --oneline`, and inspect the **relevant** code and callers. Preserve the current uncommitted cash-box work and any other worktree. Do not assume the status recorded in this file remains current.
3. Identify whether the request concerns local code, GitHub, VPS deployment, Cloudflare settings, or live business data. Confirm the exact environment before changing it.
4. For financial work, trace route → service → repository/model → history screen → `daily_ledger` → live Daily Balance → report/export, including payment method, Manila date, refunds, voids, and retry behavior. Add a focused ledger-to-Daily-Balance test.
5. For a release, verify tests and CI, take an off-VPS backup, inspect VPS-local files, apply only the needed migration, and verify health and a real user flow. A backup should have a restore drill, not just an upload banner.
6. Keep documentation status labels accurate: **plan / implemented locally / committed / pushed / deployed / verified on device**. Update this file with dated evidence when those states change.

## 14. References to read next

### Repository

- [README and local setup](README.md)
- [AGENTS working agreements](AGENTS.md)
- [Owner maintenance runbook](MD-Folders/OWNER_MAINTENANCE_RUNBOOK.md)
- [VPS deployment guide](MD-Folders/VPS_DEPLOY_GUIDE.md)
- [Staff quick start](MD-Folders/STAFF_QUICK_START.md)
- [Technical architecture](MD-Folders/technicalguide.md)
- [Security notes](MD-Folders/SECURITY.md) and [performance/reliability plan](MD-Folders/PERFORMANCE_RELIABILITY_PLAN.md)
- [Cash boxes and owner funding plan](MD-Folders/PETTY_CASH_CASH_BOXES_OWNER_FUNDING_PLAN.md)
- [Budget Spending behavior and plan](MD-Folders/BUDGET_SPENDING_GUIDE_AND_PLAN.md)
- [R2 upload helper](scripts/upload_backup_to_r2.py)
- [Migration runner](app/db/migrator.py) and [isolated tests](tests/conftest.py)

### Official operational references checked October 8, 2026

- [Cloudflare R2 CLI, bucket/token, uploads and downloads](https://developers.cloudflare.com/r2/get-started/cli/)
- [Cloudflare R2 API token permissions](https://developers.cloudflare.com/r2/api/tokens/)
- [Cloudflare R2 rclone bulk copy](https://developers.cloudflare.com/r2/examples/rclone/)
- [Cloudflare R2 lifecycle rules](https://developers.cloudflare.com/r2/buckets/object-lifecycles/)
- [Cloudflare R2 bucket locks](https://developers.cloudflare.com/r2/buckets/bucket-locks/)
- [Cloudflare R2 pricing](https://developers.cloudflare.com/r2/pricing/)
- [Cloudflare R2 data security](https://developers.cloudflare.com/r2/reference/data-security/)
- [MySQL `mysqldump` reference and `--single-transaction` limits](https://dev.mysql.com/doc/refman/8.4/en/mysqldump.html)

### Accessible chat topics used as historical evidence

The accessible Codex chats covered codebase exploration, VPS-only conversion, security and reliability phases, PWA/SEO, inventory iterations, Daily Balance/finance reconciliation, September and October deployment verification, October 7 backup, cash-box design/prototype, staff recovery, and the October 7 audit. The repository's Git history and documents filled earlier gaps. This file deliberately excludes unrelated personal chats and any credentials that appeared in past conversation text.
