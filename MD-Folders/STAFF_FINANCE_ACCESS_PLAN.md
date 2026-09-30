# Staff access to Receivables, Daily Balance, Expenses, Payables, Inventory, and Menu

**Status:** Implemented locally on 2026-09-30; production deployment pending. Existing staff Expenses and Receivables flows remain in place. Staff use the shared Inventory, Menu, Daily Balance, and Payables management pages with the same actions as admin on those pages. Staff-facing pages and APIs use `/staff/` URLs so Cloudflare's `/admin/` access rule does not intercept them.

## Confirmed permission matrix

| Area | Logged-in staff may | Admin retains |
| --- | --- | --- |
| Receivables | View/filter, create a debt, record a customer collection by method, update notes using the existing staff flow | Existing admin-only account actions, if any |
| Daily Balance | View live cards/reports, export CSV/PDF/Excel, generate a daily report and AM/PM soft balance snapshot with their own name and notes | The same Daily Balance actions; unrelated admin finance routes stay protected |
| Expenses | View/filter and log an expense with a payment method using the existing staff flow | Void an expense and other admin-only corrections |
| Payables | View/filter, create a supplier payable, record full/partial payments with a method, view payment history | Any future correction/void permission not specifically granted here |
| Inventory | Use the same stock, ingredient, recipe, serving, and history controls as admin; changes are attributed to the logged-in staff account | The same Inventory actions |
| Menu | Use the same page and create, edit, variant, availability, delete, category, price, image, and meal-option actions as admin | The same Menu actions |

The user explicitly approved staff creating and paying Payables. Staff actions must attribute the actor and appear in the same financial ledger as admin actions. A link in the sidebar is not sufficient permission; the page, its data APIs, and export requests must all work for staff.

## Existing path

`app/templates/layout.html` links staff to Expenses, Receivables, `/staff/daily-balance`, `/staff/inventory`, `/staff/menu`, and `/staff/payables`. The four `/staff/` blueprints reuse the admin handlers and service paths, with staff-or-admin route guards and middleware protection. Staff can save daily reports and soft balances through `/staff/daily-balance/api/...`; both retain the logged-in actor and use the same ledger. Admins retain their `/admin/` URLs. The shared `PayableService.mark_paid` still handles funding source, method balance, idempotency, and the ledger.

## Phases

### 1. Route authorization

1. Reuse the Daily Balance handlers under `/staff/daily-balance` for staff and `/admin/daily-balance` for admins. Allow daily-report and soft-balance POSTs for staff; validate dates, AM/PM period, and notes, and attribute snapshots to the logged-in user. Keep unrelated admin finance routes protected server-side.
2. Reuse Payables handlers under `/staff/payables` for staff and `/admin/payables` for admins. Require normal CSRF/request-key checks, and keep payment amount, method, remaining balance, and idempotency validation in the service.
3. Reuse Inventory handlers under `/staff/inventory` for staff and `/admin/inventory` for admins. Stock changes retain the actor and item-level history; deleting a stock record archives its prior logs into durable inventory actions before the row is removed. Point the staff sidebar and mobile drawer to the staff URLs. Keep `/admin/*` restricted to admins.
4. Reuse the Menu page and handlers under `/staff/menu` for staff. The same category, item, variant, price, image, modifier, availability, and delete actions use CSRF and duplicate-submit protection. Keep the staff Menu navigation and order-category fetches off `/admin/*`.

### 2. Financial integrity and UI

1. Keep existing method options (Cash, GCash, supported banks), same-day business/external funding decision, partial-payment balance, actor, timestamp, and immutable payment rows for staff Payables. One staff payment must appear once in Payables history and in `SalesRepository.daily_ledger`, live Daily Balance, generated report/export, and method breakdown. Do not count payable payments as revenue.
2. Existing staff Expenses and Receivables continue to use their service methods so amounts and methods reconcile. Keep expense void and other corrections admin-only. The staff Daily Balance uses the same Asia/Manila day boundaries and numbers as admin, including prior-day filters; no separate arithmetic in the template.
3. In the shared or staff-specific UI, show a clear permission-aware state for admin-only buttons. A disabled/hidden button does not replace endpoint authorization. Provide useful JSON errors for denied API requests and readable empty/loading/error states.

### 3. Verification

- Log in as staff: all six sidebar links open and load data; staff can create an expense, create/collect a receivable, create/pay a payable, update and inspect inventory, manage the Menu with the same controls, and view/export Daily Balance and generate a report and soft balance. Log in as admin: existing actions still work, including serving updates through the inactive admin shadow user.
- Try staff requests directly to admin-only expense void, admin management, and any checkout-void approval: return forbidden with no data change. Unauthenticated and unrelated roles are denied. Staff `/admin/` requests stay blocked.
- Make a staff payable payment via GCash and one external-funded payment; verify remaining supplier debt, payment history, per-method ledger, live balance and report/export agree. Retry the same request key and confirm exactly one payment row.
- Run focused authorization, payable/expense/receivable, and ledger-to-Daily-Balance tests; inspect the final diff.

## Done when

Staff can use the six agreed areas and the listed actions without gaining unrelated administrator privileges; stock history remains attributed, and finance history reconciles for every payment method.
