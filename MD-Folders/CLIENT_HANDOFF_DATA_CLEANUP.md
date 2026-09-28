# Client handoff: clear demo activity, keep business setup

## Decision and scope

Use `app.db.reset_demo_data` for this handoff. **Do not use** `app.db.reset_operational_data --execute`: that older full reset removes menu items, inventory definitions, spaces, and custom prices.

The handoff reset keeps every admin and staff account, configured spaces and current rates, space price history, menu items/categories/ingredient definitions/images, inventory item definitions/units/reminders, and budget names. It does not alter application code or business workflows.

It deletes demo customer sessions, orders, sales, discounts recorded on those sales, bookings and booking history, expenses, receivables and payments, payables and payments, daily balance reports, staff time records, inventory movement logs, and other activity records. It sets **every inventory stock quantity and budget amount to zero** so staff can enter actual opening amounts. Menu items with stock-based availability may show as sold out until real stock or servings are entered. Uploaded files in local storage or R2 are left untouched.

The command cannot tell dummy records from real records. Review the preview, especially active sessions and upcoming bookings, before proceeding. This cleanup is for the one-time pre-client handoff only.

## Before the cleanup window

1. Make and verify a database backup before deploying or migrating. Deploy the current code, including `app/db/reset_demo_data.py`, and run `sudo venv/bin/python -m app.db.run_migrations` in `/var/www/pos`. The new manual staff-shift table must exist before preview can pass. Verify the normal app pages work.
2. Choose a quiet period before the client starts entering real data. Tell all staff to log out. Review active sessions on the Dashboard and every future reservation in Space Bookings; do not post customer details in chat. Record the current space rates, menu item count, staff account count, and any opening quantities the client will need to enter afterward.
3. Rehearse the procedure on a restored copy of the database if one is available. Do not run the execute command on production as a rehearsal.

## Production window

1. Stop writes: `sudo systemctl stop ideahub`.
2. Create and verify a **fresh** MySQL dump and an archive of uploaded files using the backup procedure in [OWNER_MAINTENANCE_RUNBOOK.md](OWNER_MAINTENANCE_RUNBOOK.md). Keep the backup outside the web root. Check the dump exit status, nonzero file size, table definitions, and archive contents. Keep the backup for rollback; do not send database credentials in chat.
3. From `/var/www/pos`, run the preview only:

   ```bash
   sudo venv/bin/python -m app.db.reset_demo_data
   ```

   Confirm the database is `pos_db`. Review every `KEEP`, `DELETE`, `KEEP ITEMS; ZERO STOCK`, and `KEEP BUDGETS; ZERO AMOUNTS` line. Record the printed **Activity rows to delete** number. If the schema check fails or a count looks wrong, stop. If active sessions or bookings today or later are listed, confirm each is demo data before using the matching confirmation flag.
4. Only after the backup and preview are checked, replace `YOUR_PREVIEW_COUNT` with the exact printed number and run:

   ```bash
   sudo venv/bin/python -m app.db.reset_demo_data --execute --expect-database pos_db --expect-delete-rows YOUR_PREVIEW_COUNT
   ```

   Add `--confirm-active-sessions` only for reviewed demo sessions. Add `--confirm-future-bookings` only for reviewed demo bookings. A changed row count or wrong database name stops the reset. The deletes and balance updates commit together; a failure rolls them back.
5. Run the preview again. All `DELETE` counts, `Inventory items with nonzero stock`, and `Budgets with nonzero amounts` should be zero. Account, space, menu, and inventory-item counts should match the first preview. Then start the service:

   ```bash
   sudo systemctl start ideahub
   curl -fsS http://127.0.0.1:5000/health/ready
   ```

6. Sign in as an existing account and check the configured spaces/prices and menu. Check that checkout, bookings, expenses, receivables, payables, and Daily Balance start empty. Enter real opening stock and budget amounts before the client uses those features.

Record the backup location, pre/post counts, operator, and cleanup time in the maintenance log in [OWNER_MAINTENANCE_RUNBOOK.md](OWNER_MAINTENANCE_RUNBOOK.md).

## If a check fails

Keep the site closed to new activity and use the verified pre-reset backup to restore. Once the client starts recording real activity, restoring the old dump would overwrite that new work, so investigate before any restore.

**Status:** Cleanup command prepared and tested locally. No production data has been reset.
