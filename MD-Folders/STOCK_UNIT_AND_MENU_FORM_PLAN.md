# Stock units and Add Menu Item plan

Status: implemented in the repository on 2026-09-27. Verify the deployed revision before using it in production.

## Goal

Let an owner or authorized kitchen staff member choose the unit when updating an ingredient's stock (for example, kg or grams). Keep the Add Menu Item form to name, category, price, description, and image.

## Current behavior

- Each ingredient has one stored unit in `inventory_items.unit`; stock and history quantities have two decimal places.
- The owner Adjust Stock dialog currently accepts a number in the stored unit. The staff ingredient form sets an exact count in the stored unit. Neither form lets the person choose a unit for that update.
- Menu creation accepts an optional recipe list. The Add Menu Item form exposes it, although the backend already allows creating an item without a recipe.

## Implementation

1. **Owner stock update:** Add a labeled unit selector beside Quantity in the Adjust Stock dialog. Default it to the ingredient's stored unit. Keep Add, Subtract, and Set Exact Total. Show the current stock with its stored unit.
2. **Staff stock update:** Add the same selector beside Amount on hand for kitchen staff. Default it to the selected ingredient's stored unit each time the ingredient changes. Staff will enter both the amount and unit manually.
3. **Conversion and validation:** Send the entered unit to the server. Convert kg ↔ grams and liters ↔ ml to the ingredient's stored unit before applying the update. Allow pieces, packs, and trays only when they match the stored unit; do not guess pack or tray sizes. Reject unsupported units, incompatible units, negative totals, and conversions that cannot be represented exactly with the existing two decimal places. Do not change the ingredient's stored unit during an update. Log the entered amount/unit and resulting stock in the existing stock history.
4. **Menu creation:** Remove the recipe input and its submit handling from Add Menu Item. Keep ingredient/recipe management elsewhere unchanged.

## Verification

- Owner can add 500 grams to 1.00 kg and see 1.50 kg afterward; staff can set the exact stock using grams or kg. Both changes have a readable history entry with the actor.
- An incompatible unit or a conversion requiring silent rounding is rejected without changing stock or adding a history entry. A retry does not apply the same change twice.
- Add Menu Item shows only the requested fields and creates an item without a recipe.
- Run the focused inventory and menu tests, check the browser scripts for syntax errors, and inspect the final diff.
