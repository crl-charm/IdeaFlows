# Inventory units, stock reasons, and per-meal serving controls

Status: **plan only** (2026-09-27). No application behavior is changed by this file.

## What is already in place

- Ingredients store one base unit and a stock quantity in `inventory_items`. The owner can add, subtract, or set an exact total; kitchen staff can set the amount on hand. Both stock forms currently allow only the stored unit or an automatic kg/grams or liters/mL conversion.
- The owner's Adjust Stock reason list includes **Restock**, **Damaged**, **Expired**, **Inventory count**, and **Other**. `Inventory count` means a physical count correction; `Other` is an unspecified reason. Existing history can contain either reason.
- Adding a sellable menu item already makes it appear under Meals & Availability. The owner screen has one **Set available servings** button above all meal cards. The existing dialog then asks the user to choose a meal from a dropdown. Serving changes use the existing stock action endpoint and write `InventoryAction` and `InventoryLog` records. Orders and voids also affect stock history. The recent stock activity view combines items and is limited to 100 records.

## 1. Unit measurements when updating ingredient stock

### Intended workflow

1. Rename **Unit** to **Unit measurements** in the owner Adjust Stock dialog and the kitchen staff stock form.
2. Offer the supported ingredient units in both selectors: **kg, grams, pieces (pcs), packs, trays, liters (L), and milliliters (mL)**. Default to the ingredient's stored unit whenever an item is opened or selected. Keep the stored unit visible beside Current Stock.
3. The person enters both a quantity and its unit for this update. Example: if rice is stored in kg, entering 500 grams adds 0.50 kg. The ingredient's stored unit does not change.
4. Convert kg ↔ grams and liters ↔ mL automatically. For a pack, tray, piece, or any other pairing without a known fixed conversion, show a required field such as **“How many kg are in one pack?”**. The user supplies the ratio for that update; the app must never guess a pack size. The field stays hidden for same-unit and automatic conversions.
5. Send the selected unit and, when required, the explicit ratio through the existing owner and kitchen stock endpoints. Apply the conversion in the service before the existing add/subtract/set operation. Show the entered unit, ratio (if supplied), resulting quantity in the stored unit, actor, and time in the stock history.

### Validation and integrity

- Reject an unknown unit, missing/zero/negative or non-finite ratio, fractional pieces/packs/trays, negative resulting stock, and any amount that cannot be represented exactly by the existing two-decimal stock column. Show the server's error without changing stock or recording a false log.
- Keep the existing idempotency keys, permission checks, transaction boundaries, and real-time inventory refresh. A retry must not apply the stock change twice.
- Do not change recipe ingredient units or menu recipe conversion settings. This form converts only the **entered stock update** into the ingredient's existing base unit.
- Use the existing unit normalization and fixed conversion helper. An explicit ratio is per update, so no database migration is expected.

### Code and checks

- UI: `app/templates/admin/inventory.html`, `app/templates/staff/inventory.html`.
- Endpoint wiring: `app/routes/inventory.py`, `app/routes/staff_inventory.py`.
- Conversion and log: `app/services/inventory_service.py`; keep `app/utils/inventory_helpers.py` as the source for fixed conversions.
- Test kg/grams and liters/mL; packs/trays with and without an entered ratio; staff and owner access; invalid precision/whole-unit amounts; history and retry behavior. Update the focused inventory UI and service tests.

## 2. Simplify the owner stock reason list

### Intended workflow

- Show only **Restock**, **Damaged**, and **Expired** in the Adjust Stock Reason dropdown. Remove **Inventory count** and **Other** from this dropdown.
- Keep Add, Subtract, and Set Exact Total available. Select Restock by default when the dialog opens. Where the UI changes the suggested mode for Damaged or Expired, make the selected mode visible and let the user review the quantity before saving; never alter stock silently.
- Preserve old Inventory count/Other entries in the history. Removing choices from a form must not delete or rewrite past inventory records.
- The separate kitchen **Amount on hand** operation and prepared-meal serving counts still have their own internal action names. This request changes the owner's manual ingredient Reason choices, not those audit events.

### Checks

- New owner adjustments display and save one of the three requested reasons; no removed option appears in the dialog.
- The saved history still shows the mode, reason, quantity change, actor, and time. Old history remains readable.
- Review how Add/Subtract/Set Exact Total interact with each reason so a choice such as Damaged cannot accidentally increase stock without a clear warning or validation.

## 3. A serving button and history on every meal card

### Intended workflow

1. In **Meals & Availability**, put **Set servings** and **History** actions on each sellable meal card. Remove the shared Set available servings button above the cards. Keep the existing search and Needs setup review filter. The buttons belong to the visible card, so the user does not choose a meal from a second dropdown.
2. Clicking **Set servings** opens the existing serving dialog for that meal, displays its name and current count, and accepts a whole-number **available now** value. Entering 0 marks it sold out. Saving uses the existing `/inventory/api/menu-items/<id>/action` path with `action: "servings"`, then refreshes the cards and menu availability.
3. Clicking **History** opens a view filtered to that one meal. Show each change's date/time, action, quantity or delta, actor, and reason. Include manual serving counts, order deductions, returns/voids, and other stock changes when they exist. Give an empty state for new meals; old entries must remain visible after another meal is edited.
4. Reuse `InventoryAction`, `InventoryLog`, and existing order allocation records rather than inventing a separate serving ledger. Add a meal-specific, authorized history query/API so it does not rely on filtering the global 100-row recent activity response in the browser. Paginate or cap results with a way to reach older records; avoid loading every meal's history with the initial dashboard.
5. Keep the existing role rules: owner and authorized kitchen staff may change servings; users without kitchen permission may see availability but must not receive an enabled edit action. Server authorization remains the final check. Show History only to roles allowed to read stock history.

### Item types and audit details

- Serving counts apply to the existing `prepared`, `recipe`, and `untracked` meal modes. A `direct` item is counted in pieces; its card should use the corresponding existing stock action rather than silently relabeling pieces as servings. Every sellable card still gets a relevant update action and a History action.
- A new serving count replaces the **current** count; it is not an amount to add. Make that clear in the dialog. Record enough detail for future history to show the previous and new counts, while presenting older records only with the detail they actually contain.
- Keep the existing idempotent stock action, stock/order concurrency checks, and real-time refresh. No new stock table or migration should be needed unless implementation reveals missing audit data that cannot be reconstructed from existing records.

### Code and checks

- Owner cards: `app/templates/admin/inventory.html` (`renderRecipeInventory`). Shared serving dialog and client behavior: `app/templates/inventory_controls.html`, `static/js/inventory-workflow.js`.
- Kitchen staff inventory: `app/templates/staff/inventory.html`; put the equivalent actions beside each meal row for authorized kitchen staff and use the same shared dialog instead of a second save path.
- Per-meal history query/API: `app/routes/staff_inventory.py` and existing inventory models/services. Reuse the stock log data and preserve authorization.
- Test that every relevant card opens its own item without another selection step; a 0 count marks the meal sold out; another meal is unchanged; order and void movements appear in that meal's history; old records remain accessible; unauthorized users cannot update or read protected history; repeated submits do not double-change stock. Check desktop and narrow/mobile layouts, keyboard labels, and script syntax.

## Implementation order and completion gate

1. Implement and verify unit input, conversion, and ingredient history.
2. Simplify the owner Reason selector and check mode/reason behavior without altering historical rows.
3. Add per-card meal actions, reuse the serving save path, and add meal-filtered history.
4. Run the focused inventory tests and JavaScript syntax checks. Inspect the diff for extra code and regressions. Run broader tests if changes touch order or void behavior.
5. Confirm the deployed revision after the user pushes and deploys it. This plan alone requires no database migration and does not change the live site.

Related earlier work: `MD-Folders/STOCK_UNIT_AND_MENU_FORM_PLAN.md` documents the first unit selector and the simplified Add Menu Item form. This plan extends the unit selector and adds the reason and per-meal workflows.
