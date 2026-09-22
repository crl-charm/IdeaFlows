# Task: Type meal recipes while adding or editing Menu items

Status: **implemented locally**; automated tests passed. Manual owner review and deployment remain. No existing menu prices, recipes, or stock counts were changed by this implementation.

## Goal

An owner creates a meal and types the raw ingredients used by **one order** in the same Menu form. Orders then deduct those ingredients from shared Inventory stock and show the estimated number of meals that can still be made. Cashiers continue placing orders normally.

## Owner-facing flow

1. In **Menu → Add Menu Item**, enter the existing details: name, category, price, description, and picture.
2. In **Ingredients for one order**, type an ingredient name, amount, and unit. **+ Add Ingredient** can be used repeatedly for as many ingredients as the meal needs; each row can be removed. There is no four-row limit or required ingredient picker.
3. Save the meal and all recipe rows together. If any row is invalid, save nothing and explain which row needs correction.
4. **Edit Menu Item** shows the same recipe rows so the owner can change an amount, add an ingredient, or remove one later. Edits affect future orders only.

Example recipe for one Corned Beef Silog (four ingredients here are only an example, not a limit):

| Typed ingredient | Amount per order |
| --- | ---: |
| Corned beef | 30 grams |
| Egg | 1 piece |
| Rice | 30 grams |
| Cucumber slices | 3 pieces |

The example amounts are illustrative; the owner must confirm actual portions, including whether rice is weighed raw or cooked.

## How typed names connect to Inventory

- Match a typed name to one existing raw-ingredient record using a normalized exact name (trim spaces, ignore case). Meals that type the same ingredient share **one** stock balance.
- If no exact match exists, create a raw-ingredient Inventory record with the typed name and unit and **0 stock**. The owner enters the real on-hand amount in Inventory before that meal can be ordered.
- Do not silently create a second stock record for a near-duplicate name or conflicting unit. Show a clear warning for owner review. Do not guess conversions or merge records based only on similarity.
- Do not create duplicate recipe rows for the same ingredient in one meal. Validate positive amounts and supported, compatible units. Stock changes remain in Inventory, not in Menu.

## Availability and order flow

- For a recipe-based meal, estimated servings = the smallest whole-number result of `stock on hand ÷ amount needed per order` across its ingredients. With 120 g corned beef, 24 eggs, 120 g rice, and 30 cucumber slices, the example can make **4** meals.
- At order submission, recheck the shared stock. For quantity `N`, deduct `N × recipe amount` for **every** ingredient in one database transaction with the order. If any ingredient is short, save neither the order nor any deduction; keep the cart and identify the shortage.
- After one example order, the balances become 90 g corned beef, 23 eggs, 90 g rice, and 27 cucumber slices. Recalculate availability for every meal sharing those ingredients.
- Record each deduction against the order so a void can return only unused/reusable stock. Food already used or wasted must stay deducted; record its reason.
- Editing a recipe changes later availability and orders, but never rewrites historical deductions or current on-hand stock.
- Use **recipe ingredients OR prepared-servings counting** for a meal, never both. Switching an existing counted meal to recipe mode must be explicit and must not erase its stock history.

## Keep the UI understandable

- Owner/admin: type recipes in Menu; receive supplies, record waste, and correct physical counts in Inventory.
- Cashier: see `X servings possible` or a clear unavailable reason; no recipe-entry work during checkout.
- A new meal with a new ingredient at 0 stock may appear in Menu but cannot be ordered until the owner records stock.
- Recipes are optional for items that should remain manually available or counted as packaged pieces. A bundle can be one menu item whose recipe contains the full bundle's raw ingredients; do not also deduct its component menu items.

## Existing system to reuse

The implementation reuses menu items, raw-ingredient stock, recipe links, availability calculations, transactional order deductions, and stock history. The added flow is typed recipe creation/editing inside Menu, safe name resolution, and saving the meal plus its recipe together. No new dependency was added.

## Acceptance checks

- [x] An admin can add, save, reopen, edit, and remove as many recipe rows as a meal needs, including more than four, without selecting existing ingredients from a list.
- [x] Saving reuses exact existing raw ingredients; a genuinely new one appears in Inventory at 0 stock. Invalid or ambiguous rows do not create partial data.
- [x] The example stock above shows 4 possible meals; ordering one deducts to 90 g / 23 pieces / 90 g / 27 pieces and shows 3 possible meals.
- [x] Ordering more than available stock fails without creating an order or changing any ingredient balance.
- [x] Two meals sharing rice deduct from the same rice record and both capacity estimates update.
- [x] Changing a per-order amount affects future orders only; historical order deductions remain correct.
- [x] Voiding an unused order can restore its recorded ingredient amounts once; wasted/used ingredients are not restored.
- [x] Existing meals without recipes keep their current behavior until an admin deliberately changes their tracking mode.

## Out of scope

Importing recipes from the photo folder, guessing portion sizes, changing menu prices, automatically counting prepared servings and raw ingredients for the same sale, and deploying this feature.
