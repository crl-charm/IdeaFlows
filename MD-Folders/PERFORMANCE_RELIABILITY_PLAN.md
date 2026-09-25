# IdeaFlow Performance and Reliability Plan

Status: Phase 1 is installed and fully verified. Phases 2, 3, and 4 are implemented
and verified locally. Phase 5's core write-safety implementation, Phase 6's
real-time authorization implementation, Phase 7's threaded Socket.IO migration, and
Phase 8's CSP/browser-asset cleanup have passed their local automated gates.
Production-browser, two-tab, and deployment gates remain pending until the code is
deployed.

Phase 0 public baseline was captured on 2026-09-13. The Phase 1 production service
change was installed with its rollback path and passed live, ready, WebSocket, and
authenticated two-browser checks.

## Objective

Eliminate unexplained page delays, repeated background requests, broken Socket.IO
reconnections, and duplicate financial or inventory actions without replacing or
resetting production data.

## Non-negotiable safety invariants

- Keep the production MySQL database at `localhost:3306/pos_db`.
- Never copy a local SQLite database to production.
- Never overwrite the VPS `.env` during a code deployment.
- Never overwrite or delete existing R2 objects as part of this work.
- Run schema migrations explicitly and only after a verified MySQL backup.
- Do not enable automatic production migrations.
- Make one independently reversible production change at a time.
- Do not use a successful health check as proof that financial workflows are safe.

## Evidence from the current codebase

### Socket.IO deployment mismatch — critical

- Production was observed running ordinary Gunicorn with three workers.
- `wsgi.py` monkey-patches Eventlet and production defaults to
  `SOCKETIO_ASYNC_MODE=eventlet`.
- `deploy/ideahub.service` expects one Eventlet worker.
- Multi-worker Gunicorn without sticky routing can send Engine.IO polling requests
  to a process that does not own the session, matching the observed HTTP 400 and
  reconnect loop.
- The checked-in service paths use `/var/www/ideahub/.venv`, while the actual VPS
  uses `/var/www/pos/venv`; the service file must be adapted, not copied blindly.
- The checked-in Nginx file contains WebSocket upgrade headers, but this does not
  prove the active VPS Nginx configuration matches it.

### Excessive client refreshes — high

- The codebase contains 14 `createSmartPoller` calls, one raw `setInterval`, and
  eight page-level Socket.IO initializers.
- The admin dashboard calls four loaders directly and then starts four pollers that
  run those loaders again immediately.
- Global layout polling requests order counts, overdue bookings, unpaid
  receivables, and due payables even while the user is idle.
- Menu, inventory, expenses, and receivables reload full datasets after broadcast
  events. Some successful writes also reload directly, causing duplicate reads.

### Redundant and expensive database work — high

- The receivables page queries all receivables while rendering HTML, ignores that
  result in the template, and requests the full list again from JavaScript.
- The menu page similarly supplies menu/category data that JavaScript requests
  again. Menu caching reduces database work but not the extra HTTP request.
- The admin customer count loads complete sessions, orders, order items, menu
  items, and spaces instead of executing a database count.
- Inventory dashboard construction performs additional queries per sellable menu
  item and is an N+1 query path.
- Space prices query the latest history row separately for every space.
- Receivables are unpaginated and creator relationships are not eagerly loaded.

### Duplicate write protection — high

- There are 44 declared state-changing routes and five uses of
  `@idempotent_request`.
- Browser button disabling provides feedback but cannot protect against retries,
  multiple tabs, lost responses, or different clients.
- Expense creation, order creation, customer check-in, and checkout have the new
  protection; many menu, stock, receivable, payable, booking, and status mutations
  do not.

### Socket authorization — high

- The Socket.IO connect handler does not explicitly reject unauthenticated users.
- Operational events are broadcast globally rather than to role-specific rooms.
- CORS origin restrictions are not a substitute for connection authorization.

### CSP console messages — low

- Blocked CDN `.map` files are developer source maps and do not explain application
  latency.
- The Cloudflare Insights beacon is blocked by CSP, so that analytics beacon does
  not run. This should be resolved deliberately without broadly weakening CSP.

### Test baseline

- Static parsing succeeded for 113 Python files.
- A clean Python 3.12 virtual environment was created without changing `.env`.
- The complete isolated suite passes: 93 tests, including browser-request
  coordination and role-specific badge authorization regression tests.
- Rendered inline JavaScript passes `node --check` on all 11 changed pages.
- The pre-existing modified file `instance/ideahub_local.db` remains untouched.

## Implementation phases and gates

### Phase 0 — Production evidence and recovery point

1. Capture sanitized output from the active systemd unit and `nginx -T`.
2. Record Gunicorn, Flask-SocketIO, Engine.IO, Eventlet, Redis, and Nginx versions.
3. Save a browser Network export for admin, menu, inventory, and receivables.
4. Record endpoint response times using `Server-Timing` and slow-request logs.
5. Create a fresh MySQL dump, validate it with `mysqldump` exit status, file size,
   table/data markers, and SHA-256.
6. Archive the active service and Nginx configuration for rollback.

Gate: do not continue until the database backup and configuration rollback files
are verified.

### Phase 1 — Stabilize Socket.IO without redesigning the application

Deployment status: installed and verified on 2026-09-13. Gunicorn is temporarily
pinned to 25.3.0 because version 26 removed its Eventlet worker. Local and public
health checks pass, WebSocket returns HTTP 101, 12/12 Engine.IO polling sessions
completed without HTTP 400, the browser remained free of the prior request loop,
and a staff status event reached a second authenticated browser exactly once.

1. Correct the active service to use the actual `/var/www/pos` paths.
2. Run one Eventlet Gunicorn worker and load `wsgi:application`.
3. Bind Gunicorn to `127.0.0.1:5000`, not every network interface.
4. Confirm the active Nginx `/socket.io/` location forwards Upgrade and Connection
   headers with HTTP/1.1 and suitable timeouts.
5. Keep Redis enabled for broadcasts and rate limiting.

Gate:

- `/health/live` and `/health/ready` return HTTP 200.
- Browser receives a WebSocket HTTP 101 upgrade.
- No Socket.IO HTTP 400 or reconnect loop for ten minutes.
- A menu or inventory update reaches a second authenticated browser once.

Rollback: restore the archived systemd/Nginx files and restart only those services.
No database restore is involved.

### Phase 2 — Repair the local verification environment

Local implementation status: complete. Production was not changed.

1. Create a new virtual environment from an installed, supported Python version.
2. Install project dependencies without changing `.env`.
3. Pin tested production versions in a lock or constraints file.
4. Run the complete existing suite against its in-memory SQLite configuration.

Gate: all existing tests pass before functional refactoring begins.

### Phase 3 — Give each page one refresh owner

Local implementation status: complete for the current page architecture. The
production-browser Network gate below cannot be signed off until deployment.

1. Remove duplicate direct-load plus immediate-poller calls.
2. Create one managed Socket.IO client for the application shell.
3. Subscribe page modules to only the events they require.
4. Coalesce concurrent GET requests and debounce bursts of identical events.
5. Use polling only when Socket.IO is disconnected, with slower intervals and
   exponential backoff.
6. Stop page-specific timers and listeners when navigation replaces their content.
7. Poll global badges only when the relevant element and role are present.

Gate: compare a two-minute idle Network capture before and after. There must be one
socket connection, no repeated failures, no overlapping identical GETs, and only
documented fallback requests.

### Phase 4 — Reduce database and payload cost

Local implementation status: complete. Production data and services were not
changed. Automated query guards confirm that inventory dashboard reads stay at
three queries as rows grow, receivable pages stay bounded at three queries with
pagination and filters, and customer count/latest space prices each use one query.
No indexes were added because no production-compatible query plan has yet shown a
need; this avoids an unproven production schema change.

1. Replace the admin customer-record request used for totals with a count query.
2. Remove unused server-side menu/receivables/inventory list queries or render their
   data directly, choosing one loading strategy per page.
3. Add paginated receivables with eager-loaded creator data and server-side filters.
4. Bulk-load menu items, recipe mappings, ingredients, and inventory rows, then
   calculate inventory capacity in memory.
5. Fetch latest price-history rows with one grouped/subquery operation.
6. Add indexes only when production-compatible query plans demonstrate a need.

Gate: endpoint response payloads remain correct, query counts do not grow per row,
and measured response time improves without stale financial data.

### Phase 5 — Standardize safe write actions

Local implementation status: core protection complete. Every registered business
write route carries a Redis-backed idempotency guard, and the shared browser fetch
layer retains a stable key across uncertain network failures. Checkout, payable,
receivable, and inventory mutations use production row locks. Order creation,
order items, stock deductions, and inventory logs now commit or roll back as one
transaction. Automated coverage checks every write route, a real duplicate expense
submission, and rollback after a simulated stock race. Manual slow-network and
two-tab browser checks remain part of the production gate.

Apply in this priority order:

1. Expenses, receivables, payables, checkout, and sales closing.
2. Inventory stock mutations and recipe changes.
3. Menu changes, bookings, order status, voids, and staff management.

For each action:

- Use `runButtonAction` for immediate and slow-request feedback.
- Send one stable `Idempotency-Key` for an uncertain action and reuse it on retry.
- Add `@idempotent_request` on the matching server route.
- Keep Redis as the cross-process idempotency store.
- Use a database transaction and row locking where concurrent stock or money
  updates could conflict.
- Treat HTTP 409 duplicate responses as “refresh current state,” not as a retry.
- Test double-click, slow response, lost response, refresh, and two-tab scenarios.

Gate: each critical action produces at most one committed business record under
all tested retry scenarios.

### Phase 6 — Authorize and scope real-time events

Local implementation status: complete. Socket.IO rejects anonymous, expired,
inactive, and unsupported-role sessions. Accepted users join authenticated,
role-specific, and user-specific rooms using the current database role. Financial
and staff-status events are restricted to admins, operational events are restricted
to authenticated users, and broadcasts contain compact identifiers/change types.
Connection, rejection, and disconnect logs contain diagnostic context but no
credentials. Automated tests verify anonymous and expired-session rejection,
admin/staff financial isolation, authorized delivery, and payload minimization.
The production two-browser and Nginx/WebSocket gate remains pending deployment.

1. Reject Socket.IO connections without a valid application session.
2. Join users to role-appropriate rooms.
3. Limit financial events to admin clients.
4. Emit identifiers/change types rather than unnecessary record contents.
5. Add connection, rejection, and disconnect observability without logging secrets.

Gate: unauthenticated connections fail, staff cannot receive admin-only finance
events, and authorized real-time updates continue to work.

### Phase 7 — Remove the Eventlet dependency

Local implementation status: complete. The application now explicitly uses
Flask-SocketIO threading mode with `simple-websocket`; Eventlet and monkey-patching
were removed from the active runtime and dependency files. The supplied systemd
unit and Phase 7 drop-in run one Gunicorn `gthread` worker with 50 threads on
`127.0.0.1:5000`. Focused runtime, dependency, authorization, and request-management
tests pass without Eventlet warnings. Full local regression gate: 109 tests passed
on 2026-09-13 with no failures. The production-like Nginx, authenticated WebSocket,
concurrency, and rollback gates remain pending deployment.

After Phases 1–6 are stable:

1. Add and test `simple-websocket` with Flask-SocketIO threading mode.
2. Remove Eventlet monkey-patching from `wsgi.py`.
3. Update configuration, requirements, service definitions, and documentation
   together.
4. Keep one threaded Gunicorn worker unless a separately tested sticky-session
   architecture is introduced.

Gate: full automated suite, authenticated WebSocket tests, concurrency tests, and
the production-like Nginx smoke test pass without Eventlet warnings.

### Phase 8 — CSP and third-party asset cleanup

Local implementation status: complete. Cloudflare Web Analytics remains enabled and
its documented script/reporting origins are explicitly allowlisted. The two existing
asset CDNs are allowlisted only where their pinned assets and developer source maps
need them; no wildcard or broad scheme source was added. The unused jQuery script
permission and broad HTTPS image permission were removed, Chart.js was pinned, and
the authentication layout now uses the same pinned Bootstrap and Bootstrap Icons
versions as the application layout. CSP hardening adds explicit `script-src-elem`,
`base-uri`, `object-src`, `form-action`, and `frame-ancestors` directives. Focused CSP
and asset tests passed, followed by the full local gate of 111 tests with no failures
on 2026-09-13. Browser-console confirmation remains a post-deployment gate.

1. Decide whether Cloudflare browser analytics is required.
2. If not required, disable its injection. If required, allow only its exact script
   and reporting origins.
3. Prefer pinned, self-hosted Bootstrap and Socket.IO assets to eliminate source-map
   console noise and reduce third-party runtime dependency.
4. Do not add broad wildcard CSP sources.

### Phase 9 — Controlled production deployment

Pre-deployment status: local safety preparation is complete. Runtime database and
upload paths are ignored, the production-config startup gate passes, no model/schema
change is present, and the full local suite passed 113 tests on 2026-09-13 with no
failures. The controlled VPS deployment has not started. It is waiting for the owner
to remove historically tracked runtime files from Git's index, review the release,
and create/push the release commit. Production `.env`, MySQL, R2, uploads, services,
and code remain unchanged by this phase so far. Follow
`MD-Folders/PHASE9_DEPLOYMENT_RUNBOOK.md` one gate at a time after that commit exists.

1. Create and verify a new database backup.
2. Deploy tracked code only; preserve `.env`, MySQL, R2, and local upload directories.
3. Run reviewed migrations explicitly.
4. Restart the application and execute health, login, Turnstile, Access, Redis, R2,
   menu, inventory, expense, receivable, order, and checkout smoke tests.
5. Monitor Socket.IO failures, HTTP 5xx, slow requests, and duplicate records.

Final acceptance:

- No Socket.IO 400/reconnect loop.
- Idle request volume matches the documented design.
- Receivables navigation displays a visible loading state and has measured latency.
- Menu and inventory mutations refresh once.
- Critical writes cannot duplicate under slow or uncertain connections.
- MySQL row counts and financial totals remain consistent across deployment.
- R2 uploads and existing media URLs remain intact.

## Required new tests

- Authenticated and unauthenticated Socket.IO connection tests.
- Role-room event isolation tests.
- Admin initial-load and idle-request budget test.
- Polling fallback/recovery test.
- Receivables pagination and eager-loading test.
- Inventory query-count regression test.
- Idempotency tests for every money/stock route.
- Concurrent stock-decrement and payment mutation tests.
- Production-config startup test for Redis, R2, Turnstile, and migration flags.
- Nginx-to-Socket.IO WebSocket smoke test in a production-like environment.

## Execution rule

Phases 2 and 3 were implemented locally after explicit approval. Do not combine
their eventual deployment with an unverified Phase 1 service change; make each
production change independently reversible and run its gate before continuing.
