# Daily meal servings and customer order audit

**Status:** Implemented locally on 2026-10-01. Git push and VPS deployment remain separate steps.

**Implementation:** The shared Inventory UI now adds serving batches, offers a reasoned count correction, shows an ordered/available button, and opens a dated audit of batches, customers, cancellations and other stock movements. The read-only audit uses existing stock logs, order allocations and action records; no schema migration was added. It flags incomplete legacy history, positive count corrections and orders placed before serving tracking.

**Verification:** The full suite passed (255 tests). After the final audit changes, the audit and Inventory UI targets passed again (14 tests), along with Python and JavaScript syntax checks.

## Goal and confirmed rules

The owner wants a per-meal, per-date explanation of the serving count. Beside each meal's serving action, show a compact button such as **6 of 10 ordered today**. Clicking it opens a modal showing who ordered that meal, how many servings each customer ordered, who entered each serving batch, and the movements that explain the remaining stock.

- A placed order counts immediately, including an active session that has not paid. Label the number **ordered**, not **paid sales**. Checkout and Daily Balance still determine actual money received.
- Each later serving entry on the same Manila date is **an additional batch**. It must add to stock; it must not silently overwrite the first entry.
- Unsold servings carry into the next day. Show **opening stock** separately from **servings added today**.
- The same view must work for admin and staff using the shared Inventory page. The owner can see the account name that recorded every batch or stock correction.
- This is an audit of recorded activity, not proof that a meal was physically handed to the named customer. Show discrepancies and manual changes instead of presenting an unexplained count as verified.

## Existing code to reuse

- `app/templates/admin/inventory.html` renders Meals & Availability and currently shows remaining `available_quantity`. The same page is served at `/admin/inventory` and `/staff/inventory`.
- `static/js/inventory-workflow.js` renders each meal's **Set servings** and **History** buttons and uses `app/templates/inventory_controls.html` for the dialogs.
- `app/routes/staff_inventory.py` already has authenticated stock actions and per-meal history at `/inventory/api/menu-items/<id>/history`. `app/services/stock_management.py` writes `InventoryAction` (action, quantity, actor, time, request key) and `InventoryLog` (stock delta, reason, actor, time). Its `servings` action currently means **replace available stock with this exact number**; `add` means **add a batch**, but currently accepts only `prepared`/`direct` modes and requires an existing stock row.
- `app/services/order_service.py` and `app/services/menu_availability.py` reserve servings when the order is placed. `OrderInventoryAllocation` preserves original order/item IDs and deducted quantity. `Order` links to `CustomerSession`, which has the customer name and lounge/takeout location. `void_item` records `void_return` or `void_no_return`, even if it deletes the last `OrderItem` row.
- `app/utils/dates.py` provides `manila_date` and `manila_day_bounds`; database timestamps are naive UTC. Reuse those helpers.
- The existing `/inventory/api/prepared-summary` is lifetime aggregate data. It is not a per-day or per-customer sales report.

## Display and accounting definitions

For a selected Manila business date `D` and meal `M`:

| Field | Meaning |
| --- | --- |
| Opening stock | Sellable servings carried from the end of the previous Manila day; do not reset inventory at midnight. |
| Added today | Sum of successfully recorded new serving batches for `M` on `D`, with each batch's timestamp, amount, and logged-in actor. |
| Ordered today | Servings from orders placed on `D`, less cancelled servings from those orders. Include unpaid active sessions. Show placed and cancelled quantities separately so the subtraction is reviewable. |
| Available today | Opening stock + added today. This is the denominator in **ordered / available**. |
| Remaining stock | Actual inventory quantity after orders, returns, waste, sold-out actions, and exact-count corrections. For today use the stored current value; for an older selected date derive that day's closing value from durable stock movements. Keep this separate from the ratio. |
| Other movements | Waste, sold-out, void without stock return, and exact-count corrections. Show each with reason, actor, time, and signed stock change. These must never be disguised as customer orders. |

Example: opening 0, Diana adds 10, customers order 6, no other movement: **6 of 10 ordered; 4 left**. If Diana later adds 5, show **6 of 15 ordered; 9 left**, with two batch rows. If opening is 2 and 10 are added, show **6 of 12 ordered**, with **opening 2** and **added today 10** explicitly displayed.

If an order is partially or fully cancelled, retain the original order event and the cancellation event. Exclude cancelled servings from the net ordered count, whether or not stock was returned. A cancellation without return must instead appear under **not returned / stock discrepancy**; never invent a customer sale to explain the missing serving. A later cancellation of an earlier day's order adjusts that original order day's net count when viewed again and shows the cancellation's actual timestamp in the audit trail. Keep actual remaining stock based on the dated inventory movements. Show a visible reconciliation warning if opening, additions, order deductions, returns and manual movements do not explain that day's closing stock.

Do not calculate the numerator by subtracting current stock from a set amount: waste, manual corrections, carryover, and voids make that wrong. Do not count raw ingredient deductions as meal servings. Count only menu items whose tracked unit is `servings` (`prepared`/`recipe` and an `untracked` item after servings are enabled); a `direct` piece-counted item keeps its piece controls and should not receive a misleading servings ratio. If a meal has no valid starting count, show **Set up servings** rather than `0/0 sold`.

## Interaction and UI

1. On each eligible Meals & Availability card, place the new **N of T ordered today** button immediately to the left of the serving action. Keep the existing prominent remaining-stock label and History button. Update the button after inventory/order socket events and after a successful batch or void; the server supplies the numbers.
2. The new modal identifies meal and Manila date, with a date input defaulting to today and clear previous/next or Today controls. Its summary shows opening, added, placed, cancelled, net ordered, remaining, and non-order movements. Use an explicit empty state on a day with no batches or orders; show when older records are incomplete rather than guessing.
3. Batch section: date/time, quantity, actor name (from authenticated `User`/admin shadow user), and action/reason. Customer order section: order time, customer name, location, order ID, servings ordered, cancelled, net servings, order handler, and checkout state if available. For active orders, show **Not checked out** while still counting the order. Keep separate rows if the same customer placed two orders.
4. Keep the current meal History modal for all stock movements. The new modal is the dated reconciliation view and links to History for details. Escape names/reasons in HTML, label buttons and date input, restore focus when closing, and support narrow screens with a scrollable table or stacked rows.
5. Change the current serving-entry wording and action so an entered number clearly means **new servings prepared in this batch**; reuse the existing `add` stock action and its idempotency key. Extend that action to `recipe` servings and initialize an `untracked` meal's servings row/mode atomically on its first batch. Keep a separate **Correct available count** action for an exact physical count, requiring a reason and recording its before/after delta. Do not reinterpret historical `servings` actions as additions: they remain exact-count corrections in history.

## Query/API design

- Add an authorized, read-only per-day summary for all visible meals to avoid one request/query per card. It can extend the existing Inventory dashboard response or be one batched `/inventory/api/meal-day-summary?date=YYYY-MM-DD` request. Return meal ID, opening, added, placed, cancelled, net ordered, remaining, and `history_complete`/reconciliation state. Do not put all customer rows in the initial card response.
- Add an authorized, lazy-loaded detail route such as `GET /inventory/api/menu-items/<id>/daily-audit?date=YYYY-MM-DD`. Validate date and meal type, apply `manila_day_bounds`, paginate customer/movement rows if needed, and return a stable sort with timestamp and ID. Require the same active staff/admin inventory access as current meal history; the staff browser must not call `/admin/*`.
- Derive customer lines from `OrderInventoryAllocation` -> `Order` -> `CustomerSession`, joined to surviving `OrderItem` when present. Use allocation snapshots and `InventoryAction` void records to account for deleted/partially voided order items. Use `InventoryAction`/`InventoryLog` for batches and manual stock movements. The final query must not depend on the global last-100 history endpoint.
- Use database-side aggregates for totals, preserve Decimal/whole-serving validation, and never let a browser-supplied total control stock or money. Keep meal ID/date input bounded and filter all joins to the selected meal. If legacy data cannot establish an accurate denominator, return an explicit incomplete-history state and still show the known order/movement rows.
- Do not change checkout, payment methods, or Daily Balance arithmetic. The order list is a stock audit. Where a placed or voided order has a money effect, retain its existing financial audit path and include a focused check that checkout revenue and payment-method Daily Balance totals remain correct and unduplicated.

## Implementation sequence and verification

1. Add the server-side dated aggregation and customer-detail query using existing records. Prove the totals with a focused test before adding UI.
2. Make serving-entry semantics additive for new batches and keep an explicit exact-count correction path with reason/actor. Preserve atomic stock updates, idempotency, and socket refresh.
3. Add the card button and modal to the shared Inventory template/JS. Verify admin and staff URLs/permissions, desktop/mobile layout, keyboard use, and readable empty/error states.
4. Test: two batches on one day; opening carryover; an order before payment; several customers and quantities; different dates around 00:00 Manila; partial/full void with and without stock return; waste/correction; duplicate submit; concurrent order/batch update; missing/legacy history; deleted order item; no cross-meal leakage. The modal's net count, stock movements, and persisted remaining stock must reconcile for each case.
5. Run focused inventory/order tests and broader suite because stock, orders, and checkout share records. Inspect the diff and check that no new migration/table is added unless existing durable records cannot express the required audit. Plan and test any required migration before deployment.

**Done when:** the owner can open any meal for a date and see the exact recorded batches, actor names, customer orders, cancellations, other movements, and an explainable remaining count; a placed but unpaid order is counted and labelled as such.
