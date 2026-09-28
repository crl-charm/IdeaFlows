# Manual staff Time In and Time Out

## Goal and confirmed rules

- A staff member signs in to the app, then records work time with a **Time In/Out** control to the left of Orders in the top navigation. The control is available on mobile too.
- The staff member's name comes from the signed-in account. They select the role performed on that shift (General Staff, Cashier, Cook, or Server). This role is a historical snapshot and **does not change account permissions**.
- Staff enter the local **date and time** of Time In manually. Time Out stays blank until the same staff member enters its local date and time and saves it later. An overnight shift is valid when Time Out is on the next date.
- Logging out, losing a session, or signing in again does not close an open work shift. A later signed-in session for that same staff account can record Time Out.
- The admin Staff Members tile opens a read-only history with name, shift role, Time In, Time Out, and a source label. Older login-based entries remain visible as **Legacy login record**; new login-presence rows are not presented as work shifts.

## Phase 1 — Separate presence from shifts

1. Keep the existing `staff_attendance` records for online/login presence so current login security and status continue to work.
2. Add a `staff_shifts` table for manual work shifts with staff ID, shift role, entered Time In/Out, and server recording timestamps. Store entered dates as UTC and display them in Asia/Manila time.
3. Mark new login-presence rows as hidden from the admin work history. Existing login-based rows remain labeled legacy. Deploy this column and table through the existing database migration path without deleting history.

## Phase 2 — Staff API and validation

1. Read the current staff account and its open shift from the authenticated session, never from a client-supplied staff ID or name.
2. Time In accepts a valid shift role and Manila date/time, creates one open shift, and rejects another Time In while that staff account has an open shift.
3. Time Out accepts a Manila date/time for the open shift, rejects a time before Time In or a future time, and saves the closing timestamp. Keep the server time when each action was recorded so backdated entries remain auditable.
4. Use CSRF protection and request keys for writes. Lock the staff row during writes to prevent two concurrent Time In requests from opening duplicate shifts.

## Phase 3 — Staff interface

1. Place a Time In/Out button before Orders in the desktop header and an accessible entry in the mobile header.
2. Open a modal showing the account name, shift role, Time In date/time, and Time Out date/time. For a new shift, only role and Time In are editable; Time Out is blank. For an open shift, show the saved role and Time In and enable Time Out.
3. Save with clear validation and status feedback. Refresh the modal state after saving. Do not silently fill manually entered dates or times.

## Phase 4 — Admin history

1. Update the Staff Members modal columns to Name, Shift Role, Time In, Time Out, and Source.
2. Show manual shifts newest first and include labeled pre-upgrade login-based rows. Leave this modal view-only.
3. Escape staff names and displayed values in the browser.

## Phase 5 — Verification and rollout

- Test staff-only access, role snapshot, manual Manila time conversion, overnight shifts, invalid/future time, duplicate Time In, logout and later Time Out, admin visibility, and legacy labels.
- Run the focused tests, then the full suite because the shared layout and admin attendance list are touched. Review the diff for regressions.
- Before production use, run the normal migration and verify `staff_shifts` and the new login-history flag exist; restart and check the manual flow in a staff account and read-only history in an admin account.

**Status:** Implemented locally. Focused checks and the full suite pass (221 tests). The local SQLite migration was applied and verified on September 29, 2026. Production migration and rollout remain pending.
