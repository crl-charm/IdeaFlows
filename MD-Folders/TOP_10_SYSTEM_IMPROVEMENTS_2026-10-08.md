# IdeaHub: Top 10 System Improvements

Review date: **8 October 2026**  
Status: **Recommendations; application fixes have not been implemented by this review.**  
Reviewed checkout: `master`, commit `022f288`, including the current uncommitted cash-box, expense, payable, and Daily Balance work.

## Purpose and scope

This report answers: **Which ten changes would make IdeaHub better, what is wrong today, why does it matter to the business, and how should a developer fix it?**

The review traced checkout, ordering, inventory cancellation, bookings, payment handling, Analytics, Daily Balance, shared UI rendering, and the backup helper. It includes direct tests against an isolated in-memory database. It is a targeted review of these paths, not a claim that every line or every production configuration has been audited.

The current local cash-box changes are included because they affect how the system behaves now. Their presence locally does not establish that they are deployed. Existing application edits were preserved. Only this report was added for this request; no production database, VPS service, or Cloudflare resource was changed.

For broader history and the existing backup procedure, read [PROJECT_HISTORY_AND_R2_BACKUP_GUIDE.md](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/PROJECT_HISTORY_AND_R2_BACKUP_GUIDE.md).

Source-link labels identify repository paths. Click targets use this Windows checkout. A future developer should resolve those paths in their own checkout and recheck line numbers after edits.

## Recommended priorities

**P1** means a security, money, stock, or booking-integrity issue worth addressing promptly. **P2** means a worthwhile correctness, usability, performance, or operational improvement after the immediate integrity fixes. Scope estimates describe complexity, not promised delivery times.

| Rank | Improvement | Priority | Main benefit | Evidence | Scope |
| --- | --- | --- | --- | --- | --- |
| 1 | Render customer names and messages safely | P1 | Protect staff/admin browser sessions | Traced active input-to-HTML path | Small |
| 2 | Keep order retry protection in the database | P1 | Prevent duplicate orders and stock deductions | Reproduced through the real endpoint | Medium |
| 3 | Serialize food cancellation with checkout | P1 | Keep receipts, payment totals, and stock consistent | Traced competing transaction paths | Small change; concurrency verification |
| 4 | Make booking reservation and start checks atomic | P1 | Prevent overlapping bookings and duplicate sessions | Traced check-then-write paths | Medium |
| 5 | Reject unsupported payment methods | P1 | Keep Cash/GCash/bank reconciliation accurate | Reproduced through checkout | Small |
| 6 | Reconcile Analytics with Manila dates and the sales ledger | P1 | Make reports agree on actual sales | Reproduced against Daily Balance | Medium |
| 7 | Deduct retained credit from “Still to Collect” | P2 | Show the amount actually still owed | Reproduced against checkout preview | Small |
| 8 | Give Analytics trustworthy loading, error, and date states | P2 | Stop users mistaking old charts for new results | Traced active UI behavior | Small |
| 9 | Reuse Daily Balance ledger calculations | P2 | Reduce repeated database work as history grows | Instrumented actual ledger calls | Small–medium |
| 10 | Complete unattended backups and prove recovery | P2 / operations | Make recovery dependable | Repository gaps confirmed; live scheduler unverified | Medium |

For item 10, first verify the live backup situation. If there is no current successful daily backup or usable recovery copy, move that operational work ahead of the P2 UI and performance changes.

## 1. Render customer names and messages safely

### What happens today

The shared `showToast()` function joins its `message` directly into `innerHTML`. The pause/resume response includes the stored customer name, and the dashboard passes that response directly to the toast. HTML entered as a customer name therefore reaches an HTML-rendering context.

There is another unsafe interpolation in the active Analytics food list: the menu-item name is inserted into HTML without escaping.

**Code evidence:**

- [app/templates/layout.html:644](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/app/templates/layout.html:644): shared toast construction; unescaped message at line 655.
- [app/services/session_service.py:264](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/app/services/session_service.py:264): pause/resume message includes `sess.customer_name`.
- [app/templates/dashboard.html:305](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/app/templates/dashboard.html:305): response message is passed to `showToast()`.
- [app/templates/analytics/_content.html:314](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/app/templates/analytics/_content.html:314): raw `food.name` in generated HTML.

### Why it matters

This is a stored HTML injection/XSS risk in authenticated screens. A malicious stored value could execute browser code with the privileges of the staff member or admin viewing it. Ordinary names containing HTML-like characters can also display incorrectly.

### Smallest useful implementation

Keep the existing toast design. Create its static markup, then assign the message through `textContent`. Render menu/customer values through text nodes or the existing HTML-escaping helper in HTML text contexts. Review direct callers so a caller intentionally supplying HTML is converted to a safe structured rendering path if needed. Do not solve this by forbidding normal punctuation in customer names.

### Completion checks

- A name containing `<`, `>`, quotes, and `&` displays literally in pause/resume messages and Analytics.
- No input-derived element or event handler is created in the DOM.
- Existing toast icons, colors, dismissal, and accessibility still work.

**Evidence limit:** The active source-to-render paths were verified. No browser exploit was executed during this audit.

## 2. Keep order retry protection in the database

### What happens today

The `idempotent_request` decorator remembers an order request for 180 seconds in Redis or local process memory. The order route does not pass the request key into order creation, and the `Order` model has no durable key for identifying a replay.

**Code evidence:** [app/core/idempotency.py:43](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/app/core/idempotency.py:43), [app/routes/order_routes.py:47](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/app/routes/order_routes.py:47), and [app/models/order.py:4](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/app/models/order.py:4).

### Reproduced example

Using the actual `/api/add-order` endpoint with one intended item, the same request key, and a controlled clock:

| Step | Response | Result |
| --- | --- | --- |
| First submission | HTTP 200 | Order recorded |
| Immediate replay | HTTP 409 | Duplicate blocked |
| Replay after 181 seconds | HTTP 200 | Second order recorded |

The database contained **two orders**, and stock fell from **10 to 8** for one intended order. This reproduction used isolated SQLite and did not touch business data.

### Why it matters

A slow connection, lost response, or delayed retry can add the same food to the bill again and deduct stock again. Restarting a worker can also lose local-only protection. A short cache lifetime is insufficient to identify an already committed business operation.

### Smallest useful implementation

Pass the request key into `OrderService.add_order()`. Persist a uniquely constrained, actor-scoped key with the order in the same database transaction as its items, stock allocation, and financial history. Return the existing order/result for an identical replay. Reject reuse of a key with a different payload. Coordinate the frontend so each deliberate new order gets a new key and retries retain the original key.

Existing persistent request-key patterns in the inventory/cash flows can guide this change. Keep the short-lived decorator as supplementary coordination if useful; the database must enforce the durable guarantee. Account for existing rows in the migration and for the route's current support for requests without keys.

### Completion checks

- Retry immediately, after 181 seconds, after cache loss, and after a response fails following a successful commit.
- Each case produces one order, one stock allocation, and one financial history effect.
- Concurrent requests with the same key cannot both commit.
- A deliberately new order with a new key still works.

## 3. Serialize food cancellation with checkout

### What happens today

Food cancellation locks the `OrderItem`, then reads the customer session without a lock. Checkout locks the customer session and calculates its food bill. These operations do not share the same initial lock.

**Code evidence:** [app/services/order_service.py:318](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/app/services/order_service.py:318) and [app/services/session_service.py:420](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/app/services/session_service.py:420). Checkout reads the food total at line 448.

### Failure scenario

1. Staff A begins cancelling an item and sees that its session is active.
2. Staff B checks out the session and calculates the bill while that item still exists.
3. Checkout and cancellation complete without a shared session lock ordering them.
4. The paid total can include food that the cancellation subsequently changes/removes and returns to stock.

### Why it matters

The recorded payment, order details, and inventory can disagree. The error depends on timing, so a cashier may be unable to explain it by looking at the screen afterward.

### Smallest useful implementation

Acquire the customer-session lock before locking or changing its item. Reread the session's current status under that lock, and reject cancellation after checkout has completed. Follow the session-first lock order already used by order creation. Preserve cancellation reasons, actor details, stock disposition, and before/after financial history.

### Completion checks

- Cancellation wins first: checkout bills the reduced food total and stock is restored once when appropriate.
- Checkout wins first: cancellation reports that the session is closed; the paid order and stock remain unchanged by that rejected cancellation.
- Exercise both orderings against an isolated MySQL database with separate connections.

**Evidence limit:** This is a code-supported concurrency risk. The competing transactions were not executed against MySQL in this review. SQLite tests cannot establish the behavior of MySQL row locks.

## 4. Make booking reservation and start checks atomic

### What happens today

Booking creation checks for conflicting reservations before inserting. Starting a booking reads its status and occupancy before creating a customer session. The repository reads involved do not lock the shared resource or booking through those decisions.

**Code evidence:** [app/services/booking_service.py:75](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/app/services/booking_service.py:75), [app/services/booking_service.py:232](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/app/services/booking_service.py:232), [app/repositories/booking_repository.py:13](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/app/repositories/booking_repository.py:13), and [app/repositories/booking_repository.py:51](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/app/repositories/booking_repository.py:51).

### Failure scenarios

- Two staff members, using different request keys, both see the same slot as free and save overlapping bookings.
- Two requests both see one booking as `booked` and start separate customer sessions before the booking's `session_id` is overwritten by the later write.
- An extension or time edit can race with another reservation checked against the old schedule.

### Why it matters

The business can promise the same room twice or create duplicate billable sessions. This causes customer disputes and manual reconciliation even if each individual form submission is valid.

### Smallest useful implementation

Use a shared space/resource lock around availability checks and writes. Lock the booking for status transitions, and perform current reads after obtaining the lock. Whole-hub bookings, boardroom bookings, and relevant walk-in check-ins must coordinate on the resources they share. Use one consistent lock order.

Reuse the existing space-lock/current-read approach in [app/repositories/session_repository.py:69](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/app/repositories/session_repository.py:69) rather than adding a separate distributed locking service. Locking only existing conflicting bookings is insufficient when the contested slot is empty.

### Completion checks

- Two competing reservations produce one accepted booking and one understandable conflict response.
- Concurrent starts create exactly one linked customer session and one successful start history event.
- Booking extension, time changes, whole-hub reservations, and walk-ins respect the same occupancy rules.
- Run these interleavings against isolated MySQL; verify the resulting bill and booking history.

**Evidence limit:** The race is supported by the current read/write paths; no production overlap or live MySQL race was demonstrated.

## 5. Reject unsupported payment methods

### What happens today

`normalize_payment_method()` maps any unknown value to `cash`. Checkout calls it before processing payment.

**Code evidence:** [app/utils/payment.py:6](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/app/utils/payment.py:6) and [app/services/session_service.py:426](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/app/services/session_service.py:426).

### Reproduced example

A checkout submitted with `payment_method: "not-a-method"` and enough tendered money returned **HTTP 200**. Its stored transaction was **Cash, PHP 50.00**.

### Why it matters

A malformed request or frontend integration mistake becomes a valid-looking cash transaction. The cashier can then see a cash shortage even though the original error was a wrong payment-method value.

### Smallest useful implementation

Validate new writes against the existing allowed-method set and reject explicit unsupported values with a clear HTTP 400 response before financial mutation. Normalizing case and whitespace is reasonable. Preserve any intentional handling of a missing value separately, and inspect all callers before changing a utility also used to display historical records.

### Completion checks

- Unsupported strings and malformed value types return a validation error.
- A rejected checkout creates no transaction/history entry and leaves the session active.
- Cash, GCash, BDO, BPI, and QueenBank still follow their intended flows.
- A valid checkout appears under the matching payment method in Daily Balance and its export.

## 6. Reconcile Analytics with Manila dates and the sales ledger

### What happens today

The active Analytics summary groups and filters `Transaction.created_at` using the stored timestamp's calendar date. These timestamps are stored in UTC, while Daily Balance uses Asia/Manila business days. Analytics also sums transactions without applying the ledger's approved-void treatments.

The UI calls `/api/analytics/summary`, which uses `AnalyticsReportService`; this is an active screen path, not just an unused helper.

**Code evidence:** [app/services/analytics_oop_service.py:42](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/app/services/analytics_oop_service.py:42), [app/controllers/analytics_controller.py:28](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/app/controllers/analytics_controller.py:28), and the existing treatment logic in [app/repositories/sales_repository.py:198](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/app/repositories/sales_repository.py:198).

### Reproduced example

The isolated data contained:

- A valid PHP 100 sale at `2026-10-06 16:30 UTC`, which is **7 October at 00:30 in Manila**.
- A PHP 40 sale on 7 October UTC that had an approved `false_entry` correction.

For the selected business date **7 October**, Analytics returned **PHP 40** and Daily Balance returned **PHP 100**. Analytics excluded the valid midnight sale from that date and included the false entry.

### Why it matters

An owner comparing charts, reports, and closing totals can get different answers for the same day. Customer-spending and food-revenue rankings also need clear definitions about settled sales, orders, discounts, and corrections.

### Smallest useful implementation

Use the existing daily ledger for the Analytics revenue series and matching financial totals. Use the existing Manila date helpers for date ranges and defaults. Carry those rules through the Analytics export. Define operational rankings explicitly: quantities ordered and money collected are different measurements and should have accurate labels and queries.

Do not merely add `is_voided = false` everywhere. The existing ledger preserves an original sale for a refund, records the refund on the decision day, removes false entries, and handles retained credit separately. Receivable collections must not become a second sale.

### Completion checks

- Transactions on either side of midnight Manila appear on the correct business day.
- False entries, refunds on a later day, retained credit, replacement checkouts, discounts, and receivable collections follow the existing ledger rules.
- For the same date range and sales metric, Analytics, Daily Balance, and exports agree by payment method.
- The PHP 100/PHP 40 example above returns the correct revenue consistently.

## 7. Deduct retained credit from “Still to Collect”

### What happens today

Today's stats sum the full time bill and food bill of active sessions. They do not subtract the session's retained credit. Checkout preview already calculates the amount still due using that credit.

**Code evidence:** [app/routes/sales_balance.py:206](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/app/routes/sales_balance.py:206) and the checkout credit calculation in [app/services/session_service.py:459](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/app/services/session_service.py:459).

### Reproduced example

For one active food-only session:

| Value | Amount |
| --- | --- |
| Current bill | PHP 100 |
| Retained credit already held | PHP 60 |
| Checkout preview shortfall | PHP 40 |
| Daily Balance “Still to Collect” | PHP 100 |

### Why it matters

The owner expects another PHP 100 even though only PHP 40 is due. Any projection using that number is inflated by money already retained.

### Smallest useful implementation

Calculate each session's remaining collectible amount as `max(current payable bill - applicable retained credit, 0)`, using the same money rounding and credit rules as preview. Reuse existing calculation logic where practical while preserving the bulk queries used for active sessions.

Clarify the UI label if the amount is an estimate before checkout discounts or payment-method selection. The amount still owed should not imply that every future payment will arrive as physical cash.

### Completion checks

- PHP 100 bill with PHP 60 credit shows PHP 40 still collectible.
- Full coverage and excess credit show zero collectible, with any refund obligation handled separately.
- No-credit sessions retain their current behavior.
- Preview, final checkout, credit history, and Daily Balance agree without counting retained money twice.

## 8. Give Analytics trustworthy loading, error, and date states

### What happens today

`loadAnalytics()` logs non-success responses and exceptions only to the browser console. Existing charts remain visible. There is also no request-sequence check to stop an older response overwriting a newer date selection.

**Code evidence:** [app/templates/analytics/_content.html:158](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/app/templates/analytics/_content.html:158), especially lines 177–189. The Daily Balance page already has a useful request-number and visible-error pattern at [app/templates/admin/daily_balance.html:422](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/app/templates/admin/daily_balance.html:422).

### User-visible failure scenario

An owner loads last week's chart, changes the dates, and clicks Update Report. If that request fails, last week's chart stays visible next to the newly selected dates with no visible failure message. Rapidly submitting two ranges can also display whichever response finishes last, even when that is the older request.

### Why it matters

The screen can look successful while showing the wrong period. This is a UI/UX problem with a direct effect on business decisions.

### Smallest useful implementation

- Show an accessible loading status and a visible error with a Retry action.
- Display the date range actually represented by the charts and the last successful update time.
- Keep previous results only with an explicit “showing previous results” state when refresh fails.
- Reuse the existing request-number approach so only the latest requested range can update the charts.
- Distinguish “no sales in this period” from “could not load data.”

### Completion checks

Simulate a server error, loss of connection, an empty successful result, and two responses arriving in reverse order. The visible date range must always describe the displayed result, errors must be visible without opening developer tools, and only the newest requested result should replace the chart.

**Evidence limit:** The behavior was traced in the active JavaScript. These UI failure scenarios were not executed in a browser during this review.

## 9. Reuse Daily Balance ledger calculations

### What happens today

`SalesService.list_reports()` builds the requested ledger and then calls cash-box summaries, which build another ledger from the cash-box opening date. Today's stats follow the same pattern. The browser requests both endpoints during `loadReports()` and configures that refresh through a 15-second smart poller, as well as socket events.

**Code evidence:** [app/services/sales_service.py:64](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/app/services/sales_service.py:64), [app/services/cash_box_service.py:50](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/app/services/cash_box_service.py:50), [app/routes/sales_balance.py:175](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/app/routes/sales_balance.py:175), and [app/templates/admin/daily_balance.html:383](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/app/templates/admin/daily_balance.html:383).

### Instrumented example

With cash boxes opened on 6 October and 8 October selected, a reports request plus a today's-stats request invoked `daily_ledger()` four times:

| Endpoint | First ledger build | Second ledger build |
| --- | --- | --- |
| Reports | 8 October only | 6–8 October |
| Today's stats | 8 October only | 6–8 October |

These are four ledger builds, not four SQL statements; each build reads several kinds of financial records. The repeated work was measured by wrapping the actual ledger method, without replacing its calculation.

### Why it matters

Every cash-box summary covers the history since opening. As months of transactions accumulate and more staff use the screen, these overlapping reads and calculations can increase database load and response time.

### Smallest useful implementation

Start with request-local reuse: load the required ledger once, then derive the selected report rows and cash-box running balances from that result. A historical report range earlier than cash-box opening still needs its own correct coverage; choose the earliest required date deliberately.

Measure again before introducing checkpoints or a long-lived cache. Cash corrections and backdated financial entries make cache invalidation consequential. Keep the ledger authoritative and preserve financial output exactly.

### Completion checks

- Reduce the duplicate ledger builds within each reviewed endpoint while preserving all financial outputs.
- Compare reports, exports, cash-box openings/closings, and historical corrections before and after the change.
- Measure query counts, records loaded, and response times on a realistic isolated dataset.
- Verify a newly recorded payment or correction is visible immediately.

**Evidence limit:** Repeated calculations were measured. No production latency, database size, or speedup percentage was measured or promised.

## 10. Complete unattended backups and prove recovery

### What exists today

The repository uploader accepts a folder containing `pos_db.sql` and `production-files.tar.gz`. It asks interactively for credentials, uploads those two files, and compares remote object sizes with local sizes.

**Code evidence:** [scripts/upload_backup_to_r2.py:14](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/scripts/upload_backup_to_r2.py:14), [scripts/upload_backup_to_r2.py:33](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/scripts/upload_backup_to_r2.py:33), and [scripts/upload_backup_to_r2.py:49](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/scripts/upload_backup_to_r2.py:49).

The project history records a successful two-file R2 upload on 7 October. It also documents that a restore test and coverage of separately stored R2 menu media remain to be completed. Matching object sizes confirms that expected sizes arrived; it does not prove that SQL restores or that all needed assets are recoverable.

### What is not established by this review

The live VPS scheduler, today's backup status, retention settings, and recovery results were not inspected. Absence of a timer in this repository is not proof that no server-side job exists.

### Why it matters

A manual upload can be forgotten. A backup can exist while missing media or failing to restore. The business needs a predictable way to recover its financial records and application assets after data loss or a server failure.

### Smallest useful implementation

1. Inspect the existing VPS backup job and logs first; extend it if it already exists.
2. Extend the current helper to support protected noninteractive credentials. Keep credentials out of source code, this report, and logs.
3. Produce a dated, internally consistent database dump and required application-files archive. Record the application revision and backup format.
4. Include a separate recoverable copy of menu media stored in R2; the local-files archive does not cover remote objects by itself.
5. Write a manifest containing the backup's contents, sizes, checksums, creation time, and completion status.
6. Use one server-side scheduled service with a defined run time and protection against overlapping runs.
7. Record success and alert on failed or missing daily runs through an owner-approved channel.
8. Download a set, verify its checksums, and restore into a separate database and isolated application environment. Disable external services in that recovery test.
9. Verify representative receipts, payment history, Daily Balance totals, booking records, inventory, and menu images after recovery. Then apply an agreed retention policy to known-good completed sets.

### Completion checks

- A daily run succeeds without interactive prompts and records what it protected.
- A deliberately failed test run is visible, and a missing run is detected.
- A downloaded backup passes verification and restores successfully without touching production.
- The owner has a readable restore guide and knows the latest successful backup and restore-test dates.

No scheduler, cloud upload, retention deletion, or outbound notification was configured by this review.

## Verification performed for this report

### Existing focused tests

Executed with the working Python environment:

```powershell
.\.venv-phase2\Scripts\python.exe -m pytest -q tests/test_idempotency.py tests/test_phase4_query_efficiency.py
```

**Result: 10 passed.** The run emitted existing deprecation warnings. Passing these tests does not disprove the findings: immediate replay protection is covered, while the demonstrated delayed order retry is a different case.

### Additional isolated probes

The probes loaded the test isolation configuration before the application, used `sqlite://`, and disabled external services. They did not write persistent regression-test files.

| Probe | Observed result |
| --- | --- |
| Same order request after 181 seconds | Accepted again; two orders; stock 10 → 8 |
| Unsupported checkout payment method | HTTP 200; stored as Cash, PHP 50 |
| Analytics versus Daily Balance for 7 October | PHP 40 versus PHP 100 |
| PHP 100 active bill with PHP 60 credit | Stats PHP 100; preview shortfall PHP 40 |
| Reports plus today's stats with cash-box openings | Four overlapping ledger builds |

The XSS input/render path, concurrency risks, Analytics error behavior, and backup-helper limitations were checked in source. Browser execution, live VPS inspection, a MySQL concurrency test, and a backup restore were outside this review's executed checks.

## Suggested implementation sequence

1. **Small immediate fixes:** safe text rendering (#1), strict payment validation (#5), and retained-credit display (#7).
2. **Transaction integrity:** durable order replay protection (#2), checkout/cancellation serialization (#3), and booking coordination (#4).
3. **Trustworthy reporting:** Analytics financial rules (#6) and visible loading/error/date states (#8).
4. **Measured performance:** remove repeated ledger work (#9) after the financial output is protected by meaningful tests.
5. **Operational recovery:** verify the live backup state now and complete #10 alongside application work. Escalate its priority if current backups or recovery copies are missing.

This sequence favors a few small fixes first while keeping the larger integrity work near the front. It is not a recommendation to implement all ten in one large change.

## Handoff instructions for the next developer or AI

- Read `AGENTS.md`, the `ponytail` skill in full mode, and the repository review skill when reviewing changes.
- Recheck the working tree before editing. This review included substantial existing uncommitted cash-box work; preserve it and determine which changes have since been committed or deployed.
- Reproduce the chosen finding on the current code before changing it. This report is dated evidence, not a guarantee that the issue remains after later fixes.
- Implement one coherent improvement at a time using the existing service/repository/UI paths. Add a new dependency or abstraction only when the existing paths cannot reasonably do the work.
- Keep financial history queryable: amount, payment method, Manila business date, actor, related entity, and before/after or remaining balance. A retry must not create duplicate financial effects.
- For money changes, add a focused path from the affected history to Daily Balance, payment-method totals, and the corresponding report/export. Verify the relevant history screen as well.
- Run the smallest meaningful tests for the affected behavior. If the implementation crosses several domains, follow the repository's full-suite requirement. Use isolated MySQL tests for the locking cases; the current SQLite-only CI setup does not verify those concurrency guarantees.
- Inspect the final diff for unnecessary complexity and regressions. Report what was actually verified and what still needs a production or recovery check.
- Do not mark an item complete merely because the UI looks better or a successful HTTP response was returned. Use its completion checks above.

The highest-value outcome is a system whose orders cannot duplicate on retry, whose money and inventory agree, whose bookings stay consistent under concurrent use, whose screens clearly describe their data, and whose backups can actually be restored.
