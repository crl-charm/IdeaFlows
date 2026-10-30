# Admin Panel — daily customer visits and staff history filters

Date: October 30, 2026 (Asia/Manila).

**Status: implemented and verified locally on October 30, 2026, and included in this source release. Not deployed to the VPS.** Live backup automation testing remains a separate, deferred task.

## 1. What the client will see

The customer card defaults to **today's customer visits**, rather than every customer visit ever recorded. Clicking it opens Customer Records with:

- **Today**
- **Yesterday**
- **Month** — a month-and-year picker, for example September 2026
- **Show All** — explicitly open all retained visit history

The selected period is visible on both the card and the modal. Changing the customer period updates both the number and the list. The card label becomes **Customer visits**, with a caption such as `Today · October 30, 2026` or `October 2026 · October 1–30`.

Staff Members still opens Staff Time In/Out. That modal gets the same period choices and defaults to Today, with its existing day-grouped events and load-more navigation. Its selected period is independent of the customer filter and clearly labelled **Staff event period**.

The **Staff Members**, **Active / Online**, **Offline**, staff-role totals, and Staff Directory continue to describe the current staff accounts. A historical attendance filter does not turn those cards into historical account totals.

## 2. Confirmed counting rules

The user confirmed:

1. Carl visiting twice on one day counts as **two visits**.
2. Include **Regular, Premium, started Boardroom visits, and food-only visits**. Exclude cancelled check-ins.
3. Use the **Manila arrival date** for timed visits and the food-only record's creation date for food-only visits.
4. Apply the filters to customer records/count and Staff Time In/Out; keep current staff account counts unchanged.

Implementation meaning:

- Count one qualifying `CustomerSession` record once, not a distinct name. Do not guess whether identical names belong to the same person.
- A boardroom group has one visit record under its booking customer's name; this counter is not a count of every person in the group. Count its underlying started session once, without adding the booking again. A future reservation that has not started contributes no visit.
- Food-only creation already stores its creation time in `CustomerSession.time_in`; use that value rather than adding a new timestamp column.
- Include both active and completed valid visits in the selected arrival period. Checking out, pausing/resuming, ordering more food, or refunding a checkout does not create an extra visit or remove an actual visit.
- Cancelled check-ins stay in their existing audit history but are excluded from this visit total and its ordinary list.
- Do not include an unstarted reservation, an individual food item, or a receivable entry as an additional customer visit.
- Preserve the existing session-based scope for other supported started space visits; any additional service-mode exclusions must be made explicit before implementation.

## 3. Daily rollover and month behavior

**All dates use Asia/Manila, regardless of the phone, browser, or VPS display timezone.**

| Selection | Included visits/events |
| --- | --- |
| Today | The current Manila day through the current time. |
| Yesterday | The complete preceding Manila calendar day. |
| Past month | The whole selected month and year. |
| Current month | The first day of the month through the current date/time. |
| Show All | All retained qualifying history through the current time. |

Examples:

- At midnight on October 31, the **Today** customer total starts at zero if nobody has arrived yet that day. October 30's records remain available under Yesterday or October 2026.
- Carl arrives October 30 at 7 p.m. and checks out after midnight. His visit belongs to October 30; it is not counted as another October 31 arrival.
- Selecting October 2026 on October 10 includes October 1–10 so far, without waiting for the month to finish. Selecting September 2026 includes September 1–30.

This is a date-filtered view, not a daily database reset. No midnight deletion, counter-reset job, or historical data rewrite is needed.

Refresh the relative Today/Yesterday periods when the page remains open across Manila midnight, when it becomes visible again, and on normal reload. If a page was suspended, refresh immediately on return. Reuse a small bounded HTTP refresh for the displayed count/open modal; Socket.IO is not a requirement for loading or rollover. Server-returned dates/time boundaries must guide rollover so an incorrect device timezone does not select the wrong day.

An explicitly selected month remains that month across midnight or a new month. If it is still the current month, its month-to-date range grows as time passes. The default on a fresh Admin Panel visit is Today.

## 4. Verified current behavior and files

| File | Current responsibility / planned work |
| --- | --- |
| `app/repositories/admin_repository.py` | `count_customer_sessions()` currently counts all session rows; `list_customer_sessions()` loads all history and its orders. Add shared qualifying-session/date predicates, database counts, stable ordering, and bounded records pagination. Filter relevant staff rows by time ranges before constructing events. |
| `app/services/admin_service.py` | `customer_count()` and `customer_records()` currently receive no period. Apply the same normalized period to the count/list and return clear date/total metadata. Extend `staff_attendance_events()` from an optional single date to normalized period bounds while preserving each event's own date and paired-time display. |
| `app/routes/admin_routes.py` | Customer count/records routes currently accept no date filter; staff attendance accepts a single date with `events=1`. Add strict period/month validation and bounded pagination while retaining admin-only authorization and existing response compatibility where required. |
| `app/templates/admin.html` | Customer count and modal currently fetch every record without a period. Add the customer period controls/caption, customer load-more navigation, staff Yesterday/month controls, clear empty/error states, and responsive layout. Reuse the existing `fetchJSON` and staff request-version guard patterns. |
| `app/utils/dates.py` | Reuse `manila_date`, `manila_day_bounds`, and `month_bounds`. Add only a small shared period-normalization helper if both routes need it; do not duplicate month/date parsing. |
| Existing and focused tests | Extend date-boundary, customer query-efficiency, attendance-event, authorization, and frontend request checks; add focused period tests where needed. |

Confirmed source locations at planning time:

- `app/repositories/admin_repository.py:74` — unfiltered customer record query.
- `app/repositories/admin_repository.py:86` — all-time `CustomerSession.query.count()`.
- `app/services/admin_service.py:124` — customer record serialization.
- `app/services/admin_service.py:147` — customer count passthrough.
- `app/services/admin_service.py:208` — existing staff event filtering.
- `app/routes/admin_routes.py:178` — customer records endpoint.
- `app/routes/admin_routes.py:185` — customer count endpoint.
- `app/routes/admin_routes.py:192` — staff attendance endpoint.
- `app/templates/admin.html:401` — customer card.
- `app/templates/admin.html:638` — existing staff date controls.
- `app/templates/admin.html:956` — customer card loading.
- `app/templates/admin.html:969` — customer modal loading.
- `app/templates/admin.html:1004` — staff event loading and stale-response guard.

These are planning references; verify line positions again when editing.

## 5. Smallest implementation approach

1. Normalize the requested period on the server into naive UTC start/end bounds. Use a half-open interval (`timestamp >= start`, `timestamp < end`) and clamp current periods to the current server time. Reject malformed months, conflicting filter inputs, invalid pagination, and future months.
2. Use the exact same customer status/date predicates for the scalar count and paginated list. Return the selected period, effective dates, server as-of time, total, and pagination metadata so labels and numbers agree.
3. Query by `CustomerSession.time_in` using the existing `idx_customer_sessions_time_in` index. Do not wrap every timestamp in a date function or fetch all historical records to count them. No new database column or migration is currently expected.
4. Keep eager loading for the displayed page's orders and spaces. Order customer records by time-in descending, then ID descending, with a bounded page size such as 50 and a maximum of 100.
5. For staff, include a Time In or Time Out only when that specific event falls inside the selected Manila period. An overnight shift can appear on both dates. The paired time may fall outside the filter and remains visible for context. Preserve Manual shift / Legacy login record labels and hidden-log exclusions.
6. Retain the existing staff events API's single-date mode for existing callers where needed. The updated UI uses the new period mode; do not silently change an unrelated caller's response shape.
7. Use standard Today/Yesterday buttons and a native month picker with a plain month/year fallback for browsers without month-input support. Keep controls and rows readable on phones without adding sideways page scrolling.
8. Reset pagination when the period changes. Cancel/ignore older requests so an October response cannot overwrite a newer September selection. Refresh the customer card and its open list from the same selected period, without duplicating modal instances or event listeners.
9. Treat 401 as an expired session and 403 as unavailable admin access. A failed request shows a clear error/retry state, not zero customers or an empty-history claim. A successful empty period shows `0` and `No visits in this period`.

The server remains authoritative. No cron job, new dependency, new permanent counter, name-merging system, or attendance/payroll redesign is needed.

## 6. Verification before delivery

- Today, Yesterday, September, current October month-to-date, and Show All return matching card totals and full paginated record sets.
- Two sessions named Carl count twice. A started boardroom session counts once, not once per booking plus session or once per attendee.
- Cancelled check-ins are excluded; active/completed sessions and food-only sessions use the correct date. Future unstarted bookings do not inflate customer visits.
- Manila midnight, UTC/Manila date differences, end-of-month/year, leap February, late check-in times, and an overnight customer visit stay in the correct period without duplication.
- Current-month results do not depend on the month being complete. Invalid/future month inputs return a clear 400 response.
- Staff events retain each event's date, overnight paired context, source labels, hidden-history exclusions, stable pagination, and current staff-card totals.
- A tab open through midnight updates Today; a suspended tab refreshes on return. A fixed month remains selected. HTTP loading still works when real-time connections fail.
- Rapid filter changes, pagination, network errors, and expired sessions do not leave the UI showing the wrong period or reporting failed requests as zero.
- Admin-only endpoints remain protected. Verify the existing customer count query stays a scalar database query with bounded eager-loading queries for each records page.
- Check the customer/staff modals at phone, tablet, and desktop widths, including the month-picker fallback.
- Confirm all visit, checkout, debt, cash, and staff history is preserved. This feature changes presentation and queries, not billing or stored records.

## 7. Delivery order

1. Implement and verify locally — completed.
2. Review the count/list and mobile behavior with the confirmed visit rules.
3. Push only the requested release files when authorized.
4. Deploy to the VPS through the normal backup and verification process when authorized.

Publishing this source to GitHub does not deploy it to the VPS or activate the separate backup timer.

## 8. Implementation and verification evidence

- Added shared `history_period()` normalization in `app/utils/dates.py`, using Manila calendar boundaries and naive UTC database predicates. Current periods end at the server's current time; future months and conflicting inputs return 400.
- Customer count and paginated record queries share the same non-cancelled session/date predicates. The count remains one scalar SQL query, and record pages keep bounded eager-loading queries. No new columns, dependencies, or migration were needed.
- `/api/admin/customer-count` preserves `count` and adds filter metadata. `/api/admin/customer-records` now returns the paginated `{data, total, page, per_page, has_next, filter}` envelope consumed by the updated Admin Panel. No other repository caller of its previous array response was found.
- Staff period requests use `events=1` plus `period`/`month`. The old raw attendance response and `events=1&date=...` behavior remain compatible. Staff source rows are filtered by matching Time In or Time Out before constructing each in-range event; paired times and former staff history are retained.
- The customer card and its modal share selection and totals. Staff history has an independent selection. Month controls are shared markup in `partials/admin_history_controls.html`, with a native month input and a YYYY-MM fallback.
- Browser requests use `fetchJSON`, AbortController, request-version guards, and no-store reads. Relative rollover uses a duration supplied by the server; bounded HTTP polling and visibility refresh work with real-time connections disabled. Mobile history rows stack vertically rather than scrolling sideways.
- **36 automated checks passed:** 19 new admin-period tests plus 17 existing staff shift, query-efficiency, staff recovery, and frontend request-management checks. Tests use isolated in-memory data.
- Headless Chrome checks passed at **320, 375, 768, and 1366 pixels**, with no JavaScript page errors. These covered matching card/list totals, load-more pagination, rapid filter changes, failed requests/retry, independent staff filters, unchanged staff account counts, escaped customer names, and a single modal/backdrop after repeated opens.
- Additional browser checks covered Manila midnight in a Los Angeles browser timezone, refresh on visibility return, preserving an explicitly selected September, the simulated unsupported-month-input fallback, clear 403 access errors, and redirecting an expired 401 session to login. This is browser simulation evidence, not a test on a physical iPad.
- Local screenshots: `instance/admin-history-customer-375.png` and `instance/admin-history-staff-375.png`. Isolated browser fixture/harness and JUnit results are kept under ignored `instance/`; they contain synthetic records only.
- No production command or real backup was run. Existing uncommitted backup automation work, local notes, and unrelated workspace changes were preserved.
