# Edit a cart item to remove rice and/or egg

**Status:** Implemented locally on 2026-09-30. Owner selection, cart editing, price snapshots, stock use, receipt/kitchen labels, and checkout-to-Daily-Balance reconciliation are covered by `tests/test_order_modifiers.py`. Deployment requires `python -m app.db.run_migrations` before serving the new code; production has not been updated.

**Inventory finding:** Current recipe-mode sales reserve finished servings only; raw ingredient stock is tracked separately. These modifiers therefore keep the normal one-serving reservation and do not change raw stock. If raw ingredient reservation is added later, its rice/egg requirements must respect these stored options.

## Confirmed behavior

The owner chooses **which menu items** allow removing rice, egg, or both. On Add Order, staff can use an edit/pencil action **before Place Order** to remove either or both allowed components. Each removed component deducts **₱18 per serving** from that line's menu price; removing both deducts ₱36 per serving. Unselected menu items retain their normal price and have no modifier action. This edits the pending cart, not an already placed/kitchen order. Existing item-void behavior remains the way to correct a placed order.

## Existing path

`app/templates/admin/menu.html`, `app/routes/menu.py`, `app/services/menu_service.py`, and `app/models/menu_item.py` manage menu settings. `app/services/order_service.py::list_menu` feeds `app/templates/order.html`; that page currently merges cart rows by menu ID and submits only `{menu_item_id, quantity}`. `OrderService.add_order` merges all lines by menu ID, `OrderRepository.add_order_with_items` copies `MenuItem.price` to `OrderItem.price`, and `SessionRepository.sum_food_total_for_session` bills `quantity × OrderItem.price`. Inventory is reserved by `MenuAvailability.reserve` at Place Order. All of these need a consistent modifier snapshot.

## Phases

### 1. Owner configuration and migration

1. Add `can_remove_rice` and `can_remove_egg` boolean columns to `MenuItem`, default false for every existing item, with an idempotent production migration. Add two clearly labeled checkboxes to the admin Add/Edit Menu Item forms and include the fields in list/detail serializers. Existing menu items must not acquire modifier options automatically.
2. Validate on save that a menu price remains positive for **every combination allowed**: if both flags are on, base price must exceed ₱36; if one flag is on, it must exceed ₱18. Revalidate when changing a flagged item's price. Use Decimal money arithmetic, never browser floats, for persisted totals.
3. Check inventory mode. Prepared, direct, and current recipe-mode orders consume one finished serving per ordered serving; removing a component is a sale customization, not an automatic raw-stock restock. Raw ingredient stock is currently managed separately. If automatic raw consumption is added later, make its rice/egg allocation respect these stored options.

### 2. Cart UI

1. Include eligibility flags in `/api/menu`. After staff adds an eligible item, show an **Edit** icon on that cart line. The editor shows only the allowed “No rice” and/or “No egg” checkboxes, the base price, ₱18 deductions, resulting unit price, quantity, and line total. Provide a Cancel and Save action; edits remain reversible until Place Order.
2. Key/merge cart rows by **menu ID plus modifier combination**, not menu ID alone. Two normal meals and one no-rice meal must remain separate lines. Increasing/decreasing/removing one line must leave the other variant untouched. Preserve mobile cart, keyboard controls, accessible icon labels, and unavailable-stock states.
3. On submission send each line's item ID, integer quantity, and explicit modifier booleans. Show final unit and line prices in the confirmation/cart; client totals are display only. Refresh/reject a stale cart if the owner changed eligibility or price before placement.

### 3. Server price and audit

1. In `OrderService.add_order`, validate each line, eligibility and quantity against current `MenuItem` while reserving stock. Reject unknown modifier keys, forged removals, invalid quantities, negative/zero resulting price, and stale unavailable items. Compute `final_unit_price = base_price - (18 × selected_allowed_components)` on the server using Decimal, then sum quantities correctly.
2. Store an immutable snapshot on each `OrderItem`: base unit price, removed-rice/removed-egg flags, total unit deduction, and final unit `price`. Keep distinct combinations as distinct `OrderItem` rows; do not collapse them back by menu ID in `OrderRepository`. Preserve order actor/time and queryable before/after food total for the session (on the order or a small audit entry), so a later menu-price edit cannot rewrite the sale history.
3. Use stored final `OrderItem.price` everywhere: active order, kitchen view, receipt, Checkout Records, PWD/Senior discount base, food-only/timed checkout, and Daily Balance. Show “No rice” and “No egg” with each item where staff need to prepare or verify it. Do not add the ₱18 deduction as a separate expense or Daily Balance adjustment: it is a lower sale price, counted once when paid.
4. Existing inventory allocation/void logic still reserves or returns one finished serving for each ordered serving. Any future component-level stock logic must reconcile `MenuAvailability` without double returns.

### 4. Verification

- Configure only one eligible menu item, then test normal, no rice, no egg, and both removed; an ineligible item rejects forged options. Two variants of the same item persist as separate rows.
- For quantity 2 with both removed, line total equals `2 × (base − ₱36)`. Price edits after placement do not change the old order/receipt.
- Checkout preview, transaction food bill, PWD/Senior discount, receipt, checkout history, and Manila-day Daily Balance per method agree. Verify stock decrements/returns once per actual serving and failed/duplicate submits leave neither duplicate orders nor stock changes.
- Run focused menu/order/inventory and ledger-to-Daily-Balance tests; inspect the final diff.

## Done when

Owner eligibility controls the pre-placement editor, the kitchen sees the chosen removals, and every displayed/stored amount uses the same server-calculated final price.
