# Current Customer: public live bill view

**Date: October 26, 2026 · Status: implemented locally; production deployment pending.**

## Goal and agreed decisions

Let a customer open **https://idea-flows.online/current-customer**, find their name, and check their running bill without asking staff.

- Anyone with the link can open the page without logging in. The current customer names and bills are visible to other visitors to this page.
- Include active timed **Regular Lounge, Premium Lounge, and Boardroom** visits. A Boardroom booking appears once it has started and has an active customer session. Future bookings, Whole Hub, and food-only orders are outside this first version.
- Show Time Bill, Food Bill, and Running Total, with food order details available to expand.
- Use the same gold logo, favicon, Inter/Newsreader fonts, Bootstrap controls, and shared theme colors as the staff/admin dashboard and login pages. The shared branding head is `app/templates/partials/brand_head.html`; customer-specific CSS handles the public layout rather than defining another brand theme.
- Running Total means **Time Bill + Food Bill**, before checkout discounts and customer credit adjustments. Staff finalize those adjustments at checkout.
- Keep the current staff and admin dashboard layouts. Their existing actions update the same underlying visits and orders that this page reads.
- Reflect staff changes immediately whenever the live connection is available. Keep automatic refresh as a fallback.
- Customers can search and view details. They cannot add orders, edit, delete, pause, resume, or check out a visit from this page.
- A completed or cancelled visit disappears from the current customer list. Its existing business history remains in the system.

## Customer screen and flow

1. Open the page. Load the current customer list immediately, without waiting for a real-time connection.
2. Show all eligible customers as responsive cards, with a search field labelled **Search your name**. Search is case-insensitive and filters the already loaded list.
3. Each card shows the customer name, space, Manila time in, billable duration, Running/Paused status, Time Bill, Food Bill, and a prominent **Running Total**.
4. Expand **View food orders** to see item names, quantities, unit prices, and line totals. Show **No food orders yet** when appropriate.
5. Keep search text and expanded cards in place during refreshes. Use the visit ID to identify a card, so two customers named Carl, or two separate visits with the same name, are not merged. Space and time in help customers identify their visit.
6. Show the last successful update time and a connection/update status. Use a phone-friendly layout without horizontal scrolling.

Display this explanation beside the total:

> Running total = time bill + food bill. Discounts and any customer credit are finalized with staff at checkout.

Example: Carl in Premium can find his card, expand his Bangus Silog, fries, and iced latte orders, and see their recorded prices alongside his current time charge. Use actual saved order prices; the example does not establish menu prices or change billing rates.

## Staff action and customer page behavior

| Staff/admin action | Customer page result |
| --- | --- |
| Check in a Regular/Premium customer or start a Boardroom booking | The active visit appears. |
| Pause a Regular/Premium time bill | Show Paused; billable duration and time charge freeze. The customer stays visible. |
| Add food while time is paused | Food Bill and Running Total increase; the time charge stays frozen. |
| Resume time | Show Running; continue the existing billable duration using the normal billing rules. |
| Add or cancel an order item | Refresh item quantities, Food Bill, and Running Total after the change is saved. |
| Mark food served | Keep the food in the bill; serving is not payment or removal. |
| Complete checkout or cancel/remove an eligible active visit through an existing staff action | Remove the visit from the public active list after the saved change. |

This feature does not introduce another way to cancel visits or bypass the existing rules for cancelling a visit that already has orders or payments.

## Billing and public data

- Reuse the server's existing billing paths: `current_time_bill` and `billable_microseconds` in `app/utils/billing.py`, and the food/checkout breakdown in `app/services/session_service.py`.
- Keep existing started-block pricing, accumulated pauses, Boardroom booking rates, and saved item prices/modifiers. Do not reproduce billing arithmetic in browser JavaScript.
- Include all chargeable order items for the visit, including served items. Use saved item names and prices, rather than replacing them with the current menu price.
- If a reopened checkout carries an earlier food charge, show it as a separately labelled amount so the displayed breakdown explains the Food Bill. Preserve the existing retained time charge behavior.
- Calculate a response using one server timestamp. Batch-load active sessions, orders/items, linked bookings, and any needed carried charges; avoid calling a query-heavy checkout preview separately for every card.
- The total describes this active visit, not previous receivables or customer debt history.

Add these read-only HTTP interfaces:

- **GET `/current-customer`**: standalone public page using the existing brand assets, without staff navigation or staff session/activity scripts.
- **GET `/api/current-customers`**: JSON with an `as_of` UTC timestamp and a `customers` list. Each entry includes the visit ID, customer name, space, time in, billable seconds, pause state, public food item details, Time Bill, Food Bill, any separately labelled carried food charge, and Running Total.

Build an explicit public field allowlist. Do not return school/course, booking purpose, contact details, staff identity, payment credentials, internal audit history, or unrelated financial records. Preserve authentication on the existing staff/admin APIs and all write operations.

Return fresh responses with browser/CDN `no-store` controls. Keep the existing no-index headers. Use a dedicated feed rate limit that accommodates multiple customers sharing the venue's internet connection; handle a rate-limit response as a retryable update failure, not an empty list.

## Live updates and recovery

1. Add a separate public Socket.IO namespace, **`/current-customer`**, using the existing Socket.IO service. Its only application message is a server-to-client **`current_customers_changed`** notification with an empty payload. Customers fetch the approved public JSON after receiving it.
2. Keep the authenticated namespace and its room checks intact. Public connections do not join staff/admin rooms, modify authentication sessions, acquire login leases, or send business actions.
3. Reuse existing order, booking, and checkout notifications where possible. Add the missing change notification after successful check-in, pause/resume, and visit cancellation. Emit only after the relevant database commit succeeds.
4. Debounce bursts of notifications briefly and prevent overlapping refreshes from replacing newer data with older responses. A public notification failure must not turn an already saved staff action into an error.
5. Refresh immediately on first load, connection/reconnection, returning to the foreground, and coming back online. Also refresh every **five seconds while visible** to update time charges and recover missed events. Background tabs stop periodic requests and refresh when shown again.
6. The browser may animate billable duration from the latest server state while Running, but monetary amounts always come from the server. Pause freezes the displayed billable duration as well as the time charge. Socket changes trigger immediate refresh; time-only price-boundary changes are picked up by the periodic server refresh.
7. On HTTP/network failure, retain the last successful values, visibly mark them as out of date, and retry. Never replace a failed request with zero bills or **No customers**. An actual successful empty response shows **No current customers**; a search with no match shows **No matching customer found**.

Reference: [Flask-SocketIO namespaces and events](https://flask-socketio.readthedocs.io/en/latest/getting_started.html#receiving-messages).

## Verification and acceptance

- [x] Anonymous visitors can open the page and public feed without a staff login.
- [x] Only the three agreed active timed spaces appear; future bookings and completed/cancelled visits do not.
- [x] Time, food, and total amounts match the staff checkout preview before discounts/credit at the same server time, including billing boundaries, paused visits, Boardroom rules, modifiers, and carried charges.
- [x] Food added while paused changes only the food component and total. Served food remains chargeable.
- [x] Staff action tests cover check-in, pause/resume, item addition/cancellation, and checkout. Separate browser contexts confirm live pause/order updates without manually reloading the customer page.
- [x] Blocking the Socket.IO library/connection does not prevent initial loading or periodic updates. Reconnection and foreground recovery refresh the latest data.
- [x] Failed writes do not produce a verified public change, and failed reads do not display false empty/zero results.
- [x] Search, expanded details, duplicate names, and long item names fit 320px/375px phone, 768px tablet, and 1366px desktop layouts without sideways scrolling in Chromium. Physical Android/iPad testing remains pending.
- [x] Public HTTP/socket access cannot perform staff actions or receive private events. Existing authentication, session lease, billing, order, and booking regression tests pass.
- [x] Exercise multiple anonymous viewers sharing one IP so normal refresh traffic does not cause repeated rate-limit errors.

### Local verification record

- Automated suite: 316 tests passed in the full run; four existing admin-provisioning tests hit a Windows sandbox temporary-folder permission error before running. All four passed when rerun with a writable temporary folder under `instance/`. No application assertion failures remained.
- The new feature has 12 focused API, Socket.IO, billing, query-count, shared-IP, and browser-controller tests. These are included in the full-suite results.
- Real Chrome browser checks passed using a disposable in-memory database: anonymous live updates, search, preserved expanded orders, orders while paused, stale-data recovery, blocked-Socket.IO fallback, and all four viewport widths above.
- Import validation, JavaScript syntax checking, and Git whitespace checks passed.
- The public feed overrides the normal request limit with **2,400 requests per minute per IP** for shared venue connections. The controller respects `Retry-After` and backs off after failed requests. Billable duration, like the monetary amounts, comes from each server snapshot rather than a separate browser billing clock.
- Browser screenshots and test reports are local artifacts under `instance/`; the in-memory browser checks do not add transactions to the existing local database.
- Branding follow-up: dashboard, login, and customer pages now include the same shared branding head and theme stylesheet. The customer page uses the existing gold navigation logo and favicon, with page-specific CSS limited to its layout. Twenty relevant regression tests passed, and a real-browser comparison confirmed identical logo/favicon paths, body/heading font families, background, and brand color. All four viewport checks and live-update/recovery checks passed again.
- GitHub release verification on October 26: the expanded suite contains 325 cases. The full local run passed 319; five workflow cases required an unrestricted Git Bash process, and one older branding test needed to inspect rendered templates after the shared-head refactor. All five workflow cases then passed, and all 22 customer/branding/PWA/startup checks passed, including the corrected test. Import validation and public JavaScript syntax checks also passed. Test reports remain local under `instance/`.

**Done when:** customers can reliably see their current visit's running time and food charges, staff actions are reflected automatically, and public viewing grants no editing permissions.

## Rollout

Implement and test locally first. This document does not authorize an immediate production change. The current database already holds the visits, pauses, bookings, and orders; **no schema migration is expected**. Handle the GitHub push and production deployment separately, with the usual backup, health checks, and a controlled two-browser verification after deployment.

The approved October 26 publication scope is the customer page and its supporting backend/branding/tests, the customer plan, codebase review, revised R2 backup plan, and `.github/workflows/activity.yml` with its regression check. The backup/Telegram work remains documentation only. Publishing this release to GitHub does not deploy it to the VPS.

The activity workflow targets **4 commits at midnight**, **2 at 9:15 a.m.**, and **2 at 8:25 p.m.**, all Philippine time. It chooses the count from the triggering cron expression rather than the runner's current hour. GitHub schedules can be delayed, so the times are scheduling targets rather than guaranteed execution times. See [GitHub schedule behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).
