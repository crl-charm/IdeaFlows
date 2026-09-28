# Regular and Premium spaces: automatic check-in selection

## Goal

When staff open **Regular** from the Spaces navigation and start a customer check-in, the form already uses Regular Lounge. From **Premium**, it uses Premium Lounge. Staff should see the selected space as clear text and should not have to choose it again. The general Dashboard keeps a space selector because it has no space context.

## Current flow

- The sidebar and mobile drawer link to `/dashboard?space=Regular%20Lounge` and `/dashboard?space=Premium%20Lounge`; Boardroom uses the same Dashboard with `space=Boardroom`.
- `app/routes/dashboard_routes.py` renders one `app/templates/dashboard.html` with the available `SpaceType` rows.
- Dashboard JavaScript reads the `space` query into `currentFilter` for the session list, but the New Customer Check-in modal's `#spaceType` selector stays on its first option. `checkinCustomer()` posts that selected ID to `/api/checkin`.

## Phase 1 — check existing behavior

1. Verify sidebar and mobile navigation, direct Dashboard entry, and the New Customer Check-in modal on each page. Confirm the `SpaceType` names/IDs from the database rather than assuming option order.
2. Trace `/api/checkin` validation and capacity/booking checks in `app/routes/session_routes.py` and `app/services/session_service.py`. These server checks remain authoritative.

## Phase 2 — small UI change

1. On modal open, resolve the URL's known Regular/Premium space name against the rendered options and select its existing ID. For those two contexts, display a fixed, readable space label instead of an editable dropdown; still submit the resolved ID.
2. On `/dashboard` with no recognized space context, keep the selector editable. An invalid or outdated query value must fall back safely to the general selector, not silently check the customer into the first space.
3. Keep the selection correct after modal close/reopen and after a successful check-in. Do not change the price, capacity, customer fields, or the shared server-side validation.

## Phase 3 — verification

- Add a focused page/UI check: Regular submits the Regular ID, Premium submits Premium, general Dashboard permits a chosen space, and an unknown query does not submit a surprise default.
- Check desktop and mobile modal labels, keyboard access, and that the selected space is visible before staff press **Check In**.
- Confirm both pages still filter active sessions correctly and that the server refuses invalid IDs or a full/reserved space.

## Done when

Staff can open Regular or Premium, press the check-in button, fill customer details, and submit without choosing the space; the resulting session is in the space shown on the page.

**Status:** Implemented locally and covered by the space-page test. Production deployment remains pending.
