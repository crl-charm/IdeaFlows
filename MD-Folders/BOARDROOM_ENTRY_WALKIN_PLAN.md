# Boardroom: one booking entry point and reliable one-hour walk-in

## Goals

1. Remove the green **+** check-in control from the Boardroom space Dashboard. Staff create Boardroom walk-ins and advance bookings through **Space Bookings** (`/lounge-booking`). Keep the Boardroom status/list visible.
2. Fix the reported **Walk in now (1 hour)** failure after an earlier booking for that time was canceled. A truly free slot must accept the walk-in; an actually occupied or reserved slot must remain protected.

## Current flow and likely source of the error

- The Boardroom sidebar and mobile drawer open `/dashboard?space=Boardroom`, where `app/templates/dashboard.html` shows the same floating check-in **+** used by other spaces. There is also an older `/boardroom` page (`app/templates/boardroom.html`) with another **+** and `/api/book-boardroom`. Both should be covered so a duplicate path is not left visible.
- Space Bookings posts walk-ins and reservations to `/api/book-lounge` from `app/templates/lounge_booking.html`; both use `app/services/booking_service.py` and `app/repositories/booking_repository.py`.
- The conflict query checks only `booked` and `active` bookings, so a successfully canceled `booked` row should not block a new walk-in. The exact message **“The requested space is currently occupied.”** comes from a separate active `CustomerSession` occupancy check. A lingering active session, an unsuccessful cancellation, or a different active booking must be distinguished before changing code. The booking overlap check also has a 10-minute buffer.

## Phase 1 — reproduce and identify the blocker

1. Capture a failed request's response, selected date/time/type, and server log. Inspect the affected booking's status, linked session ID/status, and any other active Boardroom sessions. Verify cancellation returned success and persisted `cancelled`.
2. Reproduce in isolated tests: cancel an upcoming reservation, then create a walk-in for the same current slot; separately test an active session, a different active booking, and the 10-minute buffer. Check the 7:00 AM–10:00 PM boundary and the server's current-time validation.
3. Trace all callers of `/api/checkin`, `/api/book-boardroom`, and `/api/book-lounge` before removing a UI path. Preserve an active customer's legitimate occupancy; never clear a session just to make the slot appear free.

## Phase 2 — simplify the entry controls

1. Hide/remove the Dashboard floating check-in button only for the Boardroom space context. Leave it for Regular/Premium and the general Dashboard. Provide a clear link from the Boardroom view to **Space Bookings** for walk-in or advance booking.
2. Remove the obsolete **+** and booking modal from `/boardroom` if that legacy page remains reachable, or redirect the legacy page to the current Space Bookings flow. Keep read-only booking information and existing valid deep links as appropriate.
3. If direct Boardroom `/api/checkin` bypasses booking rules, route that action through the booking flow or reject it with a clear message. Do not weaken the server's reservation or occupancy checks for users who call the API directly.

## Phase 3 — fix the actual walk-in bug

1. If a canceled booking is still treated as blocking, fix the shared conflict/status path once. If a linked session remains active incorrectly, fix the cancellation or completion transition that left it active and retain the audit trail. If an independent session is truly active, keep the rejection and show staff which current occupancy/reservation needs action.
2. Refresh schedule and booking state after cancellation and before retry so the UI does not use stale occupancy. Make errors specific enough to distinguish **reserved slot**, **active customer**, and **time outside opening hours**.
3. Preserve one-hour pricing, booked duration, actor, customer, and booking history. A successful retry or double click must not create duplicate bookings or customer sessions.

## Phase 4 — regression and production verification

- Add a focused canceled-booking-to-walk-in test plus tests for legitimate occupied/reserved denial, checkout releasing occupancy, and retry idempotency. Run the relevant booking tests and check desktop/mobile Boardroom navigation.
- Verify a canceled slot on the live schedule can be used for a one-hour walk-in, and that an occupied Boardroom still rejects it. Compare booking/session audit history and any financial checkout with Daily Balance by method and Asia/Manila date.
- Do not change production booking rows manually as part of rollout; collect read-only evidence first if the live issue persists after the fix.

## Done when

Boardroom has one clear creation route through Space Bookings, and a canceled reservation alone no longer prevents a current one-hour walk-in. Real active occupancy and overlapping reservations still block new bookings with an understandable reason.

**Status:** The duplicate Boardroom creation controls were removed locally. The canceled-booking walk-in issue in this broader plan has not been reproduced or resolved; it needs separate investigation before this plan can be marked complete.
