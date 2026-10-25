# Android home-screen app: Back and login recovery

## Status

Implemented locally on 2026-10-25. Automated tests pass. This change has not been deployed or verified on the owner's Android phone yet. This fix requires no database migration.

## Reported behavior

The owner opens IdeaFlow from an installed home-screen icon. After pressing the phone's **Back** button, reopening IdeaFlow shows the login form. Entering the same account's password says the account is already signed in. The goal is to resume a valid login after Back without weakening the existing session and device limits.

## Cause found in the code

- The installed app starts at `/welcome` ([manifest](../static/manifest.webmanifest)). That route always rendered the sign-in landing page, even when the phone still had a valid login. The duplicate-login message shows that Redis still held an active login lease; it does not, by itself, prove that the login cookie had been lost.
- Login created a browser-session cookie, which may be discarded when an installed app closes. Making it persistent within the existing one-hour idle window covers that case.
- The successful-login redirect used `window.location.href`, leaving an authentication page in browser history. Back could restore that page from the browser's page cache.

## Change made

1. [Login](../app/routes/auth_routes.py) now marks the signed Flask session cookie as permanent. The configured one-hour idle deadline and Redis lease remain authoritative.
2. The [`/welcome` route](../app/__init__.py) validates an existing session and sends an authenticated user back into IdeaFlow. A revoked or expired session is handled by the normal authentication check.
3. Both [login](../app/templates/login.html) and [landing](../app/templates/landing.html) use `location.replace()` after successful sign-in, so the just-used login page is not left as the immediate Back destination.
4. The shared [authentication layout](../app/templates/auth_layout.html) checks session status when an authentication page is restored from the browser's back/forward cache. A still-authenticated user returns to the app instead of seeing a misleading login form.

## Security behavior

- Pressing the phone's Back button does not call Logout or revoke the Redis lease.
- **Logout** still clears the session and releases its lease. One hour without user input still expires the session. A revoked or expired session must sign in again.
- The existing limits are unchanged: staff accounts allow one active login; admin accounts currently allow two active logins per account. Separate named admin accounts are only appropriate for people who actually need admin access.
- No authentication token is stored in JavaScript storage.
- If app data or cookies are deliberately cleared while a Redis lease remains active, another login can still be blocked until that lease expires or an authorized admin revokes it. This is the existing device-protection rule, not the Back-button flow.

## Verification

- Automated: `tests/test_session_leases.py` checks a valid app relaunch, the persistent cookie, blocked login from another device, revoked-session handling, and admin relaunch. The session/PWA targets passed (**27 tests**); the full suite passed (**294 tests**).
- Physical Android check after deployment:
  1. Sign in from the installed home-screen app and open the admin page.
  2. Press the phone's Back button until the app closes, then reopen it immediately from the icon. It should open the admin page without asking for a password.
  3. Navigate between pages and use Back. A cached login page should not appear while the session is valid.
  4. Confirm the device limit with the appropriate account: a second device must be blocked for a staff account; a third simultaneous login must be blocked for an admin account under the current two-slot rule.
  5. Tap **Logout** explicitly. Reopening should now show the login page. Confirm that the normal inactivity timeout still requires a fresh login.

If the phone still asks for a password immediately after Back, capture the time, Android version, whether the app was installed from Chrome, and the exact message. Check server requests to `/welcome`, `/login`, `/api/session-status`, `/api/login`, and `/logout` around that time. Do not collect passwords, cookies, or lease tokens.
