# Late Customer Check-in

**Updated:** October 27, 2026  
**Status:** Implemented and verified locally and included in this source release. VPS deployment has not been performed.

## Goal and confirmed scope

When a customer is already using a space and staff forgot to check them in, staff or admin can create the visit using the customer's actual arrival time. Billing includes that earlier time.

- Support **Regular Lounge and Premium Lounge only**.
- Allow an arrival time **earlier today in Asia/Manila**, up to the current server time. Previous dates and future times are rejected.
- Put **Late Customer Check-in** inside the customer form opened by the existing **+** button. There is no separate Dashboard header button. Make it available on the Regular and Premium space views too.
- Keep normal check-in simple: the existing **+** button uses the current server time automatically, with no time picker to fill in.
- Use the same native date/time picker style as **Staff Time In**, clearly labeled as the customer's arrival time.

## Staff and admin flow

### Normal arrival

1. Tap the existing **+** button.
2. Enter the customer details and select the space, as today.
3. Tap **Check In**. Billing starts when the server records the visit.

### Customer was already there

1. Tap the existing **+** button to open New Customer Check-in.
2. Tap **Late Customer Check-in** inside that form. It switches to late mode while keeping the entered customer, school, course, and space details. **Use current time instead** switches it back to normal check-in.
3. An additional required field appears: **Actual arrival time (Manila time)**. Use the native `datetime-local` input already used by Staff Time In; explain **Today only. Choose when the customer arrived.**
4. Staff select the actual time. Do not silently fill it with the current time in late mode. The date must remain today; earlier and future dates are unavailable and also rejected by the server.
5. Show the selected arrival time clearly beside the save action, then tap **Check In Customer**. Keep the same modal open with the entered details if validation or saving fails.
6. The customer appears in the active list with the selected Time In and the correct running time bill. The current customer page receives the same arrival time and bill.

**Example:** Carl arrived in Premium at 9:00 a.m. Staff notice at 10:20 a.m. and choose 9:00 a.m. His billable time immediately includes 1 hour and 20 minutes. With the current Premium pricing, the time bill is **PHP 30**, before food and checkout adjustments.

Closing or reopening the modal through the normal **+** button must reset late mode and clear its time field. A previous late entry must never change the next normal check-in.

## Billing and history

- Save the chosen arrival as `CustomerSession.time_in`, converted from Manila time to the application's existing UTC storage format.
- Keep all existing rates and started billing blocks. The earlier arrival feeds the shared billing calculation; no separate late-entry price formula or fee is needed.
- Pause/resume, food orders, checkout preview, receipt, Checkout Records, Daily Balance's active estimate, and the public running bill must agree on that start time.
- Check-in itself creates no sale or cash movement. Paid checkout remains recognized on its checkout/payment business date.
- Reuse `SessionTimeEvent` for an append-only **Late check-in recorded** event. Its `occurred_at` is the actual server recording time, while the customer's Time In is the selected arrival time. Store the authenticated actor ID, name, and role and the existing billable-time/amount snapshots.
- Save the new session and its audit event in **one database transaction**. A failed audit save must not leave an unaudited late check-in.
- Make **Time history** available for a late visit even if it has never been paused, on desktop and mobile and after checkout. Show, for example: **Arrived 9:00 a.m.; recorded 10:20 a.m. by Diana (Staff)**. Keep this staff/admin audit information out of the public customer response.
- Reuse the existing tables. No additional table, column, or historical backfill is expected for this design. Existing visits and financial history remain unchanged.

## Server validation and safeguards

1. Extend the existing `POST /api/checkin` flow rather than creating a second billing/check-in implementation. Requests without late-entry fields retain the current automatic-time behavior.
2. Distinguish normal and late submissions explicitly. Late mode requires an arrival value; malformed modes/timestamps or a timestamp smuggled into normal mode return a clear `400`, rather than silently falling back to now.
3. Authorize late entries for signed-in **staff and admin**. Read the actor from the authenticated session; never trust a client-supplied actor identity. Anonymous requests receive `401`, and other roles cannot submit a late entry.
4. Parse minute-precision Manila date/time strictly on the server using the service clock and existing Manila offset helpers. Do not convert the value through the phone's timezone. The server determines today and rejects a previous date or future instant.
5. Handle midnight explicitly: if a form was opened before midnight and submitted afterward with yesterday's arrival, return **Late check-in must be for today in Manila time.** Ask the user to review the form; do not silently change the date.
6. Validate the selected space server-side. A forged late submission for Boardroom, Whole Hub, or food-only is rejected.
7. Retain one person per Regular/Premium check-in and the current capacity lock/check at recording time. Keep current reservation guards based on actual server time; changing the billing start must not bypass them. Also reject a known Whole Hub reservation overlapping the claimed arrival-to-recording interval, without treating an ordinary Boardroom reservation as a lounge conflict. Do not claim historical seat occupancy has been reconstructed.
8. Preserve existing CSRF protection, `Idempotency-Key`, and disabled-while-saving button behavior. Replaying the same keyed request must not create another visit or audit row.
9. Keep approved checkout correction/retained-credit handling separate: late mode is for an ordinary new visit and must reject a combined `void_request_id`. The existing normal correction flow stays available.
10. Commit before sending change notifications. A failed real-time notification must not turn a successfully saved late check-in into a failed response that encourages duplicate entry. Refresh through the existing HTTP loading paths when real-time updates are unavailable.

## Existing code and intended changes

These locations were inspected before implementation. The line numbers below refer to that original source and have moved during implementation.

| File | Current behavior | Planned change |
| --- | --- | --- |
| `app/templates/dashboard.html:9` | Header contains Cancelled Time Ins and customer search. | Keep the header's existing actions; place the late-entry option inside the + check-in modal. Hide it on Boardroom and food-only views. |
| `app/templates/dashboard.html:202` | The shared customer check-in modal has no arrival picker. | Reuse the modal with explicit normal/late modes; show the required picker only in late mode. Preserve the preselected Regular/Premium space. |
| `app/templates/dashboard.html:463` | `checkinCustomer()` sends details to `/api/checkin`. | Submit the late mode and arrival only when selected; preserve form data on failure and clear mode/date on normal reopen. |
| `app/templates/layout.html:590` | Staff Time In uses a native `datetime-local` input. | Use as the visual/input reference; the staff shift workflow itself needs no change. |
| `app/routes/dashboard_routes.py:7` | Renders Dashboard and selected-space context. | Supply server-derived Manila time/date context for picker limits. Server validation remains authoritative if the page is stale. |
| `app/routes/session_routes.py:51` | `/api/checkin` forwards customer details but no arrival or actor. | Validate/forward mode, arrival, and the authenticated late-entry actor; keep existing normal requests compatible. |
| `app/services/session_service.py:53` | `checkin()` always sets `time_in=now` at line 91. | Parse and authorize the late arrival, preserve live capacity checks, and record the session plus history atomically. |
| `app/repositories/session_repository.py:114` | Reservation guard checks a single instant; `add_session()` at line 130 commits immediately. | Add the necessary late-interval reservation check and allow the audit row to be saved in the same transaction as the session. |
| `app/models/session_time_event.py:6` | Existing event fields already hold actual action time, actor, and billing snapshots. | Reuse for the late-entry audit action; no schema change expected. |
| `app/services/session_service.py:273` | `_record_time_event()` and `time_history()` already serve pause history. | Reuse these helpers and show arrival versus recorded time clearly for the new event. |
| `app/templates/dashboard.html:908` | Desktop/mobile Time history buttons depend on `has_time_pause`. | Allow history for late check-ins without falsely marking them paused; include cancelled late visits in reachable history. |
| `app/dto/serializers.py:182` and `app/templates/checkout_records.html:296` | Checkout history controls also depend on pause state. | Make late check-in history reachable after checkout. Fetch any event-presence flags in batches rather than adding one query per record. |
| `app/utils/billing.py` | Shared billing already starts at `time_in` and subtracts pauses. | Preserve the calculation; verify the earlier start flows through all bill views. |

## Implementation order

1. Add the validated late-entry path and atomic history save behind the existing check-in route.
2. Add the late-entry toggle inside the shared modal opened by +, using existing Bootstrap controls and request helpers. Do not add a picker library or extra required reason field.
3. Expose the late-entry history in the existing active, cancelled, and checkout views. Preserve the public API's explicit safe field selection.
4. Run focused local checks, then the relevant billing, check-in, pause, checkout, public customer, and authorization regressions. Review the final diff before any push or production rollout.

## Verification and acceptance

- **Normal flow:** the + button requires no arrival selection and uses the current server time, including after cancelling or completing a late entry.
- **Late flow:** staff and admin can enter both Regular and Premium arrivals earlier today, with correct UTC storage and displayed Manila time.
- **Pricing:** use a fixed clock to check the example above and the 59/60/61-minute billing boundaries. Verify a later pause, food order, discount, checkout, receipt, and Daily Balance all use the same billable duration and charged amount.
- **Invalid inputs:** reject missing/malformed arrival, unknown mode, previous day, future time, another device timezone, unsupported space/role, and a combined checkout-correction request. Rejections create no session or history row.
- **Midnight:** test Manila midnight rather than UTC midnight, including a form left open across the day boundary and a server date differing from the device date.
- **Capacity/reservations:** full lounge and Whole Hub conflict still reject late entries; a Boardroom-only reservation does not block Regular/Premium. Concurrent last-seat submissions cannot overfill the space.
- **Audit/retry:** verify actor cannot be spoofed, recorded time differs correctly from arrival, session/event roll back together, and repeated keyed submission creates only one of each. A post-commit notification failure still returns successful creation.
- **Visibility:** both dashboard layouts and the public page show the correct arrival/bill; private actor/history details remain private. Time history stays reachable after checkout or cancellation.
- **Mobile:** check the native picker and stacked header at phone/tablet widths, keyboard focus, clear validation, and no new side scroll. Physical-device behavior is not claimed until tested on that device.

## Local implementation and verification — October 27, 2026

- Added the late-entry option and native arrival picker inside the shared check-in modal opened by **+**. The option is absent from the Dashboard header. Each **+** open starts in normal mode; switching modes keeps customer details and clears the manual arrival. Failed saves keep the entered details.
- Added strict same-Manila-day validation, staff/admin actor attribution, current capacity and reservation guards, and historical Whole Hub overlap checks. Late entries cannot be combined with voided checkout corrections or food-only orders.
- The session and `late_checkin` history event save atomically. A failed audit rolls back both; a failed public socket notification does not undo a saved check-in. Existing CSRF and keyed request protection remain in use.
- Added `has_time_history` as a computed SQL `EXISTS` expression against the indexed event table, rather than a stored column or a separate query per row. Dashboard, cancelled visits, and Checkout Records can all open late-entry history. **No schema migration is required for this feature.**
- History displays the persisted arrival directly, keeping it accurate when MySQL stores the audit recording timestamp without fractional seconds. Public customer responses do not include audit or actor fields.
- Full regression run: **357 passed**, no failures, errors, or skips. After the timestamp precision correction, the final focused late-entry/pause/cancellation run passed **42 checks**, including all **33 late-entry cases**. Tests use isolated SQLite; the precision case explicitly simulates a rounded-down audit timestamp. This is not a live MySQL concurrency test.
- Headless Chrome checks passed for staff and admin, correct Manila bounds with device timezones set to Los Angeles and Honolulu, future-time validation, failed-save recovery, ordinary check-in reset, public bill updates, and private history. Modal widths **320, 375, and 768 pixels** had no horizontal overflow. Desktop and mobile screenshots were visually inspected; no page JavaScript errors were reported.
- After moving the option inside **+** at the client's request, **7 focused page/request checks** and the desktop/mobile browser flow passed again. Switching between late arrival and current time preserves customer/space details, clears the manual arrival, and does not add a Dashboard header action.
- Import validation, changed Python syntax, and Git whitespace checks passed. The disposable browser server used fake records in memory and was stopped afterward. The existing localhost server and its records were left alone.
- **To try it:** restart the existing localhost server if needed, refresh Dashboard, tap **+**, and choose **Late Customer Check-in** inside the form. A physical iPad/Android check and production MySQL verification remain rollout checks. No VPS action or GitHub push was performed.

**Acceptance:** an omitted customer check-in can be entered later the same Manila day, billing starts from the selected actual arrival, the owner can see who recorded it and when, and the ordinary check-in remains just as simple as before.
