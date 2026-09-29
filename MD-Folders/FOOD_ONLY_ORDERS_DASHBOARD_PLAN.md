# Food Orders dashboard without a timed lounge charge

**Status:** Implemented locally on 2026-09-29, following the request to start task 2 first. The Food Orders flow, checkout, receipt, inventory reuse, and Daily Balance reconciliation for Cash, GCash, BDO, BPI, and QueenBank are covered by `tests/test_food_only_orders.py`. The local development database was backed up and migrated after `AUTO_MIGRATE_ON_STARTUP=false` caused HTTP 500s. Deployment is pending. Empty-record cancellation and approved checkout voids remain in their separate task plans.

**Deployment gate:** Back up the target database, run `python -m app.db.run_migrations` against that target, and verify `customer_sessions.service_mode` and the `Take Out` space exist before restarting or serving the new code. The startup migration is disabled in the current environment; a code pull alone leaves these API routes failing. Keep this command scoped to the intended local/VPS database and check authenticated Food Orders, timed dashboard, checkout records, and Daily Balance endpoints after restart.

## Confirmed behavior

- Add a separate **Food Orders** dashboard and navigation entry for logged-in staff/admin.
- Creating a food-only order asks for **customer name** and a location: **Regular, Premium, Boardroom, or Take Out**. Take Out is a fourth choice.
- The location is a **label only**. A food-only record does not take a lounge seat, block a Boardroom booking, start a lounge timer, or earn a time charge.
- Each food-only record has the existing **Add Order** and **View Order** actions. Staff can add several food orders, see the running food amount, then collect payment using the existing checkout methods. A record with no placed food cannot be checked out for ₱0. An accidental empty food record can use the unused-session cancellation rule in `MISTAKEN_CHECKIN_CANCEL_PLAN.md`.

## Existing path to reuse

`CustomerSession` → `Order`/`OrderItem` → `/order/<session_id>` and `/orders/<session_id>` → `SessionService.preview_checkout`/`checkout` → `Transaction` → `SalesRepository.daily_ledger`. This is the shortest way to retain inventory reservation, payment history, receipts, per-method totals, and order status. `app/models/customer_session.py` currently requires a `space_type_id`; `app/services/session_service.py` always calculates time; `app/repositories/session_repository.py` counts all active sessions in occupancy; `app/routes/sales_balance.py::api_today_stats` calculates time for every active session. Each must distinguish food-only records explicitly.

## Phases

### 1. Schema and migration

1. Add an explicit `service_mode` (`timed` by default for old rows, `food_only` for new food records) to `CustomerSession`; use an idempotent migration in `app/db/migrator.py`, not only `db.create_all()`. Export it from the model/serializer paths that need it.
2. Keep `space_type_id` non-null by adding a zero-rate, no-capacity **Take Out** `SpaceType` via idempotent seed/migration. Existing Regular/Premium/Boardroom IDs and prices stay unchanged. Filter Take Out out of timed check-in and space-price controls.
3. Store location through the selected `SpaceType` relationship. Existing history retains its original `timed` mode and rates. Do not use the zero Take Out rate as the only food-only signal; food orders at Regular/Premium/Boardroom also have no time charge.

### 2. Creation and dashboard

1. Add an authenticated create/list path for food-only records. Validate nonblank bounded name and one of the four allowed locations. Set mode `food_only`, status `active`, and technical `time_in`/created timestamp for ordering and audit only. Do **not** call timed `SessionService.checkin` capacity/booking checks. Use existing CSRF and request-key conventions for mutations; repeated submit must not create duplicates.
2. Add a Food Orders page with a New Food Order modal and active cards/table showing name, location, food total, Add Order, View Order, and Checkout. Use `/order/<session_id>` and `/orders/<session_id>` rather than duplicating cart or kitchen logic. Handle empty, loading, error, and mobile states.
3. Keep food-only records off Regular/Premium/Boardroom timed session lists, occupancy numbers, seat availability, and booking conflict checks. Keep them visible in the new dashboard until checkout or cancellation. The `Take Out` choice must never appear as a timed lounge.

### 3. Pricing, payment, and audit

1. In shared checkout preview and checkout, branch on `service_mode`: food-only `time_bill = 0`, `food_bill` is the sum of stored order-item unit prices × quantities, and `total_bill = food_bill - eligible discount`. Preserve existing PWD/Senior rules for food. Reject checkout with no billable food or a nonpositive final total; do not create a zero-value `Transaction`.
2. Record a normal `Transaction` with mode/location discoverable through its session, full amount, method, collector, UTC timestamp/Manila business date, discount and item references. Keep its food revenue in the same `SalesRepository.daily_ledger` source as timed checkouts. Do not count food-only records as timed sessions or space revenue.
3. Update `api_today_stats` so **Still to Collect** includes the food subtotal of active food-only records but adds no time estimate. Update checkout records, receipts, report/PDF/CSV/Excel labels, and order lists to show “Food only” plus location and no fabricated duration/time charge. Keep customer-visible amounts equal across preview, checkout, receipt, and Daily Balance.
4. Ensure cancelling or voiding a food-only order follows existing inventory return and checkout-void rules; never free stock or change financial totals by deleting history.

### 4. Verification

- Create one food-only record in each location. Occupancy, boardroom availability, and timed dashboards do not change; all four appear in Food Orders.
- Place food, change order status, view order, preview, and pay in Cash and a noncash method. Time bill is exactly ₱0.00; food price/discount, `Transaction`, Checkout Records, Daily Balance method totals, and exports agree for the Asia/Manila day.
- Empty checkout is rejected; duplicate create/checkout cannot create duplicate records. Check stock reservation, sold-out handling, and any later food item void. Test cross-midnight business dates.
- Run focused order/session/sales tests, then the relevant cross-domain suite because this touches checkout, inventory, bookings, and reports. Inspect the diff before marking complete.

## Done when

Staff can take and settle food-only orders at any of the four locations through the normal order flow, with no timer or occupancy effect and a queryable payment history that reconciles to Daily Balance.
