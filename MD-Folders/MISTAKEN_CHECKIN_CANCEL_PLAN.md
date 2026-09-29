# Cancel an unused mistaken Time In

**Status:** Plan only. This is the delete icon beside Add Order and View Order.

## Confirmed rule

Staff may cancel a wrong Regular/Premium Time In (for example, a customer was entered in Regular instead of Premium) **only if the session has never had a placed order, payment, or checkout**. The action removes it from the active dashboard and frees its seat. It must remain in audit history; do not hard-delete the database row. Boardroom/Whole Hub linked bookings cannot be silently cancelled by this shortcut.

## Existing path

`app/templates/dashboard.html` renders Add Order and View Order in desktop and mobile cards. `app/routes/session_routes.py` owns `/api/checkin` and `/api/active-sessions`; `app/services/session_service.py` and `app/repositories/session_repository.py` own session state/occupancy. `CustomerSession.status` is currently `active` or `completed`. `Order`, `Transaction`, and booking/payment relationships must be checked before cancellation.

## Phases

### 1. Data and endpoint

1. Add `cancelled` session status and minimal audit fields or a small immutable cancellation record: actor user ID, UTC cancellation time, reason, original space, and time-in. Use the repo's idempotent schema migration pattern. Record the estimated unbilled time waived at cancellation if applicable, labeled **uncollected**, never as a received/refunded payment.
2. Add an authenticated cancellation endpoint, e.g. `POST /api/sessions/<id>/cancel`, with a required short reason, CSRF, and request-key handling. The server must lock/re-read the session and reject a second or stale request safely.
3. Allow only an active **timed** Regular/Premium session with **no Order row at all** (even if later item-voided), no `Transaction`/checkout, no receivable or other payment attached to it, and no linked active or historical Boardroom/Whole Hub booking. The UI's disabled state is only a hint; the server makes the decision.
4. In one transaction, mark `cancelled` and write the audit. All active-list, occupancy, current-bill, Still to Collect, and order-add queries must ignore cancelled sessions. `preview_checkout` and `checkout` must require `status == "active"` so a cancelled session cannot be billed through a direct API call. Keep old order/checkout history intact. Do not modify menu inventory or Daily Balance because an eligible session has no placed order or collected money.

### 2. UI

1. Place an accessible trash/delete icon beside Add Order and View Order on Regular/Premium desktop and mobile cards. Give it a text/ARIA label such as “Cancel mistaken Time In.”
2. Confirmation modal shows customer, current lounge, and a reason field; state clearly that an unused entry will be cancelled. On success remove/refetch the card and refresh seat counts. On conflict show why cancellation is blocked and keep the card. Disable repeat clicks while saving.
3. Keep this icon away from Checkout Records; that screen uses the separate admin-approved void flow in `CHECKOUT_VOID_APPROVAL_PLAN.md`. An empty food-only record may use the same server rule after the Food Orders feature exists, with a matching action on that page.

### 3. Verification

- Create a mistaken one-person Time In, cancel it, then check in to the correct lounge. The first is absent from active sessions, its old lounge has one more seat, and its audit is reviewable.
- Try cancel after placing an order, after payment/checkout, or with a linked booking: reject and leave all counts, stock, and money unchanged. Direct API calls have the same restrictions.
- Retry the same request and test a race between Add Order and cancellation; at most one operation succeeds, with no orphan order or stock reservation. Verify desktop/mobile controls and keyboard use.

## Done when

An unused mistaken Time In can be safely cancelled without deleting evidence or disturbing a used session. Run focused session/order tests and inspect the diff.
