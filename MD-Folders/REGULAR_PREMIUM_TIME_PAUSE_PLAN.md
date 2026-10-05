# Regular and Premium customer time pause

**Week of October 5, 2026 · Status: implemented locally.** Production requires deployment and the schema migration before this feature can be used there.

## Goal and confirmed behavior

- Staff and admin can pause and resume the **time charge** for an active Regular Lounge or Premium Lounge customer from the Dashboard action area, on desktop and mobile.
- A paused customer stays checked in and occupies the same seat. Staff can still add and view food orders. Food charges and inventory actions work exactly as before.
- The clock may show elapsed visit time, but a separate **billable duration** and the displayed time bill must stop increasing while paused. Resume continues from the accumulated billable duration; it does not start a new first-hour block.
- Boardroom, Whole Hub, and food-only sessions have no Pause control. A completed or cancelled visit cannot be paused or resumed.
- A checkout while paused uses the time charge frozen at the pause point plus all placed food orders. It closes the visit without requiring a resume click.
- Pause and resume each show a short **Yes/No confirmation** naming the customer. No reason is required or requested.

## Current flow to preserve

- `app/models/customer_session.py` stores a UTC `time_in`, `time_out`, status, service mode, and space. It has no pause state.
- `app/services/session_service.py` calculates a live bill in `get_active_sessions_view`, a preview in `preview_checkout`, and the final charge in `checkout`. `app/routes/sales_balance.py` separately estimates active-session bills for **Still to Collect**. These paths must call one shared billable-duration calculation, or the Dashboard, checkout, and Daily Balance will disagree.
- `app/utils/billing.py::calculate_time_bill` implements started billing blocks: Regular first hour ₱10 then ₱5 per started half-hour; Premium first hour ₱20 then ₱10 per started half-hour. Keep that pricing function and pass it the accumulated **active** minutes.
- `app/templates/dashboard.html` renders both desktop rows and mobile cards. Put the action next to Add Order/View Order in both renderers. `app/dto/serializers.py::serialize_transaction` and `app/routes/receipts.py` currently derive duration from wall-clock Time In/Out; update their displayed duration when pauses exist.

## Data and audit design

1. Add nullable `paused_at` (UTC) and an accumulated paused-duration field to `customer_sessions`. Keep `status='active'` during a pause so seat occupancy and orders remain valid. Never move `time_in` forward to simulate a pause: that would corrupt the visit and historical checkout dates.
2. Add a small append-only pause/resume history table linked to `customer_sessions`. Each row records action, actual UTC time and Manila business date, authenticated actor ID/name/role, and the effective billable duration and time bill before/after the action. No reason field is needed. Include a final close event or enough persisted pause state to explain checkout while paused. Show these entries in a reachable visit/checkout history view; a financial adjustment cannot exist only in a hidden database row.
3. Snapshot **billable seconds** (and, if needed, paused seconds) on the checkout `Transaction`. Existing `Transaction.time_bill`, `food_bill`, discounts, total, method, actor, and created time remain the financial history source. Old transactions without this snapshot use their existing wall-clock duration; do not rewrite old charges.
4. Make an idempotent migration in `app/db/migrator.py` for the added columns/table, with zero accumulated pause as the default. Register the model in `app/models/__init__.py`. Add the new operational table to the existing demo-reset inventory if appropriate; never touch production history during deployment.

## Server work

1. Add staff/admin-only `POST /api/sessions/<id>/pause` and `POST /api/sessions/<id>/resume` in `app/routes/session_routes.py`. Use the existing CSRF and idempotency pattern, and the authenticated session actor. Do not accept actor, amount, or timestamp from the browser.
2. In `SessionService`, lock the customer session row before a transition. Require active timed Regular/Premium, reject an already-paused pause or an unpaused resume with `409`, and return the new state. A concurrent checkout or second device action must leave one valid transition and one consistent bill.
3. Compute billable elapsed time as wall time from Time In to the earlier of `now` or `paused_at`, minus accumulated completed pauses, clamped at zero. On resume, add the just-ended pause exactly once and clear `paused_at`. During checkout while paused, include the final pause interval through checkout in persisted paused duration but charge only through the pause instant. Use the same effective duration for the live session, checkout preview, checkout transaction, receipt, and Daily Balance active estimate.
4. Leave order placement and stock deduction unchanged while paused. Keep seat occupancy unchanged. Do not create a sale or cash movement merely by pausing; Daily Balance recognizes the final paid checkout once.
5. Return pause state, pause start, billable seconds, and current time bill from `/api/active-sessions`. Check error responses for missing, stale, completed, and unauthorized sessions; never render a failed API response as an empty customer list.

## Screen behavior

- Show **Pause time** when running and **Resume time** when paused, with a visible **Paused** badge and frozen time bill. Use accessible button labels that include the customer name; disable the button while a request is in flight.
- Show elapsed visit time and billable duration with clear labels, or show only billable duration beside the bill. Avoid displaying an increasing duration beside a frozen charge without explaining the pause.
- Before pausing, ask **“Pause the time bill for [customer]?”** with Yes/No. Before resuming, ask **“Resume the time bill for [customer]?”** with Yes/No. Use an accessible confirmation dialog; No leaves the visit unchanged. Show who paused/resumed and when in the visit history. The order buttons and checkout button remain usable.
- A live refresh or Socket.IO reconnect must preserve state from the server. The UI must never infer pause state from its own timer.

## Verification and acceptance

- Focused tests in `tests/` for Regular/Premium pricing at 59, 60, and 61 billable minutes; multiple pauses; pause across Manila midnight; order while paused; checkout while paused; unauthorized/food-only/Boardroom attempts; duplicate or concurrent clicks; and receipt/record billable duration.
- Financial test: a visit with a pause, food order, and discount produces one transaction with correct time/food components and audit events; checkout records and Daily Balance show the same charged amount by method and Manila checkout day. No extra ledger entry is created for the pause.
- Manual test on staff and admin phones: check in, wait for a charge, pause, wait beyond a price boundary, add food, verify only food changes, resume, then checkout. Check the stored history and the receipt.
- Before live rollout, back up MySQL to R2, run the migration while the app is stopped, verify new fields/table, restart, check health/logs, and test one controlled visit. Preserve existing sessions and checkout history.

**Done when:** a paused Regular/Premium customer's time charge stays fixed, orders continue, resume charges only active time, the pause history is reviewable, and final checkout reconciles with Daily Balance.
