# Customer Receivables Statement / PDF Export

**Date:** October 29, 2026  
**Status:** Implemented and verified locally on October 29, 2026, and included in this source release. The local SQLite schema was upgraded after a verified backup. VPS deployment has not been performed.

## Implemented flow

1. Sign in as an admin and open **Finance → Reports & Exports → Customer Statement** (`/admin/reports`).
2. Search for a customer/building and select its **RA account reference**. Settled accounts remain searchable.
3. For older data, expand **Review customer history**. Inspect matching cycles before associating them; leave different people with the same name separate. An individual debt can also be moved out of an incorrectly combined cycle. Associations preserve debt/payment amounts and financial dates and record the admin, original account/cycle, and time.
4. Confirm the recorded history once it belongs to the correct customer. Changes to its historical associations require confirmation again. Unassigned debts matching the account and conflicting balances block PDF export until reviewed.
5. Review charges, food details, receipts, and the running balance. Optionally enter **Attention / Contact person**, then download **Export Customer Statement PDF**.

The admin Receivables **View tab / View cycle → Export Statement** shortcut opens the same account statement. All history is independent of Receivables' selected date and the on-screen page size.

For a new debt, staff/admin choose menu items, quantities, and supported no-rice/no-egg options. The server computes the amount and saves names/prices as snapshots. **Manual / historical description and amount** remains available when old prices or quantities are not known. **Ordered by / Taken by** is optional; **Recorded by** always uses the authenticated canonical User.

This form records credit for items already taken. It does not create a kitchen order or deduct stock a second time. Food preparation still uses the existing Order flow.

### Local verification

- **426 distinct automated checks passed**, combining the regression run and focused follow-up runs. The initial full run's nine temporary-directory errors were rerun successfully in a disposable workspace folder; its missing-idempotency check was fixed and passed. No failed, errored, or skipped cases remain in the combined results.
- Browser checks used fake in-memory records at **1366, 768, 375, and 320 pixels**. Statement pages and the phone entry modal needed no sideways scrolling; item entry, history association/confirmation, PDF download, and staff export denial passed with no browser page errors.
- A real **nine-page A4 PDF** was generated using the existing xhtml2pdf fallback. Summary, itemized charges, repeated ledger headings, page numbers, and final balance were rendered and visually inspected. Extracted PDF text excluded the other test customer's data.
- Tested settled/reopened cycles, ambiguous same-name customers, individual legacy-debt assignment, split and partial payments, undated historical credits, conflicting balances, stale menu prices, immutable snapshots, duplicate requests, canonical admin IDs, expired sessions, and bounded related-data reads.
- Tested upgrading an older SQLite schema and running migrations twice without duplicate account creation. Actual local debt/payment rows and amounts were unchanged after migration.
- Local backup: `instance/pre-customer-statements-20261029-7c7347ba.sqlite3` (ignored runtime data).

These are localhost/isolated SQLite and Chrome viewport checks. The production MySQL rollout and checks on the client's physical devices remain part of a separately authorized deployment. The monthly salary/accountant report is still a separate planned feature.

## Goal and confirmed scope

The owner can select **any receivables customer** and download a PDF explaining what that customer took on credit, what they paid, and what they still owe. This includes individual customers and building/company accounts.

Confirmed with the client:

- The building example uses the **building name** as the customer account.
- The feature applies to **all customers in Receivables**, rather than a building-specific workflow.
- The owner can export one selected customer's full history and give the PDF to that customer or their account contact.
- New food-debt entries use **menu items and quantities**. Preserve the descriptions and amounts already saved for older entries.
- The default statement covers **all recorded history**, including paid debts, payments, and closed customer tabs, not just today's or this month's unpaid list.

The building administrator who orders is a customer-side contact. This person is distinct from the IdeaFlow staff/admin who records a debt. A statement addressed to a building owner must still identify the correct receivables account.

## Owner's flow

1. Open the proposed **Reports & Exports** page.
2. Choose **Customer Statement**.
3. Search and select the customer or building account. Show contact information and an account reference to distinguish matching names.
4. Preview **Total Taken on Credit**, **Total Paid**, **Still Owed**, food details, and the complete dated history.
5. Tap **Export Customer Statement PDF** and download the file to give to that customer.

Also add **Export Statement** to the admin Receivables customer's View Tab/detail area. It opens the same statement view with the customer selected; it does not use a second report calculation.

The monthly accountant report and customer statement are separate export modes on one page. The customer PDF contains only the selected account's information. Salary records, business-wide sales/expenses, and other customers' debts never enter its PDF context.

## Statement contents

### Header and totals

- IdeaFlow name/logo and **Customer Statement of Account** title.
- Customer/building name, account reference, and saved contact where appropriate.
- Optional **Attention / Contact person** for a building representative. This is a delivery label and does not change which account the debts belong to.
- Coverage: **All recorded history through [generation date/time, Manila]**.
- Total charges on credit, total payments/known historical credits, and the prominently displayed remaining balance.
- A zero-balance account remains exportable, labeled **Settled as of [date]** while retaining its previous charges and payments.

### Dated charges and food details

For each debt, show its record reference, Date Taken, items, total charged, amount paid, remaining amount, and recorded due date. For new itemized entries, show food name, modifiers where applicable, quantity, saved unit price, and line total.

For a building/company account, allow an optional **Ordered by / Taken by** name per debt. Keep **Recorded by** as the separate authenticated IdeaFlow actor. Existing rows without an ordering contact should say **Not recorded**, rather than guessing who ordered.

### Payments and running balance

Show dated payments, payment method, amount, and the debt allocations where useful. A payment split across several debts is one customer payment with several allocations, rather than several separate customer payments.

Use a chronological account ledger with charge and payment amounts and a running balance. Where a charge has only a saved Date Taken, identify it as a date-only entry; do not invent an exact ordering time. Use stable references to order same-day entries consistently.

**Illustrative example:** a customer takes PHP 180 of food, later PHP 180 of drinks, and pays PHP 200. The statement shows **PHP 360 charged − PHP 200 paid = PHP 160 still owed**. If the payment is allocated PHP 180 to the first debt and PHP 20 to the second, its payment total is still PHP 200.

## Selecting the correct customer across all history

The current `ReceivableTab` represents an open/closed billing cycle, not a permanent customer identity. A new debt after a fully paid cycle can create another tab. The current open-tabs list therefore cannot supply an entire customer lifetime statement on its own.

- Add a small, stable receivables-customer/account identity and associate its billing tabs with it. Keep the existing debt and payment IDs and preserve the cycle history.
- New entries select that account, including when a new billing cycle is opened. Continue allowing a new customer to be recorded.
- For historical data, propose matches from existing name/contact data, then require admin review where account membership is ambiguous. Same-name customers or blank contacts must not be silently merged.
- Legacy records without a tab must be included through a reviewed account mapping, not omitted from the PDF. Do not overwrite their financial dates or amounts during association.
- Until ambiguous historical rows are assigned, show an explicit **History needs review** notice with the affected records. Do not claim that an unreviewed set is the customer's complete history.
- Search/select by account ID and confirmed tab membership. Do not generate a financial statement by a broad name substring search.
- The first version exports all history through the current generation time. A future date-range option would need an opening balance; it is not required for this version.

## New menu-item detail without duplicated orders

In the receivable entry form, allow menu search, quantity, and available modifiers. The server validates selections and computes the total from approved prices. Save per-debt line snapshots: item name, quantity, unit price, line total, and modifiers. A menu rename, price change, or removal must not rewrite an existing statement.

Use a small `ReceivableItem` child table or equivalent immutable per-debt item records. Keep `items_description` readable for existing views and older manually entered debts. Store optional source order/item references only when their relationship to this exact debt is verified.

Itemizing a debt must not independently create a duplicate kitchen order, stock deduction, checkout sale, or cash receipt. The receivables form records items taken on credit; order fulfillment and inventory continue through the established Order workflow. When an existing order supplies the debt, snapshot/link its exact credited items once. Do not assume every food item on a linked customer session belongs to this one receivable, because that visit may contain other paid or separate orders.

If old data only says **Food and drinks — PHP 500**, export that description and amount. Do not reconstruct quantities or old prices from the current menu. For a newly logged historical debt whose old prices are unavailable, use a verified, explicitly labeled manual description/amount entry rather than presenting today's menu prices as historical facts. Retain a recording actor and never fabricate itemization.

## Balance and history rules

- Sum the selected account's actual debts once and subtract its paid amounts once, using decimal money arithmetic.
- Include paid and unpaid debts and closed cycles. A tab closing must not make its history disappear from the customer statement search.
- Use `incurred_date` as Date Taken, with the existing Manila recording-date fallback when missing. Payment entries use `ReceivablePayment.received_at`. Keep the actual recording timestamps where available.
- Group `ReceivablePayment` allocations by their saved `payment_group_id`. Sum allocation amounts to produce that payment's total; do not repeat the group total for every allocation. Without a saved group ID, keep legacy payment records distinct rather than merging separate receipts because their dates or methods match.
- Reconcile saved `partial_paid`/remaining balances against detailed payment rows. Where a legacy recorded paid balance has no itemized payment history, show **Previously recorded payment/credit; date/details unavailable** with a clear limitation. Do not invent a receipt, method, or date or count the same known payment twice.
- If payment rows contradict the recorded balance, show the discrepancy for admin review before producing a final customer statement. Export must not silently repair financial records.
- Do not automatically add all paid checkout orders by customer name to the debt ledger. The statement lists receivable charges and the food items belonging to them.
- Export is read-only: no payment is collected, no debt is cleared, no interest or late fee is added, and no sale/cash movement is generated by downloading the file.

## Access, PDF, and layout

- Preview and PDF creation are admin/owner-only, protected server-side. Existing staff permissions for recording and viewing receivables remain a separate operational capability.
- No customer login or public statement URL is needed. The owner downloads the file and shares it manually. The public `/current-customer` page does not expose receivable balances/history.
- Build the statement from an explicit selected-customer data projection, separate from the accountant-report context. Protect against changing a customer/tab ID to export an unintended combined account.
- Use the existing PDF renderer and IdeaFlow branding. A4 portrait pages, wrapped names, repeated table headings, page numbers, and the remaining amount must remain readable.
- Include all selected records even when they exceed the on-screen pagination limit. Use bounded related-data queries and avoid one query per debt or item.
- On mobile, stack charge/payment details and keep Export easy to reach without horizontal scrolling. A failed request must show a clear error rather than a false zero balance or partial PDF.
- Suggested filename: `IdeaFlow-Customer-Statement-<account-reference>-2026-10-29.pdf`. Avoid contact numbers and unsafe free-text characters in filenames.

## Existing source and intended additions

| Existing source | Purpose / limitation |
| --- | --- |
| `app/models/receivable.py` | Debts, billing cycles, payments, payment groups, and balances; no permanent cross-cycle customer identity or structured food lines yet. |
| `app/repositories/receivable_repository.py` | Open-tab listing, tab records, oldest-debt-first payment allocation, and payment retrieval. Add confirmed all-cycle account queries. |
| `app/services/receivable_service.py` | Current debt summaries and grouped payment history; extend with a dedicated read-only statement builder and validated item capture. |
| `app/routes/receivables.py` | Admin entry/detail paths; add the statement shortcut and protected preview/PDF endpoints. |
| `app/templates/partials/receivables_workspace.html`, `static/js/receivables-dated.js` | Shared receivables entry/detail interface; add structured item capture and an admin-only export action. |
| `app/models/order.py`, `app/models/order_item.py` | Existing ordered-item snapshots and modifiers; reuse validated source data where exact debt attribution is known. |
| `app/services/export_service.py` | Shared PDF rendering. Use a dedicated customer-statement template/context. |
| `app/db/migrator.py` | Idempotent customer-account association, item/contact metadata, and indexes; preserve historical financial rows. |

The actor-ID mismatch was resolved: receivable writes now use the authenticated canonical `User` for both admin and staff. Tests deliberately use different Admin and User primary keys to verify the recording actor.

Implemented page: `/admin/reports` (Customer Statement mode). `app/routes/reports.py`, `app/services/customer_statement_service.py`, and the dedicated preview/PDF templates serve both this page and the shortcut from Receivables. The monthly accountant mode can be added separately.

## Implementation and verification sequence

1. Add/review stable customer-account mapping and retain open/closed cycles and legacy debts. Verify same-name and no-contact cases before combining history.
2. Add immutable menu-item snapshots for new debts and optional ordering-contact metadata, preserving old descriptions. Verify no duplicate orders, stock movements, or cash entries.
3. Build a single statement data builder with grouped payments, reconciled totals, running balances, and clear historical-data limitations.
4. Add the Customer Statement mode, admin Receivables shortcut, and a dedicated customer-only PDF.
5. Test the PHP 360 / PHP 200 / PHP 160 example, split payment allocation, several partial payments, fully paid closed tabs, reopened cycles, renamed menu items, manual historical charges, missing payment detail, and conflicting balances.
6. Test customer separation with identical names, different contacts, tampered IDs, staff/anonymous requests, and an export larger than one on-screen page. Assert salary and other customers' data are absent from the PDF context and extracted PDF text.
7. Render and inspect a real multi-page PDF and confirm the preview, detail rows, totals, and existing receivable balance agree. Test mobile layout and failure recovery.
8. Local implementation is complete. Any production schema migration/deployment requires the normal separately authorized backup and rollout.

**Done when:** the owner can select any confirmed receivables account, export its complete recorded charge/payment history, and hand the customer a clear, accurate explanation of the amount still owed.
