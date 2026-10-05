# Daily Checkout Records and staff Time In/Out history

**Week of October 5, 2026 · Status: implemented locally; not deployed.** This is a presentation and read-query change. Preserve every checkout, void decision, manual shift, and labelled legacy login record.

## Goal and confirmed date rule

- Checkout Records currently groups records under headings such as **October 2026**. Group by exact **Asia/Manila checkout date** instead: **October 5, 2026**, **October 6, 2026**, and so on, newest first.
- Without a date selected, older daily groups remain reachable. Selecting one date shows **only** checkouts completed on that date, including voided records clearly marked as such. Clearing the date returns to the full history. Keep customer, payment, and status filtering.
- The admin Staff Members → Staff Time In/Out modal gets the same daily headings and a date picker. Each Time In or Time Out event belongs to its **own Manila calendar day**. An overnight shift has Time In on the first day and Time Out on the second; it must not be silently assigned to only one day.
- Preserve manual shift rows and the existing **Legacy login record** labels. Do not use a login record to invent a manual shift role or discard prior records.

## Current code and important limit

- `app/templates/checkout_records.html` groups by `record.created_date.slice(0, 7)`. It already has From/To date inputs and loads `/api/checkout-records`, then filters search/status in the browser.
- `app/dto/serializers.py::serialize_transaction` already sends `created_date` as the checkout's Manila `YYYY-MM-DD`; use this exact key for headings. Do not group by Time In, Time Out, or browser timezone.
- `app/routes/session_routes.py::checkout_records` and `app/repositories/session_repository.py::list_transactions_paginated` already filter `Transaction.created_at` with `manila_day_bounds`, but default to **only the first 50 rows** and return an array without pagination information. If only the JS heading changes, older daily groups and high-volume days will be missing. Search/status totals also currently cover only those loaded 50 rows.
- `app/templates/admin.html::loadStaffAttendanceData` renders one flat table. `app/services/admin_service.py::staff_attendance` combines `StaffShift` and visible `StaffAttendance` and sends formatted times with no ISO event date. `app/routes/admin_routes.py` exposes `/api/admin/staff-attendance` for admins.

## Checkout Records implementation

1. Keep the current date range filters available. Add a clearly labelled **Day** picker (with **Today** and **Show All**) that sets From and To to the same ISO date, or replace the two date inputs with a single day plus an optional range control. The important behavior is one selected day = one exact Manila checkout day; empty selection = all dates. Preserve URL/filter state through refresh if the page already supports it, otherwise add a small query-string state.
2. Replace month grouping with full `YYYY-MM-DD` grouping from `created_date` in the existing desktop table and mobile cards. Format the heading as a human-readable date using the ISO parts, without `new Date(iso)` browser timezone drift. Sort groups and rows newest first; use transaction ID as a stable tie-breaker.
3. Extend the existing read endpoint with an **opt-in paginated response** for the Checkout Records page, or another backward-compatible mechanism. Keep the current array response for existing callers/tests until all are updated. Send `data`, total count, current page, and next-page indicator. Put customer search and status filtering in the server query so they operate across all rows, not only the first page. Validate/bound page size, dates, status, and payment method.
4. Add Previous/Next or Load Older controls. A day with more than one page must let staff see every matching checkout without mixing in another day. When appending older rows, regroup all loaded rows so a day split across pages has one heading. Label counts and payment summary as either **all matching records** (server aggregate) or **shown records**; do not present first-page totals as the whole day's money.
5. Keep the pending void banner driven by the existing pending-requests endpoint, not just the visible checkout page. Keep approved voids visible with their status, original amount/method, and review action. Never delete or move transaction rows to produce the new grouping.

## Staff Time In/Out implementation

1. Return structured UTC timestamps or explicit Manila `YYYY-MM-DD` event dates from `AdminService.staff_attendance`; keep the displayed time strings. For each `StaffShift` or visible `StaffAttendance` record, emit a Time In event and, when present, a Time Out event, each with stable source/record ID, staff name, shift role or **Not recorded**, source label, and matching paired time for context.
2. Group event rows by their own Manila dates in the admin modal. A shift crossing midnight therefore appears once on each relevant date, with the matching action highlighted. A currently open shift has only Time In until Time Out is recorded. Do not duplicate it as two completed shifts or inflate counts.
3. Add an accessible `type="date"` picker, **Today**, and **Show All** in the modal. When selected, fetch/filter only events on that date; Show All displays all daily groups newest first. For long history, use bounded paging or Load Older instead of rendering unbounded rows. Keep the modal read-only, as previously agreed.
4. Preserve legacy visibility rules: only `staff_attendance.show_in_history=True` appears; still label legacy rows. Manual records continue to show role. Filter after calculating each event's Manila date, including for backdated manual entries.

## Verification and acceptance

- Checkout tests: two checkouts on different Manila days, one at 23:59 and one at 00:01, one customer checked in yesterday and checked out today, voided/pending records, a date with more than 50 rows, combined search/status/payment filters, and a cleared filter returning older dates.
- Staff tests: manual Time In and Time Out on different days, open shift, visible legacy login record, hidden legacy row, two shifts from one person on one day, and a Manila midnight boundary. Check that admin-only authorization remains intact.
- Manual desktop/mobile checks: the same date heading appears above the same records on both layouts; choosing October 5 lists only that day's checkouts, and selecting October 6 lists its own. The admin attendance modal shows each event under its correct day.
- No monetary rows or shift timestamps are rewritten. Confirm daily checkout amounts still agree with the existing Daily Balance ledger and that a void changes financial totals only through its established approval flow.

**Done when:** every checkout and staff event is reachable under the correct Manila day, date selection isolates that day, and older history is still available.

## Local implementation check

- Checkout Records now uses Manila checkout-day headings, a day picker with Today/Show All, server-side search/status/payment filters, and Load older pagination. The existing API array response remains available to older callers.
- Admin Staff Time In/Out now shows Time In and Time Out as separate dated events, including overnight shifts and visible legacy login records, with date filtering and Load older pagination.
- Focused boundary/filter/authorization tests and the full suite passed locally (276 tests). Manual checks on the deployed site remain to be done after deployment.
