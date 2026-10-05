# Cowork, Cafe, and Discount breakdown in Daily Balance

**Week of October 5, 2026 · Status: implemented locally; awaiting deployment.** This is a daily sales breakdown, not a new payment ledger or a database reset.

## Goal and confirmed accounting rules

- In **Live Summary (Asia/Manila)** show **Cowork bill** = space/time charge, **Cafe bill** = all menu/food charges, and **Discounts** as separate visible amounts. Show the resulting **Checkout sales** clearly: `Cowork bill + Cafe bill − Discounts = Checkout sales`.
- Include all completed paid checkouts, including food-only orders and timed visits with food. Boardroom/Whole Hub space charges are Cowork; Take Out and any menu items sold at any location are Cafe. An unpaid placed order and an active session's estimated bill are **not** a sale yet.
- Use the **Manila date of checkout/payment**. On opening the page, Today is selected; when Manila reaches midnight, the Today view moves to the new day and starts at ₱0 until that day's checkouts occur. Historical days and date ranges remain available. Never delete or zero old transactions to achieve this display reset.
- Discounts remain visible instead of being hidden inside Cowork or Cafe. PWD/Senior time discount belongs to Cowork and an item discount belongs to Cafe for detailed reconciliation, but the main Cowork and Cafe cards show their **original bills** and the Discount card shows the reduction.
- Approved **false-entry** voids and **retained-credit** original checkouts are excluded from sales, following the current ledger. A fully **refunded** checkout remains shown as an original-day sale, while the refund appears separately on the approval day. Pending or rejected void requests continue to count as their original sale. A replacement checkout counts once on its own checkout day.
- Customer debt collections, other income, expenses, supplier payments, and retained credit cash flows remain in their existing Daily Balance categories; none is added to Cowork or Cafe sales.

## Existing source and implementation boundary

- `app/models/transaction.py` already stores `time_bill`, `food_bill`, `discount_amount`, `discount_item_id`, `total_bill`, payment method, `created_at`, actor, and void/credit fields. These immutable checkout amounts are the source for the split. Do not sum `OrderItem` at order placement or use the current menu price; those can differ from the final checkout and create premature sales.
- `app/repositories/sales_repository.py::daily_ledger` is the shared source for live totals, method reconciliation, and generated reports. It already handles false-entry/retained-credit/refund voids and credits. Add category accumulation **inside its existing transaction loop**, under the same branch rules as `checkout_methods`; do not create a second finance query that can disagree.
- `SalesRepository.summary_for_range` separately returns space/food revenue for analytics with discounts already allocated. Keep analytics consistent, but the Daily Balance cards should follow `daily_ledger` and the confirmed gross-plus-discount display.
- `app/services/sales_service.py::list_reports` merges live ledger values with generated-report metadata. `app/templates/admin/daily_balance.html` currently sums report rows for its filtered Live Summary. `app/services/daily_balance_export_service.py` and `app/templates/admin/daily_balance_report_pdf.html` render the exported values. There is no need for a new sales table if all views use the same ledger data.

## Ledger calculations

1. For each checkout that the current ledger treats as a sale, add the stored `Transaction.time_bill` to `cowork_bill`, `Transaction.food_bill` to `cafe_bill`, and `Transaction.discount_amount` to `discounts_total` on `manila_date(Transaction.created_at)`. If the discount targets a food item (`discount_item_id` is present), also put it in `cafe_discounts`; otherwise put it in `cowork_discounts`. These latter two are optional detail labels but must sum to `discounts_total`.
2. Keep the existing void branching exactly aligned. Do not add category amounts for false-entry/retained-credit originals. Keep the original category amounts for a refund treatment, and show the existing `total_refunds` on the **approval** day. Preserve credit-applied/credit-received money handling; a credit is not a second Cafe sale.
3. Return zero values for the new fields from `daily_ledger_empty`, so no-checkout days render correctly and generated reports do not need special-case UI code. Use `Decimal` internally and round once at display/serialization.
4. Assert in focused tests and, if useful, a server-side diagnostic that `cowork_bill + cafe_bill − discounts_total == total_revenue` for each day and for each payment method's checkout sales. If a legacy row violates the stored component sum, report the discrepancy for repair; do not silently invent food/space revenue or rewrite historical money.
5. Keep **refunds** separate from the four-part sales equation. Net cash movement remains computed by the established method ledger. Clearly label `Total Revenue` as checkout sales before separate refunds and label refunds on the day they actually happened.

## Screen and report changes

- In `app/templates/admin/daily_balance.html`, add Cowork, Cafe, and Discounts cards adjacent to the existing Total Revenue/Checkout sales card. Show the formula and the selected Manila date or date range so the owner knows whether numbers mean Today, This Week, This Month, or Show All. Keep compact/mobile wrapping readable.
- Preserve the existing Today default and automatic Manila midnight rollover in this template; changing filters to an older date must show historical amounts rather than suddenly resetting them.
- Include the same Cowork, Cafe, Discount, Checkout sales, and refund figures in each Daily Reports row and in CSV, Excel, and PDF exports through `DailyBalanceExportService`. Generated report data must come from the same ledger as the live cards; existing snapshots can retain generator/time/notes metadata.
- Keep payment-method reconciliation intact. A Cash, GCash, or bank checkout contributes its components to the same method's checkout total, with the discount deducted once. Avoid showing discounts or refunds as extra revenue.
- If a page request fails, show the existing load-error state rather than leaving plausible `₱0.00` cards with no warning.

## Worked examples

- October 5: one checkout has ₱20 time, ₱180 food, and a ₱18 food discount. Show Cowork ₱20, Cafe ₱180, Discounts ₱18, Checkout sales ₱182. The one payment appears in its actual Cash/GCash/bank method.
- October 5: a ₱100 Cafe checkout is later approved for a full refund on October 6. October 5 still shows Cafe ₱100 and checkout sales ₱100. October 6 shows a separate ₱100 refund/cash outflow; it does not create negative Cafe food sold on October 6.
- A ₱150 receivable payment on October 6 appears under **Debt collected** on October 6 and does not increase that day's Cowork or Cafe cards.

## Verification and deployment

- Focused ledger-to-Daily-Balance tests: mixed time+food sale, food-only sale, each payment method, time and food discounts, Manila 23:59/00:01 checkout, unpaid order, pending/rejected/approved void by each treatment, retained credit replacement, and next-day refund. Test the four-part sum and method totals.
- Verify live cards, generated report rows, CSV, Excel, and PDF agree for the same date and filter; historical records remain intact after the Manila midnight rollover. Run the full suite because finance data is shared across multiple screens.
- No schema change is expected for this plan. Before live deployment, back up the database and files to R2, update code, restart, check readiness/logs, and compare a known day's Checkout Records totals to the Daily Balance split.

**Done when:** the owner can see how much of paid checkout sales came from cowork time versus cafe food, see discounts and refunds transparently, and revisit any day without losing its history.
