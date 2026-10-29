# Missed Customer Checkout and Staff Time Out Reminder

**Updated:** October 29, 2026  
**Status:** Implemented locally, with automated and desktop/mobile browser verification, and included in this source release. Production records and VPS configuration were not changed; VPS deployment has not been performed.

## Local implementation and verification

- **Use:** Restart the existing localhost application and refresh. As admin, open **Dashboard → View Order → Record missed checkout** for an ordinary Regular or Premium visit. Enter the actual departure, payment details and collector, review the corrected bill, then confirm that the payment has not already been recorded elsewhere. A mismatched amount cannot be saved.
- **History:** Checkout Records groups the payment by its actual Manila payment date, with a **Recorded late** marker. Its Time history shows both the original estimate and the completed correction, including the admin, collector and receipt. A later pause remains visible but does not add time after departure.
- **Staff Time Out:** An active-customer warning offers **Review customers** or **Confirm handover and save Time Out**. Neither action automatically pauses or checks out a customer.
- **Local schema:** Added `transactions.paid_at`, `missed_checkout_corrections`, and a payment-date index on `(paid_at, created_at)`. The existing recording-time index remains. The actual local SQLite query plan uses date ranges for both new and legacy payment branches. The normal migration command includes these changes for a future authorized release.
- **Local data protection:** Backed up `instance/ideahub_local.db` before the schema change to `instance/pre-missed-checkout-20261029-160451-e2997f.db`. All original row counts across the 34 pre-existing tables were preserved. The new correction table is empty; no real customer checkout was performed. A second local snapshot was made before refining the new index.
- **Automated verification:** The complete regression run passed **396 tests**. The final focused run passed **94 tests**, comprising **44 missed-checkout checks** and **50 related stock/order checks**, after the index refinement and final collector handling. These cover prior-month/year payments, Manila midnight, fractional pause precision, preservation of saved daily/AM-PM snapshots and inactive historical staff collectors. Imports, JavaScript syntax and changed-file whitespace checks also pass. Test results remain in `instance/missed-checkout-full-20261029.xml` and `instance/missed-checkout-final-focused-20261029.xml`.
- **Browser verification:** Synthetic local data only. Verified the actual admin form, mismatch blocking, CSRF enforcement, failed-save recovery, receipt/history, staff access restrictions, review-versus-handover behavior, and no horizontal overflow at **320, 375 and 768 pixels**. Browser test artifacts remain under ignored `instance/`.
- **Limits:** A physical iPad/Android device and a real MySQL concurrent-write run were not available. MySQL date SQL compiles successfully; transaction locking was reviewed and the relevant stock/checkout tests pass. Production still needs its own authorized backup, migration and live checks before this feature is released there.

Rio's actual departure, food/discount breakdown, payment method, collector and any previously recorded receipt still need the owner's confirmation before using this feature on that real visit.

## Goal and confirmed decisions

Give the owner a way to finish a genuine customer visit when staff forgot to record checkout, including after a power outage or loss of internet. The customer has already paid and left; the system needs the actual departure and payment recorded accurately.

- **Admin only**, inside the customer's **View Order** screen. No additional Dashboard header button.
- First version: **Regular Lounge and Premium Lounge only**.
- Actual departure may be on a **previous Manila day**. This differs from Late Customer Check-in, which permits earlier today only.
- If the recalculated bill differs from the reported payment, **stop until the time, orders, discounts, or payment details are reconciled**. No free-form amount override or new discretionary discount.
- Remind staff about customers still checked in **before saving Staff Time Out**.
- Keep the actual departure/payment timestamps separate from when the admin records the missed checkout.

## Incident motivating this feature

The user confirmed that Rio paid **PHP 168** and left, but checkout was missed. Staff paused the visit the next day after extra time had accumulated. This is a forgotten checkout; pausing the next day cannot remove time already counted.

The screenshot shows a paused Premium visit with **18:16:26** billable time and **PHP 370** time bill. That amount matches the current Premium pricing. The message mentions **PHP 498** and a real payment of PHP 168. The actual departure time, food/discount breakdown, payment method, collector, and any separately recorded payment still require verification. Do not infer Rio's food bill from those figures or change her live record from the screenshots alone.

## Admin flow

1. Open the active customer and choose **View Order → Record missed checkout**. Hide this action from staff and from unsupported session types.
2. Explain briefly: **Customer already paid and left. Enter the actual departure and payment details.**
3. Enter:
   - **Actual departure date and time**, using the familiar native date/time picker, labeled **Manila time**.
   - **Amount paid toward this bill**, as the net bill payment, not cash tendered before change.
   - **Payment method**, using the existing methods.
   - **Actual payment date/time**, initially matching departure. Allow correction when the customer paid at a different time.
   - **Received by**, selecting the actual staff/admin collector. The admin recording this correction may be a different person.
   - A short **reason**: Power outage/no connection, Forgot to record checkout, or Other. Other requires a short note.
4. Preview the current running estimate and the corrected bill side by side, with actual departure, billable duration, time charge, food charge, existing supported discount, total, reported payment, and any difference.
   Select a supported discount only if it was actually given; do not infer a discount from the reported payment or invent one to make the totals match.
5. Require confirmation that the payment was already received and has not already been recorded through another checkout, debt collection, or manual income entry. Show likely existing records for review when available; an amount match alone is not proof of duplication.
6. Enable **Record payment already received and complete checkout** only when the bill and reported payment match exactly to the cent and all checks pass. A mismatch displays **Review the arrival/departure, orders, discount, and amount received before continuing.** Preserve the form for review.
7. On success, complete the visit, release the seat, remove it from active staff/admin lists and the public customer page, and provide a receipt and correction history. Do not prompt the customer to pay again.

Use the existing modal patterns and a mobile layout without horizontal scrolling. If the main order modal opens a separate correction modal, hide/show them in sequence so focus and backdrops remain correct. No new picker library or staff approval queue is needed.

## Correct billing at a past departure

The existing `billable_microseconds()` uses `paused_at` whenever it is set. Passing yesterday's departure into that helper alone is insufficient when `paused_at` belongs to today.

1. Keep the original `CustomerSession.time_in` unchanged. The correction ends an existing visit; it does not create another check-in.
2. Calculate billable duration from Time In to the actual departure, subtracting only pauses overlapping that interval. Reconstruct pause/resume intervals from the existing time events. A pause or resume after departure stays in audit history but does not affect the corrected bill.
3. Do not subtract the entire current `paused_microseconds` aggregate blindly: some recorded pauses may have happened after the customer left. If pause history is missing or inconsistent enough that a valid result cannot be established, return a clear review-required result instead of guessing.
4. Preserve the current Regular/Premium started-block pricing and shared discount rules. Use one historical calculation for preview and final save. Test timestamp precision at charge boundaries, including existing MySQL timestamps without fractional seconds.
5. Retain the actual food items, saved prices, and modifiers. This operation must not delete food, reverse stock consumption, or change kitchen history to make the amount match. Flag clearly dated orders after the claimed departure for review. Per-item historical edits cannot be reconstructed reliably from the current `OrderItem` model alone; do not claim a complete historical food snapshot without evidence.
6. On completion, set Time Out to the actual departure, clear the open pause, and persist the final billable duration and applicable paused duration. Preserve the original pause state in the correction audit before replacing live state.
7. Snapshot the final billing start/end, duration, food/time totals, discounts, method, and customer details on the one checkout transaction. Preview must not create a sale or change the session.

Removing extra uncollected running time is a correction to the estimate. It is not a refund, an expense, or a promotional discount. A refund requires money actually returned; this case does not authorize one.

## Dates, cash, and financial reports

Keep three facts distinct:

| Fact | Meaning | Storage/report use |
| --- | --- | --- |
| Actual departure | When time billing ended | Session Time Out and `Transaction.billing_end_at` |
| Actual payment received | When the business received the payment | New `Transaction.paid_at`; sales and payment business date |
| Recorded at | When the admin saved the entry | Preserve `Transaction.created_at` as the actual recording time, plus the correction audit |

- Add nullable `paid_at` to transactions. Normal new checkouts set it to the current server time; missed checkouts use the verified actual payment time. Existing rows fall back to their existing `created_at`, preserving current historical totals without inventing better dates or rewriting old timestamps.
- Define one shared effective-payment-time rule, in Python and SQL: `paid_at` when present, otherwise `created_at`. Use Manila day boundaries consistently.
- Index `paid_at` and preserve the existing recording-time index. For bounded date queries, check the query plan and use indexed payment-time/null-fallback predicates where necessary instead of assuming a `COALESCE` filter uses those indexes.
- Apply that rule to Daily Balance, payment reconciliation, Cowork/Cafe sales, checkout date filters/grouping, relevant sales analytics, daily report detail queries, and PDF/Excel/CSV exports. This also establishes the correct source for the planned monthly accountant exports.
- Introduce explicit payment-date and recorded-at response fields. Checkout Records should label and group by the payment business date while showing a **Recorded late** marker and the actual recording timestamp. Do not silently rename the meaning of every existing `created_date` field.
- Keep latest-transaction lookups and audit ordering based on actual recording sequence/ID where that is their purpose. Do not replace every `created_at` reference mechanically; order placement, finance entries, staff attendance, and refund decision times have their own meanings.
- Void requests for a missed checkout must snapshot the original **payment business date**, not the later entry date. Preserve the established refund/retained-credit/false-entry rules and their own decision dates.
- A cash payment enters the customer cash ledger once, on the verified payment date. Do not add a second Cash Box top-up or manual income entry for the same money. Digital methods do not enter physical cash boxes.
- Check tracking/opening dates before applying a backdated cash receipt. Money already included in a later physical opening count must not be added to that running balance again. Keep actual cash-count and withdrawal records intact.
- Preserve existing saved reports, AM/PM counts, and posting snapshots. Recomputed live totals may change after the late entry; show that a late entry changed the ledger and make original snapshot differences visible instead of silently rewriting signed-off history.
- Store reported net payment separately from optional known tender/change details. If a cash customer paid a PHP 168 bill with PHP 200 and received PHP 32 change, the sale is PHP 168. If tender/change are unknown, leave them unknown rather than fabricating exact tender and zero change. The ordinary live cash-checkout validation remains unchanged.

## Data and audit design

Add a small `MissedCheckoutCorrection` model/table linked to the session and the transaction created by this action. Reuse the existing `SessionTimeEvent` history for the visit's visible time correction; do not try to fit all payment/reason metadata into its existing pause fields.

Persist at least:

- Session and resulting transaction IDs, with database constraints preventing another missed-checkout completion of that same visit.
- Actual departure and payment times, actual server recording time, and the relevant Manila business dates.
- Admin actor ID/name/role from authentication, actual collector ID/name snapshot, reason, and note.
- Reported net payment, payment method, and known tender/change information.
- Before/after billable duration and time/food/discount/total snapshots; the original active/paused state and a link to the final receipt.
- The request identity needed to identify a retry and the confirmed preview inputs/revision.

Append a time-history event recorded **now**, with explicit before/after snapshots calculated at their proper cutoffs. Do not reuse a helper that recalculates the corrected duration at the later recording time or invent a pause event in the past. Keep genuine next-day pause events visible, explaining that they occurred after departure.

New nullable payment-time fields, the audit table, and needed indexes require an **additive, idempotent migration**. Register the model and update demo/operational reset inventories in dependency order. Do not reset production data, change old receipt snapshots, or backfill guessed departure/payment/collector details.

## Server validation and consistency

1. Use dedicated admin-only preview and completion endpoints, for example `POST /api/sessions/<id>/missed-checkout/preview` and `POST /api/sessions/<id>/missed-checkout`. Preview is read-only. Both enforce authentication/authorization on the server; completion also uses the existing CSRF and idempotency patterns.
2. Support only a currently active, timed Regular/Premium visit with no completed checkout or conflicting debt/payment state. First version excludes Boardroom/Whole Hub bookings, food-only, retained-credit/reopened void corrections, and visits already handled through another financial flow. Keep those existing workflows available separately.
3. Strictly parse Manila date/time, convert to UTC, require departure after Time In and no later than server now, and require payment between check-in and server now. Payment and departure need not be identical. Allow genuine previous-day or previous-month entries.
4. Read the admin identity from authentication using its canonical `users.id`; do not mix an `Admin.id` with a `User.id`. Verify the chosen historical collector against stored accounts; a collector who later became inactive may still be a valid historical collector. Keep collector and recording admin distinct.
5. Parse money using the shared Decimal validation. Require reported net payment to equal the recalculated discounted total. Reject negative/invalid amounts and unsupported methods. Do not silently create a debt, refund, extra discount, or balancing income for a mismatch.
6. Lock and re-read the session for final save. Recheck pause history, orders, discounts, relevant existing payments, and preview revision before committing. If inputs changed after preview, return a conflict and require a fresh preview. Existing order-placement code already locks the customer session; verify all relevant concurrent mutations follow a compatible lock order.
7. Save the transaction, effective payment date, correction audit, time event, session completion, pause cleanup, and existing order finalization in one transaction. Any failure rolls back the whole operation.
8. Repeated or concurrent completion must create only one sale and one correction. A normal checkout racing the missed checkout must leave one completed visit, with the losing request receiving a clear conflict.
9. Commit before emitting authenticated/public change hints. A failed notification must not turn a saved financial entry into an error that encourages another payment record. Retain HTTP refresh/reconnect recovery.
10. A previously recorded manual income/debt payment must be reconciled through its existing audited correction path before this feature records another receipt. Do not identify or erase unrelated payments merely because their amounts match.

## Reminder before Staff Time Out

1. When staff press **Save Time Out**, check currently active Regular/Premium visits. If none remain, continue the current flow normally.
2. If visits remain, show an accessible confirmation listing customer name, space, Time In, and running/paused status. Explain: **These customers are still checked in. Review any missed checkouts or confirm another staff member is taking over.**
3. Provide **Review customers** and **Confirm handover and save Time Out**. Legitimate customers may still be using the space when one employee ends a shift, so acknowledgement must allow a normal handover.
4. Reuse the existing Staff Time Out request: without acknowledgement, the server returns the active-visit warning instead of saving Time Out. After confirmation, recheck the warning context and save once. If relevant active visits changed since the warning, return the updated list for review.
5. The reminder does not pause or check out customers, collect money, or change their bills. Staff can review and contact an available admin for a missed-checkout correction. It creates no scheduled service, offline write queue, or daily auto-checkout.

## Inspected files and implementation map

Line numbers refer to the source inspected on October 29 and may move.

| File/location | Relevant work |
| --- | --- |
| `app/templates/dashboard.html:154` and `:670` | Put the admin action inside View Order; add dated inputs, matching-payment preview, and clear already-paid confirmation on desktop/mobile. |
| `app/routes/session_routes.py:175` | Keep ordinary checkout automatic; add protected missed-checkout preview/completion endpoints. |
| `app/services/session_service.py:332`, `:469`, and `:515` | Current pause, preview, and checkout. Reuse pricing/payment/finalization logic with an explicitly validated historical cutoff; add atomic correction auditing. |
| `app/utils/billing.py:31` | Current helper uses `paused_at` even if after the requested cutoff. Add the smallest shared historical interval calculation needed for preview/save. |
| `app/models/transaction.py:29` | Preserve recording time; add nullable actual payment time and an explicit effective-time rule. |
| `app/models/session_time_event.py` | Preserve actual event timestamps and append the visible missed-checkout correction with explicit snapshots. |
| New `app/models/missed_checkout_correction.py` | Persist the correction's reason, actor/collector, times, amount snapshots, and receipt linkage. |
| New `app/services/missed_checkout_service.py` | Read-only historical quote, signed preview revision, duplicate-payment warnings and admin-only atomic completion through the existing checkout service. |
| New `app/templates/partials/missed_checkout.html` and `static/js/missed-checkout.js` | Admin correction modal, mobile form, matching-payment confirmation and failed-save recovery. |
| `app/db/migrator.py`, `app/models/__init__.py`, `app/db/reset_demo_data.py`, `app/db/reset_operational_data.py` | Additive schema/model registration and safe test/demo reset inventory. |
| `app/repositories/session_repository.py:222` and `app/dto/serializers.py:121` | Payment-date filters/grouping metadata and recorded-at visibility; preserve intentional latest-record ordering. |
| `app/repositories/sales_repository.py:78`, `:204`, and `:500` | Update all relevant checkout aggregates and daily detail queries to effective payment time. |
| `app/services/session_service.py:741` | Correct the original-business-date snapshot used by future void requests. |
| `app/services/cash_box_service.py:51` | Verify backdated cash and opening-date carryforward without double counting or rewriting physical counts. |
| `app/repositories/analytics_repository.py`, `app/services/analytics_oop_service.py` | Align checkout-based sales dates and Manila grouping where these views consume transactions. |
| `app/routes/receipts.py:72`, `app/templates/receipt.html`, `app/templates/checkout_records.html` | Show actual visit/payment times, late-entry marker, recorded-at information, and reachable correction history. |
| `app/services/daily_balance_export_service.py`, `app/templates/admin/daily_balance.html`, `app/templates/admin/daily_balance_report_pdf.html` | Keep live totals, snapshots, and exported dates/labels consistent. |
| `app/routes/staff_shifts.py:88` and `app/templates/layout.html:1393` | Add the active-customer reminder to the existing Staff Time Out save flow. |
| `app/services/order_service.py:93` and `app/repositories/order_repository.py:27` | Verify session locking, finalization, and stale preview protection against concurrent orders. |
| `tests/test_missed_checkout.py` | Financial dates, pause reconstruction, supported discounts, rollback/retry, permission boundaries, handover warning, migration and saved-snapshot checks. |

## Implementation and rollout order

Steps 1–5 are complete locally. Steps 6–7 remain separate production-release and real-incident checks.

1. Add the payment-time fallback, correction model, and additive migration; cover compatibility with existing records and date-based ledger queries.
2. Implement historical bill preview/finalization and the atomic admin-only save. Test the late pause, mismatch, duplicate, and failed-save cases before connecting the form.
3. Connect the action inside View Order and update receipts, history, date filters, void original-date handling, reports, analytics, and exports. Do not release just the button while ledger dates still use recording time.
4. Add the Staff Time Out reminder using the existing request/modal helpers.
5. Run focused financial/date/concurrency checks and the relevant full regression suite locally. Use disposable test records and inspect desktop/mobile screenshots.
6. Only after deployment is authorized: verify a fresh database/media backup in R2, apply the schema migration in the agreed maintenance window, check the new table/columns/indexes before starting the new app, and verify health and dated reports. No deployment is authorized by writing this document.
7. Before handling Rio's real visit, verify actual departure/payment details and confirm whether the PHP 168 was already recorded elsewhere. Do not use test data or screenshots as authority to modify a live payment.

## Verification and acceptance

- **Rio-shaped synthetic case:** a Premium visit starts October 27; the customer pays and leaves that evening, but staff pause it on October 28 and admin records checkout on October 29. The corrected duration ends on October 27, ignores the later pause for billing, retains its history, and records one verified payment on October 27. Example fixture prices/food must be explicitly synthetic; Rio's actual breakdown is still unverified.
- **Pause timeline:** no pauses, pauses wholly before departure, a pause spanning departure, a next-day pause, multiple pauses/resumes after departure, missing/inconsistent history, and second/fractional-second boundary behavior. Preview and final receipt must agree.
- **Pricing/payment:** Regular/Premium billing boundaries, placed/served food, supported discounts, digital methods, exact net-payment matching, known cash tender/change, and unknown original tender/change. No arbitrary amount override.
- **Dates:** previous day/month/year, Manila midnight versus UTC midnight, future/pre-arrival rejection, and different device timezones. A past payment changes the correct daily/monthly sales and method totals once; recording it today does not create another receipt today.
- **Reports:** old rows retain their totals through the fallback; Daily Balance, Cowork/Cafe/discount cards, Checkout Records, receipts, analytics, and PDF/Excel/CSV agree. A later void/refund follows the original effective payment date and actual decision date. Saved report/count snapshots remain visible as originally recorded.
- **Cash:** cash versus digital separation, paid-before-opening versus paid-after-opening, existing withdrawals, backdated corrections, and suspected already-recorded payments. No duplicate top-up, collection, refund, or manual income.
- **Safety:** anonymous/staff rejection, forged actor/collector inputs, CSRF, expired sessions, repeat clicks/retries, post-commit network/notification failure, simultaneous normal/missed checkout, and an order added between preview and confirmation. Verify one final transaction/audit or a complete rollback.
- **Reminder:** no active visits, active running/paused customers, reviewing instead of timing out, acknowledged handover, changing warning context, duplicate Time Out submission, and a lost connection. Customer states and bills remain untouched by the reminder.
- **Usability:** action remains inside View Order; entered values survive a failed save; admin can review an exact difference; phone/tablet forms and history need no side scroll. Claim physical-device verification only after testing that device.

**Done when:** an admin can accurately record an already-paid missed checkout without charging the customer again or losing history; dated sales/cash reports agree; and staff receive the active-customer reminder before saving Time Out.
