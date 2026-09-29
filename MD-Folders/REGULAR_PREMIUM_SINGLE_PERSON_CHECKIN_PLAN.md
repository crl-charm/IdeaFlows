# Regular and Premium: one person per Time In

**Status:** Plan only. Implement and verify before deployment.

## Decision and result

Every Time In on the Regular or Premium dashboard represents **one person**. Remove the Number of People field from those check-in forms. Staff enter the customer's name and existing optional details, then check in. A second person needs a second check-in. Do not alter Boardroom or Whole Hub booking party sizes, and do not rewrite older group-session records.

## Current path

- `app/templates/dashboard.html` renders `#numberOfPeople`, reads it in `checkinCustomer()`, and posts to `/api/checkin`.
- `app/routes/session_routes.py` parses `number_of_people`; `app/services/session_service.py::checkin` validates it and checks capacity.
- `app/models/customer_session.py` defaults `number_of_people` to 1. `app/repositories/session_repository.py::sum_active_occupancy` adds active session counts. `app/routes/dashboard_routes.py` fixes the selected Regular/Premium space.

## Phases

### 1. Form and request

1. Remove the Number of People input, reset code, and any now-unused label/help text from the Regular/Premium check-in modal. Keep name and other existing fields and the fixed space selection.
2. Send `number_of_people: 1` explicitly, or omit the field if the endpoint defaults to 1. Show a short note such as “One check-in per person” if useful to staff.
3. Check both desktop and narrow-screen modal layouts, keyboard focus, and error handling.

### 2. Enforce on the server

1. Resolve the requested space before applying the rule. For `Regular Lounge` and `Premium Lounge`, reject a supplied value other than integer 1 and store 1. Do not trust the hidden/browser value. Invalid strings must return HTTP 400 instead of causing a 500.
2. Preserve the existing capacity check and concurrency behavior. One successful check-in increases occupancy by exactly one; a full lounge still returns its normal conflict response.
3. Leave Boardroom/Whole Hub booking and their party-size validation intact. Reject `Take Out` as a timed lounge if the food-only feature has introduced that location; see `FOOD_ONLY_ORDERS_DASHBOARD_PLAN.md`.

### 3. Verify

- Check in one person in Regular and one in Premium; each stored row has `number_of_people = 1` and each lounge's available seats falls by one.
- Directly POST 2, 0, a fraction, or text for either lounge: reject without creating a session. Boardroom/Whole Hub party sizes still work through their existing booking paths.
- Historical sessions with more than one person still display and contribute their original count until completed.

## Done when

The form has no people-count choice, every new Regular/Premium session has one occupant even for direct API requests, and existing bookings and old records remain correct. Run the smallest relevant session/dashboard tests and inspect the final diff.
