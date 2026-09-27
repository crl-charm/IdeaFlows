# Budget Spending: current behavior and implementation plan

## Purpose

Explain what **Budget Spending** means in Daily Balance, how to record ordinary spending today, and how to make budgets useful without counting the same payment twice. This is documentation and a proposed implementation plan; it does not change the application or existing financial records.

## What works today

| Action | Where it is recorded | Daily Balance effect |
| --- | --- | --- |
| Log a paid expense | Expenses (`expenses`) | Increases Total Expenses and reduces Net Cash Movement. It reduces Cash on Hand only when the method is cash. |
| Pay a supplier bill | Payables payment history (`payable_payments`) | Increases Supplier Payments and reduces Net Cash Movement. Cash on Hand falls only for cash payments. |
| Record a Finance transaction of type `expense` | Admin-only Finance API (`finance_transactions`) | Increases Budget Spending and reduces Net Cash Movement. Cash on Hand falls only for cash transactions. |
| Create or change a budget amount | `finance_budgets` | No direct cash movement. A budget is a spending limit, not a payment. |

The ledger in `app/repositories/sales_repository.py` adds the three outflows separately. **If the same purchase is recorded both as an Expense and as a Finance budget expense, Daily Balance subtracts it twice.**

The Finance page at `/finance/budget` currently shows budget totals and recent transactions but has no form to set a budget or record a transaction. It is not linked in the main sidebar. The admin API at `POST /api/finance/transaction` can create a budget transaction, but that is not a practical daily workflow. The seeded Main Budget starts at ₱0, and the service can show a negative remaining amount because it does not enforce a budget limit.

### What to do in the current app

1. Record ordinary paid business costs, such as the ₱240 staff lunch, once in **Expenses** with the actual payment method and expense date.
2. Record a supplier bill in **Payables**, then record its payment there when paid. Do not log the same payment again in Expenses.
3. Leave **Budget Spending** at ₱0 unless there are independently verified Finance transactions that represent different payments. Do not send Finance API requests merely to make that card show an amount.
4. Use **Void Expense** only to correct a wrong or duplicate expense. A void keeps the history but excludes the original expense from the live totals for its expense date; it does not document a real refund.

**Example:** With ₱1,000 of recorded cash checkouts and one ₱240 cash expense, that day's Cash on Hand movement is ₱760. Recording the same ₱240 again as a cash budget transaction would incorrectly show ₱520. These figures exclude opening cash and are not the physical drawer balance.

## Recommended meaning of a budget

A budget should be a **plan for how much may be spent**, and its “Spent” value should summarize actual expenses already recorded elsewhere. Assigning an existing expense to a budget should not create another cash transaction.

Example: Set a ₱5,000 Staff Meals budget; log the ₱240 lunch in Expenses and assign it to Staff Meals. The budget page shows ₱240 spent and ₱4,760 remaining. Daily Balance still has one ₱240 expense and one ₱240 cash outflow. If the budget amount is later edited, Daily Balance does not change.

## Implementation plan

1. **Audit existing Finance transactions.** List all `finance_transactions` of type `income` or `expense`, their dates, methods, actors, amounts, and descriptions. Compare them with Expenses and Payables for possible duplicates. Preserve all records and do not automatically decide that similar amounts are duplicates.
2. **Define budget setup.** Give admins a visible Budget page and controls to create a named budget and edit its planned amount. Show total planned, spent, and remaining amounts. Editing the plan must not create income or cash movement. Store who changed the plan, when, and the before/after amount.
3. **Link actual spending once.** Add an optional budget choice when logging an Expense. Save the chosen budget with the expense, and show it in expense history. Calculate budget spending from active linked expenses. Voiding an expense removes it from current budget usage and Daily Balance totals while retaining the void actor, time, and reason. Supplier payments can be linked in a later change if needed; do not duplicate them as Expenses to get budget usage.
4. **Clarify Daily Balance.** Show linked budget usage as an informational subtotal labeled **“Expenses charged to budgets (already included above)”**. Do not subtract it again in Net Cash Movement or Cash on Hand. Keep older independent Finance transactions visible under a clearly named **Finance adjustments** section and count each verified independent movement once. Do not silently rewrite historical totals.
5. **Validate and reconcile.** Restrict budget management to admins. Check amount, method, date, budget ID, and duplicate request key on the server. An expense and its budget assignment must be saved together so a failed request cannot leave partial data. Keep the payment method and Asia/Manila business date consistent across Expenses, budget reports, Daily Balance, and exports.
6. **Verify before deployment.** Test one cash expense assigned to a budget, one noncash expense, an expense void, a duplicate retry, and a supplier payment. Confirm budget “Spent” is a subset of the underlying expense/payment history and that each actual payment affects Daily Balance exactly once. Review legacy Finance transactions separately before changing any production data.

## Acceptance checks

- An admin can set a budget amount without changing Cash on Hand or Net Cash Movement.
- A paid expense assigned to a budget appears in Expense history, budget usage, and Daily Balance, but creates only one outflow.
- Voiding an expense preserves its audit details and updates both budget usage and the original date's live totals.
- Payment-method totals and exports reconcile with the same source records; no budget subtotal is subtracted twice.
- Existing Finance transactions remain queryable, and any legacy duplicate is handled only after a manual audit.
