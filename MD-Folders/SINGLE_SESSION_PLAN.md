# One Active Login Session

## Behavior

- Each administrator or staff account may have one active browser session.
- Tabs sharing the same browser cookie count as the same session.
- A verified login from another browser is rejected with HTTP `409`.
- The active browser is notified about the verified second-login attempt.
- Normal logout releases the Redis lease immediately.
- A session expires after one hour without user input. Background requests and
  session status checks do not extend it.
- Administrators can inspect and revoke other active sessions from the Admin
  Panel.
- Revoked or expired sessions are rejected by both HTTP and Socket.IO.
- Redis failure fails closed in production instead of permitting duplicate
  logins.

## Configuration

```dotenv
SINGLE_SESSION_ENABLED=true
SESSION_HEARTBEAT_SECONDS=30
SESSION_LEASE_KEY_PREFIX=ideahub:active-login
```

Production requires a working `REDIS_URL`. Development keeps the feature off by
default so local login continues to work without Redis. To test it locally, run a
local Redis server and explicitly set `SINGLE_SESSION_ENABLED=true`.

## Deployment checks

1. Confirm Redis responds successfully.
2. Add the configuration above. The old `SESSION_LEASE_TTL_SECONDS` setting is
   ignored; the lease now shares the one-hour HTTP idle deadline.
3. Run `python -m app.db.run_migrations` from the deployed project with its
   production environment, then restart `ideahub`. This adds
   `staff_attendance.last_activity_at` when startup migration is disabled.
4. Sign in with one browser, then try the same account in a private browser.
5. Confirm the second browser is blocked and the first browser receives a notice.
6. Log out in the first browser and confirm the private browser can then sign in.
7. Confirm the Admin Panel's **Active Sessions** dialog lists sessions without
   revealing lease tokens.

Existing sessions are expected to sign in again once when this feature is first
enabled because their old cookies contain no Redis lease token.
