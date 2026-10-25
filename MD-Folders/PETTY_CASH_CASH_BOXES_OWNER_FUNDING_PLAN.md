# Petty cash, cash boxes, and owner-funded expenses

Status: **implemented locally**. Production data and the VPS are unchanged; deploy only after the backup and migration checks below.

## Agreed business rules

1. Track two cash boxes: **Petty cash** (cash handed to staff for business purchases) and **Customer cash** (cash received from customers). Show each box and their combined cash held on Daily Balance.
2. The owner supplies petty cash from personal money. Each handover is a separate entry, so ₱300 in the morning and another ₱300 in the afternoon are both visible. The amount is variable; there is no automatic ₱300 daily entry.
3. Unused cash in either box carries into the next day. Set one opening cash count **per box** when tracking begins. An opening count is a starting balance, not a new inflow or sale.
4. Staff and admin can record top-ups, withdrawals, and reversals. Every entry shows the logged-in actor, actual time recorded, Manila effective date, amount, box, and reason or note. Reversing an entry keeps the original and adds a linked reversal; it never deletes history.
5. Allow a past effective date for a top-up or withdrawal, but display when it was actually entered. A backdated entry updates that date's live Daily Balance and subsequent running balances. Do not silently overwrite an older generated snapshot.
6. Cash checkouts and cash customer-debt collections enter **Customer cash** automatically. Cash checkout refunds leave Customer cash. For cash Expenses and cash Payables payments, staff choose **Petty cash** or **Customer cash**. A cash Expense can instead be marked **Owner paid directly**, meaning no business cash box changes.
7. On each owner top-up and owner-paid-direct Expense, ask whether the business must repay the owner. If yes, create a linked amount owed to the owner using Payables. Repaying it later reduces the selected business cash box or digital payment method, and must not record a second Expense.
8. The owner can take money out of either box. Record the box, amount, recipient, purpose, date, actor, and running balance. A withdrawal is not a business Expense. If the cash is repayment of an owner payable, record it through that payable's payment flow instead of also recording a withdrawal.

## Why a separate entry type is needed

- `app/services/expense_service.py` currently marks **every cash Expense** as `funding_source="business"`. An owner-paid cash purchase therefore reduces business cash incorrectly. Keep `payment_method="cash"` as the real method and distinguish the funding source and cash box; do not add a sixth payment method named `Cash (Owner's money)`.
- `app/repositories/sales_repository.py::daily_ledger` derives today's cash figure from dated cash receipts and outflows. `app/templates/admin/daily_balance.html` explicitly says that figure excludes opening cash. It cannot represent cash carried from yesterday until opening counts and movements between days are tracked.
- A `FinanceTransaction` with type `income` flows into **Other Income**. Money handed over by the owner must be shown as owner funding, never checkout sales or Other Income. The IFRS Conceptual Framework also distinguishes owner contributions from income; the app should avoid claiming whether a particular repayable entry is equity or a loan without that per-entry choice. [IFRS Conceptual Framework](https://www.ifrs.org/content/dam/ifrs/publications/pdf-standards/english/2019/issued/part-a/conceptual-framework-for-financial-reporting.pdf?bypass=on)
- Petty cash history must show each handover and the business spending it funded. Cash counts and supporting receipts should reconcile with the recorded balance. [Cornell petty cash guidance](https://finance.cornell.edu/accounting/topics/pettycash)

## Intended screens and workflow

### Start tracking

1. Show a one-time **Opening cash counts** setup on Daily Balance. Enter separate physical counts for Petty cash and Customer cash and a Manila start date. Explain that these are the amounts at the **start** of that day; choose a day before its transactions begin. Do not calculate a baseline from older records with unknown cash custody.
2. Save the two opening entries together, with actor and actual recording time. Prevent a second baseline for either box. Any correction uses linked reversal/replacement history rather than editing the row.
3. Historical reports before this start date keep their present movement-only meaning. Do not guess which old cash Expenses or Payables came from which box.

### Daily actions

1. Put a **Cash Boxes** action in the shared top bar beside Time In / Out and Orders. Admin and staff both see it; give the mobile icon a text label for screen readers. The modal shows Petty cash, Customer cash, and combined balance before entry.
2. **Add petty cash:** date defaults to today in Asia/Manila; enter the amount and optional handover note, then choose **Owner repayment needed: Yes/No**. Save each handover separately; show the login name automatically, never accept a typed actor from the browser. The modal lists today's entries and links to the full dated history.
3. **Record cash taken out:** select a box, amount, recipient, purpose, and effective date. Display a confirmation containing the box and amount. Prevent ordinary withdrawals from being used to settle an owner payable silently.
4. **Reverse a mistaken entry:** both roles can reverse after giving a short correction reason. A correction to an entry that never happened reverses its original effective date while retaining the actual reversal time; a real return of cash today is a withdrawal or owner-payable payment dated today. Show original entry, reversing actor/time, and linked replacement when applicable.
5. **Log Expense:** when payment method is Cash, show three plainly named funding choices: `Petty cash box`, `Customer cash box`, `Owner paid directly`. The first two are business-funded cash and reduce the chosen box. The third is external-funded cash and reduces neither box. Ask the repayment question only for Owner paid directly. Keep the receipt/expense date separate from the actual Manila posting day.
6. **Pay a supplier:** when method is Cash, require a box choice; store it in the payment history. Keep existing digital-payment funding behavior. An owner reimbursement payable is visibly labelled as such in Payables rather than appearing to be a new supplier purchase.

### Daily Balance

- Replace the current ambiguous Cash on Hand presentation with **Petty cash held**, **Customer cash held**, and **Total cash held**. These are running balances from the opening counts. Also show **Today's cash movement** separately so the owner can see what changed on the selected day.
- Show **Owner cash added today** and **Cash taken out today** as separate lines. Top-ups affect the cash box and cash movement, but never `total_revenue`, Cowork/Cafe sales, debt collection, or `total_other_income`.
- Keep `total_expenses` inclusive of owner-paid-direct Expenses; put them in `total_external_expenses` and exclude them from business cash outflows. A later reimbursement is a settlement of the linked owner payable, not another Expense. Show owner reimbursements separately from ordinary supplier payments on Daily Balance while still subtracting the payment once from the chosen method.
- For each selected Manila day, show opening amount, cash received, top-ups, cash spending, withdrawals, and closing amount for each box. `closing = opening + receipts + top-ups − business cash outflows − withdrawals`. The next day's opening equals the previous day's closing.
- The cash payment-method row must reconcile to the **combined daily change** of the two boxes. Update the live cards, dated reports, generated and soft balance snapshots, payment reconciliation, and CSV/PDF/Excel together from the same source events. Show late-entered/backdated changes as a live-versus-snapshot difference, with entry history, rather than silently changing the snapshot's original recorded values.
- Keep the existing active-session projection labelled as an estimate; unpaid bills are not physical cash in either box.

## Data and server design

1. Add one append-only cash-box event table through `app/models/`, `app/models/__init__.py`, and `app/db/migrator.py`. Each row needs event kind (`opening`, `owner_topup`, `withdrawal`, `reversal`), box (`petty`, `customer`), positive amount, signed balance effect, Manila effective date, UTC recorded time, actor ID and displayed-name snapshot, note/recipient, reimbursement choice, linked reversed entry, and a unique request key. Retain a balance-before/after snapshot at posting and calculate dated balances from the event and money histories.
2. For a repayable owner top-up, create a linked Payable in the **same database transaction**. For a repayable owner-paid-direct Expense, create a linked Payable in the same transaction as the Expense. A unique source link prevents duplicate owner debt on retry. Tag its payments as owner reimbursements so the Daily Balance cash outflow is counted once without inflating ordinary supplier-paid totals. A reversal must also resolve the linked unpaid debt or require an explicit repayment correction if it has already been paid; never erase a payment history row.
3. Add nullable `cash_box` provenance and that box's balance-before/after snapshots to new business-funded cash Expenses and Payable payments. Old rows remain unassigned instead of being guessed. Owner-paid-direct cash Expenses keep `payment_method="cash"`, `funding_source="external"`, and no business cash box. Their voids reverse the original funding choice and retain the existing void actor/reason history.
4. Route new cash checkouts, cash credit receipts, cash receivable collections, cash refunds, and existing cash finance adjustments to Customer cash. Cash Expenses and Payable payments use the selected box. Allocate all other cash movements explicitly during implementation; do not leave a cash ledger source outside both boxes. Preserve their current amount, date, and refund rules.
5. Extend `SalesRepository.daily_ledger` and `method_balance` once so all consumers receive the same owner-funding and withdrawal buckets. Use the same Asia/Manila boundaries as existing sales, Expense, Payable, and Receivable histories. Provide a running-balance query from the opening date; avoid summing a whole history on every page poll if an indexed date query suffices.
6. Use shared staff/admin routes such as `/api/cash-boxes` rather than `/admin/...`, because staff access is also used behind Cloudflare. Reuse `staff_or_admin_required`, the existing idempotency mechanism, server-side Decimal validation, and a DB uniqueness constraint. Posting, reversal, owner payable creation, and box balance updates must be atomic and safe under concurrent requests. Expired sessions return the existing JSON `401`; permission or server errors never render as a zero balance.
7. Validate positive amounts with at most two decimals, known box/kind, valid non-future Manila date, required withdrawal recipient and correction reason, existing opening baseline, and one reversal per original. Accept backdates only from the chosen opening date onward. Show a negative calculated box balance as a clear shortage requiring investigation, not as a hidden zero.

## Files to trace or change during implementation

- Cash events, opening setup, migration: `app/models/`, `app/db/migrator.py`, and a small shared cash-box service/route under `app/services/` and `app/routes/`.
- Expense choices and source history: `app/models/expense.py`, `app/services/expense_service.py`, `app/repositories/expense_repository.py`, `app/routes/expenses.py`, `app/routes/staff_expenses.py`, `app/templates/admin/expenses.html`, `app/templates/staff/expenses.html`.
- Cash Payables source and linked owner reimbursement: `app/models/payable.py`, `app/services/payable_service.py`, `app/repositories/payable_repository.py`, `app/routes/payables.py`, `app/templates/admin/payables.html`.
- Shared navigation and history: `app/templates/layout.html`, `app/templates/admin/daily_balance.html`, `app/routes/sales_balance.py`, `app/services/sales_service.py`, `app/repositories/sales_repository.py`, `app/services/daily_balance_export_service.py`, `app/templates/admin/daily_balance_report_pdf.html`.
- Tests: add focused cash-box and owner-reimbursement tests; extend `tests/test_expense_funding.py`, `tests/test_payable_funding.py`, `tests/test_daily_balance_ledger.py`, and relevant export tests.

## Verification examples and acceptance

1. Start both boxes at ₱0. Record owner petty cash top-ups of ₱300 and ₱300 on one day. Record ₱200 cash checkout and ₱50 cash debt collection. Record an ₱80 Expense from Petty cash, a ₱30 Expense from Customer cash, a ₱90 Expense paid directly by the owner, a ₱20 petty withdrawal, and a ₱100 customer-cash withdrawal. The day's closing balances are **Petty ₱500**, **Customer cash ₱120**, **Total ₱620**. Checkout sales are ₱200, total Expenses are ₱200 (₱110 business + ₱90 external), and owner top-ups add **₱0 revenue**.
2. A repayable ₱300 top-up creates exactly one linked ₱300 owner payable. A later ₱100 partial reimbursement shows ₱200 still owed, one payment-history row, and one dated outflow from the chosen cash box or digital method. It does not increase Expenses again. A non-repayable top-up creates no payable.
3. A retry with the same request key creates no duplicate top-up, withdrawal, Expense, or owner payable. Two concurrent cash actions cannot spend or reverse the same money twice. A correction keeps both entries, both actors, both timestamps, and a readable reason.
4. A late entry dated yesterday changes yesterday's live cash movement and today's opening/closing carried balance, but the audit shows it was entered today. The old generated snapshot remains reviewable with a visible difference. Crossing midnight uses Asia/Manila, including cash payments, Expenses, and refunds.
5. Cash Expenses, Payables, and refunds reduce the correct box. Owner-paid-direct cash Expenses and their voids leave both boxes unchanged. Historic pre-opening cash rows display **box unknown** and are not silently allocated to Petty or Customer cash.
6. Test staff and admin access, mobile modal labels and keyboard use, clear `401`/`403`/`5xx` failures, live refresh without Socket.IO, dated history, generated report, CSV/PDF/Excel, and equality between the cash reconciliation row and both boxes' combined daily change. Run focused tests and the full suite because this crosses expense, payable, cash, reports, and UI paths.

## Deployment gate

Back up MySQL and uploaded files to R2 and verify the backup; stop the service; fast-forward the reviewed commit; run the additive migration; verify new tables/columns; start the service; check readiness and warnings; compare one real dated top-up, one Expense of each cash source, and one cash withdrawal across history and Daily Balance. Do not reset production money records or retroactively classify old cash rows.
