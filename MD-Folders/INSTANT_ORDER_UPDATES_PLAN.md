# Plan: Instant Orders Badge and Queue Updates

Date: **8 October 2026**  
Status: **Planning complete; implementation pending.**

## 1. Goal and confirmed answers

When staff successfully place an order, the Orders navigation badge and an open Orders page should reflect it automatically across all logged-in staff devices. Staff should see the waiting order without refreshing the browser or waiting for a polling timer.

The owner answered these questions before this plan was written:

| Question | Confirmed answer |
| --- | --- |
| Which number should update instantly? | Both the navigation/sidebar badge and the Orders page count. |
| Which devices should receive the change? | All logged-in staff devices. |
| Should the counting rule change? | No. Keep the current counting rule. |

The existing preparation flow remains the requirement: place an order, mark items ready as they are prepared, then use **Served to customer**. Existing buttons, validation, completion rules, and navigation remain part of that flow.

## 2. What the current count means

The badge displays `pending_sessions`: the number of distinct **active customer sessions with at least one order whose status is not `done`**. The Orders list uses the same active-session/unfinished-order grouping.

Source: [app/repositories/order_repository.py:97](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/app/repositories/order_repository.py:97) and [app/services/order_service.py:251](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/app/services/order_service.py:251).

Examples to preserve:

| Situation | Expected badge and Orders session count |
| --- | --- |
| No active customer has unfinished orders | Badge hidden; Orders page has 0 sessions. |
| First customer places an order | 1 |
| Same customer adds another order or more items | Still 1; that customer's item details update. |
| A second active customer places an order | 2 |
| All first customer's items are marked Ready, but not yet Served | Still 2 |
| First customer's orders are marked Served | 1 |
| Remaining customer's orders are marked Served | Badge hidden; Orders page has 0 sessions. |
| A served customer places a new order while their session is still active | That session returns to the waiting count. |

`pending_items` is also returned by the count API, but the existing badge uses `pending_sessions`. Preserve that choice. Item readiness (`OrderItem.status`) and whole-order completion (`Order.status`) have different roles in the existing flow.

## 3. Findings from the current code

### A. The server already broadcasts order changes

After an order and its stock changes are committed, order creation emits `order_status_changed`. The same event is used after order status changes, marking a session served, cancelling an item, and toggling an item's readiness.

- [app/services/order_service.py:146](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/app/services/order_service.py:146): commit precedes the order-change notification.
- [app/services/order_service.py:154](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/app/services/order_service.py:154): notification after creation.
- [app/services/order_service.py:301](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/app/services/order_service.py:301): notification after serving.
- [app/services/order_service.py:373](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/app/services/order_service.py:373): notification after item readiness changes.
- [app/core/notifiers.py:19](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/app/core/notifiers.py:19): broadcasts to the existing authenticated room, covering authorized staff and admins.

Checkout also broadcasts `session_checked_out` after committing. A checkout changes whether a session belongs in the pending count: [app/services/session_service.py:546](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/app/services/session_service.py:546).

### B. The navigation badge currently relies on polling

`updateOrdersBadge()` fetches `/api/orders/pending-count` and updates both desktop and mobile badges. Its automatic refresh is currently attached to a **15-second smart poller**, with no order-change socket listener.

Source: [app/templates/layout.html:1248](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/app/templates/layout.html:1248), polling at line 1275.

This creates a confirmed delay path in the current code. The report that a manual refresh is needed may also involve a failed background request or disconnected browser; the live browser/network behavior has not been inspected in this planning task.

### C. The Orders list and details do not subscribe to order events

The Orders list loads immediately and then every **5 seconds**. The customer order-details screen loads initially and after its own local actions. Neither currently listens for an order placed or changed on another staff device.

Sources: [app/templates/orders_list.html:45](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/app/templates/orders_list.html:45) and [app/templates/orders_view.html:58](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/app/templates/orders_view.html:58).

### D. Placing an order only refreshes the local order panel

Successful submission clears the cart and runs `loadCurrentOrders()`. It does not explicitly refresh the navigation badge.

Source: [app/templates/order.html:1193](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/app/templates/order.html:1193), success handling at lines 1204–1208.

### E. Shared live-update helpers already exist

The layout provides a single Socket.IO connection per browser page through `getIdeaFlowSocket()`, plus `createDebouncedRefresh()` and `createSmartPoller()`.

Source: [app/templates/layout.html:990](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/app/templates/layout.html:990).

**Recommended approach:** connect the existing badge and order-loading functions to the existing events. The current server APIs remain the authority for counts, order details, and preparation state.

## 4. Implementation steps

### Step 1 — Refresh the shared navigation badge on live events

In `app/templates/layout.html`:

1. Obtain the existing connection with `getIdeaFlowSocket()`.
2. Use the existing short debounce helper to call `updateOrdersBadge()` after `order_status_changed`.
3. Refresh after `session_checked_out`, because a closed session no longer contributes to the pending count.
4. Refresh on the Socket.IO `connect` event, including reconnects, to catch changes missed while disconnected.
5. Keep the existing initial refresh, visibility recovery, and polling fallback.
6. Continue updating both `orders-badge` and `orders-badge-mobile` from the server's `pending_sessions` value.

Event handlers should be registered once for the page. Reconnection should trigger a refresh without registering duplicate listeners.

### Step 2 — Refresh the Orders list and its count on live events

In `app/templates/orders_list.html`:

1. Subscribe through the same shared socket to order changes, checkout changes, and connection recovery.
2. Refresh through `loadOrdersList()` so the rows and `orders-count` come from the same API response.
3. Preserve the existing customer-session grouping, item quantities, food totals, action links, and status meanings.
4. Return the fetch promise from the loader so refresh scheduling can track completion.
5. Use the existing smart-polling helper for the fallback at the current five-second cadence, replacing the raw interval.

### Step 3 — Keep an open customer's order details current

In `app/templates/orders_view.html`:

1. Refresh `loadOrders()` when a relevant order change arrives, including another staff member placing more food for that customer.
2. Refresh on connection recovery.
3. Preserve Mark ready, Undo, the all-items-ready requirement, Served to customer, and its existing redirect.
4. Keep current local success refreshes after staff actions.

Some existing item-readiness events contain `order_id` and `item_id` but **no `session_id`**. A session filter must not discard those events. The simplest compatible behavior is to refresh the open details view when the event has no session ID, and skip only events explicitly identifying a different session. Verify the existing response behavior if the customer checks out while their details are open.

### Step 4 — Refresh the placing device after confirmed success

In `app/templates/order.html`, call the existing shared badge refresh after a successful order response, alongside the existing cart reset and local order-list refresh.

This allows the placing device to update promptly even if its socket is reconnecting. Other devices use the server broadcast. Both paths fetch the current server count, so receiving both a successful response and an event must not add two to the badge.

For an existing “already processing/completed” response, refresh the authoritative count along with current orders. Never add a badge number merely because a request was attempted or rejected.

### Step 5 — Keep asynchronous refreshes accurate

Apply small guards where the added event refresh can overlap with an initial load, local success refresh, or fallback poll:

- Use a request sequence or equivalent simple guard so an older response cannot overwrite a newer result.
- Debounce event bursts with the existing helper. If an in-flight request causes refreshes to be coalesced, retain a follow-up refresh when a newer change arrives; do not discard that change.
- Treat failed responses as failures and preserve the last known value. A failed request must not fabricate an empty queue.
- Render badge counts as text and retain the existing zero-count hiding behavior.
- Keep controls usable during background refreshes; verify that a refresh does not restore a disabled submit/serve control while its action is still pending.

These changes are limited to displaying committed order state. The planned code should preserve existing authorization, order/stock writes, payment behavior, and financial history.

## 5. Expected files to change during implementation

| File | Intended change |
| --- | --- |
| `app/templates/layout.html` | Shared desktop/mobile badge listeners, reconnect refresh, response-order guard. |
| `app/templates/orders_list.html` | Live queue/count refresh and managed fallback polling. |
| `app/templates/orders_view.html` | Live updates to the open customer order, preserving preparation controls. |
| `app/templates/order.html` | Immediate count refresh after confirmed local submission. |
| Focused test file(s) | Verify count semantics and delivery/refresh behavior that the change relies on. |

The backend already provides the relevant events and count API. A database migration or new real-time dependency is not expected. Recheck the current diff before implementation: the shared layout already contains uncommitted work from other tasks.

## 6. Acceptance checks

“Instant” here means that a connected, active browser updates when the committed order event arrives and its data request completes, without waiting for a five- or fifteen-second timer or a manual refresh. Verify responsiveness on the deployed system; network delay still affects delivery. A browser returning from suspension or reconnecting must fetch the current state automatically.

| Check | Expected result |
| --- | --- |
| Place the first order from Staff A's device | Staff A's badge shows 1 automatically. |
| Staff B already has the Orders page open | Its badge, page count, and customer row update automatically. |
| A third staff member is on another application page | The shared Orders navigation badge updates there too. |
| Desktop and mobile navigation | Both badge variants show the same server count. |
| Place more food for the same customer | Badge remains 1 for that session; quantities and details refresh. |
| Place an order for another active customer | Badge and session count become 2. |
| Staff B has that customer's detail page open | Newly placed items appear without reloading the page. |
| Mark an item Ready or Undo on another device | The open details view reflects the state; current badge counting remains unchanged. |
| Mark all items Ready | Served becomes available under the existing rules; the session still counts as pending. |
| Mark the customer Served | Queue and badge decrease on all connected devices; existing action/redirect still works. |
| Existing checkout or item cancellation affects the queue | Refreshes show the existing API's resulting state. |
| Reject an order for invalid input or insufficient stock | No invented increment, customer row, or extra order. |
| Socket event and local success both fire | Count remains correct; no duplicate row or double increment. |
| Two staff submit or complete orders close together | Final count matches the server; older responses cannot restore stale values. |
| Disconnect then reconnect a staff device | It catches up automatically. |
| Socket unavailable temporarily | The existing automatic polling provides recovery. |
| Hidden tab becomes visible | It refreshes the current state automatically. |
| Repeat navigation or reconnect several times | No growing number of socket listeners or polling loops. |

### Focused automated verification

During implementation:

1. Use isolated Flask/Socket.IO clients to verify that a committed new order reaches two authenticated staff clients, and that the count API reports the expected session count.
2. Verify the same-customer, second-customer, Ready, and Served examples from section 2. Extend existing order tests where practical.
3. Exercise the changed browser logic with a controlled event and delayed responses to check automatic refresh and stale-response protection. A source-string assertion alone does not establish that the UI updates.
4. Run the relevant existing socket authorization and food-only order tests. Use the full suite if implementation expands across business domains, following `AGENTS.md`.

Existing tests to consider: [tests/test_socketio_authorization.py](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/tests/test_socketio_authorization.py) and [tests/test_food_only_orders.py](C:/Users/hi/OneDrive/Desktop/vercelIdeahub/tests/test_food_only_orders.py).

This is a display-update task. If implementation starts changing money or inventory writes, pause that expansion and follow the repository's financial auditability and ledger-to-Daily-Balance testing requirements.

### Deployment verification

After implementation is deployed, use two authorized staff accounts on separate devices, since the application has account-session controls. Verify the event and follow-up API requests in both browsers while placing and serving a test order through the normal flow.

If the event fails to reach a connected device, inspect the existing Socket.IO connection, authenticated room membership, proxy transport, and configured message queue. Change deployment configuration only for an observed delivery problem. Local test clients do not verify the VPS/Cloudflare/proxy path.

## 7. Completion checklist

- [ ] Desktop and mobile badges update immediately after order events.
- [ ] The open Orders list and its session count update immediately on other staff devices.
- [ ] Open customer order details receive added items and preparation updates.
- [ ] Existing session-counting rules and prepare/ready/serve behavior are preserved.
- [ ] Confirmed local submission, reconnects, and fallback polling refresh correctly.
- [ ] Duplicate events, failed requests, and out-of-order responses do not corrupt the display.
- [ ] Focused automated checks and a two-device browser check pass.
- [ ] The final diff preserves existing work and contains only the necessary changes.

## 8. What was completed in this planning task

- Asked the owner which displays and devices should update, and whether the counting rule should change.
- Recorded all three answers in this plan.
- Traced the current order submission, commit, event emission, count query, navigation badge, Orders list, and customer order-details paths.
- Identified existing helpers and events that can be reused.
- Created this plan. Application implementation and browser/runtime verification remain pending.
