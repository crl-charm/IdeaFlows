# User-Friendly POS Inventory and Menu Availability Plan

## Simple explanation for colleagues

### The problem

Food ingredients do not always produce an exact number of meals. For example,
3 kg of bangus does not always mean 12 servings because every fish has a different
size. Asking staff to calculate every ingredient for every meal would make the POS
hard to use.

### The simple solution

For cooked meals, the system will count **ready-to-sell servings**, not guess
servings from kilograms of raw ingredients.

Example:

1. The kitchen receives 3 kg of bangus and records it in raw inventory.
2. The kitchen prepares the fish and sees that it made 10 actual Bangus Silog
   servings.
3. The cook presses **Add Batch** and enters `10`.
4. The cashier immediately sees **10 servings left** on the ordering screen.
5. Every Bangus Silog order subtracts one serving automatically.
6. When zero remains, the item shows **Sold out** and cannot be added to an order.

The system never pretends that 3 kg automatically equals a fixed number of meals.
The kitchen enters the real number produced.

### How different items are counted

Each menu item uses one of four simple choices:

| Choice | Use it for | What the system counts |
|---|---|---|
| Prepared servings | Cooked meals such as Bangus Silog | Actual meals prepared by the kitchen |
| Stocked pieces | Bottled drinks and packaged snacks | Physical pieces in stock |
| Recipe ingredients | Standard recipes that need detailed tracking | Ingredients used per serving |
| Always available | Services or items the owner does not want to count | No quantity; staff can sell it while enabled |

The owner or admin chooses this once when setting up the menu item. Cashiers do not
need to configure recipes or open the Inventory page.

### What staff will do

- **Cashier:** sees `10 servings left`, `Only 2 left`, `Available`, or `Sold out`
  directly on each menu card and simply takes the order.
- **Cook:** uses three large controls: **Add Batch**, **Waste**, and **Sold Out**.
- **Admin:** chooses how each item is counted, corrects stock when necessary, and
  reviews the history.

### What happens automatically

- Orders reduce the correct serving, piece, or recipe ingredients.
- All connected ordering screens receive the new quantity without constant
  refreshing.
- Two cashiers cannot sell the same final serving.
- Cancelling or voiding an eligible order returns exactly what that order used.
- Staff orders follow the same inventory rules on every staff screen.
- Every batch, sale, waste entry, void, and correction is recorded for review.

### Short implementation approach

1. Add the four counting choices without disabling existing menu items.
2. Use one shared stock check for all staff ordering screens.
3. Add the simple kitchen batch controls and exact quantities on menu cards.
4. Make cancellations restore stock and keep a clear audit history.
5. Test with simultaneous orders, back up production, and deploy safely.

**In one sentence:** the kitchen counts what it actually prepared, the cashier sees
what is actually left, and the POS handles the deductions automatically.

---

## Detailed technical plan

## Goal

Make ordering feel like a normal, simple POS while keeping inventory accurate.
Cashiers must see availability directly on every menu card and must never need to
open the Inventory page before taking an order. Kitchen and admin users get simple
controls for adding prepared servings, recording waste, and marking an item sold
out. Detailed ingredient recipes remain available, but become optional.

This plan preserves the current menu, orders, raw ingredients, recipes, inventory
logs, live Socket.IO updates, and production data. It replaces the current rule
that every sellable menu item must have either a recipe or an inventory row.

## Current behavior and problems

The current code has useful foundations:

- Recipe capacity is calculated from the ingredient with the fewest remaining
  servings.
- Direct-stock items can already deduct one unit per ordered quantity.
- Stock deductions and new orders commit in the same database transaction.
- Inventory deductions lock rows, preventing two simultaneous orders from both
  consuming the same final stock.
- Ordering already displays Low Stock and Out of Stock states.
- Inventory and menu changes already have Socket.IO notification paths.

The current user-facing problems are:

- A meal with no recipe and no inventory row is treated as unavailable, even when
  the business wants to sell it without detailed ingredient tracking.
- The cashier sees only generic Low Stock or Out of Stock badges instead of the
  useful quantity remaining.
- Raw-ingredient recipes are too demanding for meals whose portions vary.
- Voiding an ordered item currently removes or reduces the order item without
  returning its previous inventory deduction.
- Customer QR ordering is not part of this product.
- The menu listing calculates capacity separately for each item; the new design
  must retain bounded query counts as the menu grows.
- Diagnostic per-ingredient logging during every order is noisy and should not be
  part of normal production ordering.

## Product decision: four simple availability modes

Every sellable menu item receives one explicit inventory mode.

### 1. Prepared servings — recommended for cooked meals

Examples: Bangus Silog, Tapsilog, Pancit, sandwiches, and daily specials.

- Inventory quantity means the number of servings currently prepared.
- Kitchen/admin enters how many servings were produced.
- Each submitted order reserves one serving per ordered quantity.
- Raw ingredients may still be recorded separately for purchasing and stock
  counts, but they do not block this meal.

### 2. Stocked pieces — recommended for packaged products

Examples: bottled drinks, canned drinks, packaged snacks, and retail items.

- Inventory quantity means physical pieces.
- Each submitted order reserves the ordered number of pieces.
- Receiving stock increases the piece count.

### 3. Recipe ingredients — optional advanced tracking

Examples: standardized recipes where the business wants ingredient-level
deduction.

- The existing recipe mappings and unit conversion rules remain supported.
- Available servings equal the lowest ingredient capacity.
- Ordering deducts every configured ingredient atomically.

### 4. Always available — no stock blocking

Examples: services, made-to-order items the owner does not want to count, or menu
items waiting for later inventory setup.

- No inventory row or recipe is required.
- The item remains orderable while its existing manual `is_available` switch is
  on.
- The ordering card says **Available** and shows no invented quantity.

The existing `is_available` field remains the master manual switch. Turning it off
must disable ordering regardless of the selected inventory mode.

## Simple workflows

### Cashier ordering

The menu card shows the information needed to make the sale:

```text
Bangus Silog       ₱120
12 servings left
[ Add ]
```

States:

- Green: `12 servings left` or `24 pieces left`.
- Amber: `Only 3 left`.
- Red: `Sold out`; Add is disabled.
- Neutral: `Available` for always-available items.
- Gray: `Unavailable` when manually switched off.

The cart prevents increasing a quantity beyond the last quantity received from
the server, but the server remains authoritative. If another cashier sells the
last unit first, submission returns a friendly message such as `Only 1 Bangus
Silog serving remains`, refreshes the affected card, and keeps the rest of the
cart intact.

### Kitchen prepared-servings screen

Kitchen/admin sees large touch-friendly cards rather than recipe forms:

```text
Bangus Silog
3 servings ready

[ + Add Batch ]  [ Waste ]  [ Sold Out ]
```

**Add Batch** asks only for `How many servings were prepared?` and defaults to the
last batch size when available. **Waste** asks for the number of servings and an
optional short reason. **Sold Out** sets remaining prepared servings to zero only
after confirmation. All actions are logged with user and time.

### Admin menu setup

Creating or editing a menu item includes one plain-language question:

```text
How should this item be tracked?

( ) Prepared servings — cooked meals
( ) Stocked pieces — drinks and packaged items
( ) Recipe ingredients — advanced
( ) Always available — do not count stock
```

Only fields required by the selected mode appear. Recipe forms stay hidden behind
an **Advanced recipe tracking** choice. Existing recipe copying/templates can be
added later without blocking this release.

### Raw ingredients

Raw fish, rice, oil, vegetables, and similar supplies continue to be received and
counted in Inventory using their natural units. They affect order availability
only when a menu item explicitly uses Recipe Ingredients mode. Prepared Servings
mode uses actual portions produced by the kitchen, which avoids guessing how many
meals an irregular weight of fish will make.

## Data model

### Menu availability mode

Add a validated `inventory_mode` field to `menu_items` with these allowed values:

- `prepared`
- `direct`
- `recipe`
- `untracked`

Use a string column plus application validation so deployment does not depend on a
database-specific enum. Do not infer behavior from category names during normal
operation.

The existing `inventory_items.stock_qty` can represent:

- Servings when mode is `prepared` and unit is `servings`.
- Pieces when mode is `direct` and unit is `pieces`.
- Raw quantities when the referenced menu item is an ingredient.

### Reversible order allocation record

Add an order-inventory allocation table that records the exact deduction snapshot
created for each order item and affected inventory item. At minimum it contains:

- Order and order-item identifiers.
- Sold menu-item identifier.
- Inventory-item identifier.
- Ordered units.
- Quantity deducted per ordered unit.
- Total quantity deducted.
- Quantity already restored.
- Mode used at order time.
- Created and updated timestamps.

This record is required because a recipe or tracking mode may change after the
order. Voiding must restore what was actually deducted at order time, not
recalculate from the current recipe.

Existing inventory logs remain the human-readable movement history. Batch adds,
waste, order reservations, and void returns receive clear movement reasons and
the acting user when available.

## Availability resolver

Create one `MenuAvailabilityService` used by every ordering entry point. It returns
a stable structure for each sellable item:

```text
inventory_mode
available_quantity       number or null
display_unit              servings, pieces, or null
availability_state        available, low, sold_out, disabled, configuration_error
can_order                 true or false
message                   safe user-facing explanation
```

Resolution rules:

- `untracked`: orderable when the manual availability switch is on; quantity is
  null.
- `prepared` or `direct`: use the menu item's inventory row; missing rows are a
  configuration warning for admins, not a silent fallback.
- `recipe`: calculate capacity from the current ingredient mappings.
- Manual `is_available=false`: always disabled.

Build availability for the full menu with bounded bulk queries. Do not issue one
recipe/inventory query per menu card.

## Ordering transaction and stock lifecycle

### Submit order

Use one business transaction for all item modes:

1. Validate the customer session and menu items.
2. Normalize positive integer quantities and combine duplicate menu-item rows.
3. Lock every affected inventory row in a consistent identifier order to reduce
   deadlock risk.
4. Recalculate authoritative availability while locks are held.
5. Reject the entire order with a friendly conflict response if any tracked item
   is insufficient.
6. Create the order and order items.
7. Deduct prepared servings, pieces, or recipe components.
8. Save exact allocation snapshots for each order item.
9. Add inventory movement logs.
10. Commit once, then emit one coalesced availability update.

No partial order or partial stock deduction may remain after an error.

### Void or cancel

- Voiding one unit restores exactly one unit's recorded allocations.
- Voiding all units restores all remaining recorded allocations.
- A second request cannot restore the same allocation twice.
- Always-available items require no stock restoration.
- Completed/served items require an explicit manager-authorized correction rather
  than an ordinary cashier void.
- Keep an auditable void record instead of silently erasing all evidence of the
  original sale.

### Staff ordering channels

All staff ordering screens must call the same order orchestration service. No
route may create order rows directly while bypassing availability, allocation,
or idempotency rules. Customer QR ordering is deliberately excluded.

## Real-time behavior without request storms

- Load the full orderable menu once when the order page opens.
- After a committed stock-changing action, emit one
  `menu_availability_changed` event containing only affected menu IDs and their
  current availability snapshots.
- Patch those menu cards directly, or perform one debounced refresh when a patch
  cannot be applied.
- Do not continuously poll the menu or inventory endpoints.
- Coalesce several ingredient changes caused by one order into one browser event.
- On reconnect, perform one full refresh to recover any missed updates.
- Update quantities already in the cart and warn before submission if the latest
  known stock is lower.

## Permissions

- Cashier/general staff: view availability and submit/void eligible orders.
- Cook: view availability and add prepared batches or record kitchen waste.
- Admin: all kitchen actions, menu tracking-mode setup, stock corrections, and
  audit history.
- Server-side authorization must enforce these rules; hiding buttons is not
  sufficient.

Confirm the exact permission for `server` staff during implementation. Until then,
do not grant prepared-batch or stock-adjustment access automatically.

## Existing-data transition

Do not make all existing items unavailable during deployment.

1. Create a pre-migration report listing every active menu item, recipe mappings,
   inventory row, unit, stock, and category.
2. Backfill existing items conservatively:
   - Items with valid recipe mappings become `recipe`.
   - Items without recipes but with an inventory row become `direct` initially.
   - Items with neither become `untracked`, so they remain orderable.
3. Show an admin **Inventory Setup Review** listing the inferred choice for every
   item.
4. Admin can bulk change cooked meals from Direct to Prepared Servings.
5. Changing modes requires confirmation and a logged starting quantity.
6. Raw ingredient rows are not converted into sellable menu modes.

The migration must be idempotent, reviewed against a copy of production data, and
run exactly once. `AUTO_MIGRATE_ON_STARTUP` remains false.

## Implementation phases

### Phase 0 — Baseline and production-data map

- Back up MySQL and production files.
- Record the current commit and dirty runtime files.
- Run the complete test suite and import validation.
- Generate the existing-data transition report.
- Measure current `/api/menu` query count and response time.

### Phase 1 — Schema and compatibility layer

- Add `menu_items.inventory_mode` safely.
- Add the order allocation table and required indexes.
- Add models and repository methods without changing current behavior yet.
- Implement compatibility resolution for rows not migrated yet.
- Test migration upgrade and rollback against a production-like database copy.

### Phase 2 — Unified availability service

- Implement all four modes in one service.
- Bulk-load menus, recipe links, and inventory rows.
- Return quantity, unit, state, and safe message consistently.
- Change no-link/no-inventory items to Untracked rather than Out of Stock.
- Preserve manual availability overrides.

### Phase 3 — Transactional order allocations

- Refactor staff ordering through the unified service.
- Lock and deduct tracked quantities atomically.
- Store allocation snapshots.
- Remove noisy per-ingredient diagnostic logs from normal success paths.
- Return structured `409` availability conflicts.

### Phase 4 — Correct void and cancellation behavior

- Restore exact allocations during void/cancel.
- Prevent double restoration and retain an audit trail.
- Apply manager restrictions after items are served.
- Test full rollback when any item fails.

### Phase 5 — Admin setup wizard

- Add the four plain-language tracking choices to menu create/edit.
- Build Inventory Setup Review for existing items.
- Provide safe mode changes, starting quantities, units, and thresholds.
- Keep recipe controls under Advanced mode.

### Phase 6 — Kitchen prepared-servings workflow

- Add touch-friendly prepared-item cards.
- Implement Add Batch, Waste, and Sold Out actions.
- Restrict actions by role and log the actor.
- Add clear confirmations and undo only through audited corrections.

### Phase 7 — Cashier ordering UX

- Show exact servings/pieces or Available on menu cards.
- Disable only sold-out or manually unavailable items.
- Respect current cart quantities.
- Preserve the cart on conflicts and highlight only affected items.
- Test phone, tablet, desktop, keyboard, and touch behavior.

### Phase 8 — Efficient real-time updates

- Emit one post-commit availability event per business action.
- Patch affected cards without polling.
- Debounce reconnect/full-refresh behavior.
- Verify no Socket.IO reconnect loops or repeated API request storms.
- Keep menu query counts bounded as data grows.

### Phase 9 — Reports and operational polish

- Report prepared, sold, voided, wasted, and remaining servings.
- Show configuration warnings only to kitchen/admin users.
- Add end-of-day count correction with a mandatory reason.
- Document the simple daily workflow for non-technical staff.

### Phase 10 — Verification and controlled deployment

- Run the complete automated suite and import validation.
- Test two simultaneous cashiers attempting the final serving.
- Perform local browser acceptance with separate staff roles.
- Back up production again immediately before deployment.
- Deploy code, run the reviewed migration once, and restart.
- Verify health, logs, ordering, void restoration, real-time updates, and reports.
- Monitor conflicts, transaction errors, query time, and Socket.IO traffic.

## Required automated tests

- Untracked items remain orderable without inventory rows or recipes.
- Manual unavailable switch blocks every mode.
- Prepared servings and stocked pieces deduct the ordered quantity.
- Recipe mode preserves correct conversions and capacity.
- Exact remaining quantities and units are returned to ordering.
- Cart quantity cannot exceed current known availability.
- Server rejects stale-cart overselling with a structured conflict.
- Two concurrent orders cannot consume the same final serving.
- Multi-item validation and deductions commit or roll back together.
- Voiding one unit restores exactly one unit of every allocation.
- Repeated void requests cannot restore twice.
- Served-item correction requires the correct authorization.
- Batch, waste, sold-out, and correction operations are audited.
- Unauthorized roles cannot change prepared quantities.
- Menu listings use bounded query counts.
- One order produces one coalesced real-time update rather than polling.
- Existing recipes, direct stock, reports, menu images, ordering, billing, and
  session totals have no regressions.

## Acceptance criteria

- A cashier can determine availability and place an order without visiting
  Inventory.
- A meal with no raw-ingredient recipe can be sold using Prepared Servings or
  Always Available mode.
- The kitchen can add a prepared batch in a few taps.
- Sold-out items disable automatically on every connected order screen.
- Cancellation restores stock correctly and visibly.
- Detailed recipe tracking remains optional and continues to work.
- There is no background polling or repeated-request storm.
- Existing menu items remain usable immediately after migration.

## Deliberate non-goals for the first release

- Automatically guessing portions from kilograms of irregular raw food.
- AI-based ingredient or serving estimation.
- Supplier purchasing, purchase orders, or full food-cost accounting redesign.
- Automatic recipe generation for every existing menu item.
- Allowing cashiers to change raw stock or tracking modes.

The system must never pretend it can infer actual prepared servings without an
explicit recipe or a simple kitchen-entered portion count.
