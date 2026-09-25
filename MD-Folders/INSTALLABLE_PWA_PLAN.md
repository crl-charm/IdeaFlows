# Installable Web App (PWA) Plan

## Purpose

Make IdeaFlow installable from its website on supported mobile phones, tablets,
and desktop computers. The installed experience should open in its own app window,
use the IdeaFlow name and icon, and remain protected by Cloudflare Access and the
application login.

This is a Progressive Web App (PWA), not a separate Android, iOS, or Windows
native application. Users continue to visit the same production website and use
the same live server and database.

## Important user expectation

Installing the PWA does **not** download the production database or make private
business records available offline. It installs the safe application shell and a
launcher icon. Live pages and business actions still require an internet
connection and successful authentication.

## Current baseline

The project currently has `static/images/Faviconlogo.jpg`, but no detected web app
manifest, service worker, install prompt, offline page, or PWA-specific icon set.

Production already provides important prerequisites:

- HTTPS through the live domain.
- Responsive layouts for mobile, tablet, and desktop.
- Cloudflare Access in front of protected production access.
- Application authentication, CSRF protection, CSP, and secure cookies.
- Versioned static assets.

## Success criteria

- Supported browsers recognize IdeaFlow as installable.
- A clear **Install IdeaFlow** button appears only when installation is available.
- Android Chrome and compatible Chromium browsers show the native install prompt.
- Desktop Chrome and Edge can install the app into a standalone window.
- iPhone and iPad users receive accurate Safari “Add to Home Screen” guidance.
- The install button disappears when the app is already installed or installation
  is unavailable.
- The installed app starts at a safe same-origin URL and preserves normal login
  behavior.
- Cloudflare Access, Turnstile, app login, one-session enforcement, and role-based
  authorization work exactly as they do in the browser.
- API responses, database rows, finance pages, authentication pages, session data,
  and Socket.IO traffic are never stored in the service-worker cache.
- Losing the internet displays a simple safe offline screen rather than stale
  private information.
- Application updates do not interrupt an order, checkout, report, or data-entry
  operation.

## Browser behavior

Installation is controlled partly by each operating system and browser:

- **Android Chrome/Edge:** show the browser's native installation prompt when the
  PWA meets installability requirements.
- **Windows/macOS Chrome or Edge:** install into a standalone app window through
  the native prompt or browser install control.
- **iPhone/iPad Safari:** browsers generally do not provide the same programmable
  install prompt. Show instructions for **Share → Add to Home Screen**.
- **Unsupported browsers:** keep the website fully usable and hide the install
  button. Do not show a fake success message.

Exact browser wording and placement can change, so the interface should explain
the supported action without promising that every browser exposes the same button.

## PWA components

### Web app manifest

Add a same-origin manifest such as `static/manifest.webmanifest` containing:

- Full name: `IdeaFlow`.
- Short name suitable for an app icon.
- A safe `start_url`, normally `/login` or another reviewed entry route.
- Same-origin scope.
- `display: standalone`.
- Theme and background colors matching the existing brand.
- Stable application identifier.
- Portrait and landscape-friendly behavior rather than forcing one orientation.
- Standard 192×192 and 512×512 icons.
- Maskable icons with safe padding.
- Optional monochrome icon where supported.
- Optional shortcuts only for routes safe for the current authenticated role.

Do not place secrets, environment-specific credentials, user information, or
private URLs in the manifest.

### Install icons

Create a reviewed icon set from the official IdeaFlow logo rather than merely
resizing an arbitrary screenshot. Required output should include at least:

- 192×192 PNG.
- 512×512 PNG.
- 192×192 maskable PNG.
- 512×512 maskable PNG.
- Apple touch icon, normally 180×180 PNG.
- Browser favicon formats as needed.

Icons must remain readable when Android applies circular, rounded-square, or other
platform masks. Keep important artwork within the maskable safe zone and verify
light and dark device backgrounds.

### HTML metadata

Add shared metadata to the public/authenticated base layouts:

- Manifest link.
- Theme color.
- Apple touch icon.
- Application name.
- Mobile web-app capability metadata where still useful.

Every entry page should receive consistent metadata through the shared layouts;
avoid copying divergent tags into individual pages.

### Service worker

Register one same-origin service worker from a shared external JavaScript file.
Keep its initial responsibility deliberately small:

- Cache only an explicitly listed, versioned set of public static CSS, JavaScript,
  fonts, safe icons, and the generic offline page.
- Use network-only handling for authenticated documents and dynamic data.
- Use network-only handling for `/api/`, `/socket.io/`, login, logout, admin,
  finance, report, and mutation routes.
- Never cache responses containing `Cache-Control: no-store`.
- Never cache non-GET requests.
- Never cache responses containing authorization or user-specific information.
- Never store cookies, CSRF tokens, Turnstile data, database rows, or generated
  financial reports in Cache Storage.
- Restrict caches to the IdeaFlow origin and a fixed allowlist.
- Remove obsolete cache versions during activation.

Avoid a broad “cache everything” or uncontrolled runtime-cache strategy. Such a
strategy could display one user's private data to another user on a shared device.

### Offline page

Provide a small static offline page that contains no private application data. It
should explain:

> IdeaFlow needs an internet connection for live business data. Reconnect and try
> again.

Include a retry control. Do not pretend an order, checkout, upload, or report was
saved while offline. The first release should not queue business mutations for
later synchronization.

### Install interface

Add a reusable installation controller that:

1. Captures the browser's `beforeinstallprompt` event where supported.
2. Reveals **Install IdeaFlow** only when the prompt is available.
3. Opens the real browser installation prompt after a user gesture.
4. Records only a non-sensitive preference if the user dismisses it.
5. Detects `display-mode: standalone` and hides the button when already installed.
6. Handles the `appinstalled` event and shows a short success notice.
7. Shows separate Safari instructions on eligible iPhone/iPad devices.
8. Leaves unsupported browsers unchanged.

Suggested locations are the login page and a Profile or Settings section. Avoid a
large prompt on every page or every visit. Let users dismiss the suggestion.

### Update behavior

Service-worker updates must not automatically reload an active business page.
When a new version is waiting:

- Show **Update available**.
- Let the user choose **Update now** at a safe moment.
- Warn or defer when a form, checkout, report, or other unsaved operation is active.
- Activate the new worker and reload only after user confirmation.

Do not use an unconditional reload loop or silently replace assets in the middle
of a transaction.

## Authentication and security boundaries

- Installation does not bypass Cloudflare Access.
- Installation does not bypass the IdeaFlow login.
- Secure and SameSite cookie behavior remains unchanged.
- The planned one-active-session-per-account rule applies equally inside the
  installed PWA.
- Logging out must remove the authenticated browser state and release its Redis
  session lease, but it should not need to uninstall the PWA.
- Shared-device users must log out explicitly.
- Sensitive pages retain `Cache-Control: no-store`.
- The service worker must not log request bodies, credentials, tokens, or URLs that
  contain private query data.
- Content Security Policy must permit only the same-origin manifest, worker, and
  required assets; do not weaken the policy broadly.

## Implementation phases

### Phase 0 — Baseline and route classification

- Record the current Git commit and run the complete test suite.
- Inventory all layouts, static assets, API routes, Socket.IO paths, authentication
  routes, report downloads, media URLs, and sensitive pages.
- Classify every route as cacheable static content, network-only content, or offline
  fallback.
- Confirm current cache headers for HTML, static assets, R2 media, APIs, and report
  downloads.

### Phase 1 — Brand assets and manifest

- Review the official logo source and generate the complete icon set.
- Add the web manifest with stable identity, scope, colors, icons, and start URL.
- Add manifest and platform metadata to shared layouts.
- Validate icon dimensions, transparency, maskable safe zone, MIME types, and
  manifest JSON.

### Phase 2 — Safe service worker

- Add the minimal allowlisted static cache.
- Add explicit network-only rules for private and dynamic routes.
- Add cache version cleanup.
- Add a generic offline response for document navigation only.
- Ensure failed POST/PUT/PATCH/DELETE operations return normal network failures and
  are never queued silently.

### Phase 3 — Installation experience

- Add the reusable install controller.
- Add the install button to approved locations.
- Add Android/Chromium native prompt handling.
- Add iPhone/iPad Safari instructions.
- Add installed-state and dismissal handling.
- Ensure keyboard operation, screen-reader labels, and accessible focus behavior.

### Phase 4 — Safe updates

- Detect a waiting service worker.
- Add an update-available notice.
- Prevent automatic refresh during unsaved work.
- Add user-confirmed activation and one controlled reload.
- Prevent update/reload loops.

### Phase 5 — Automated validation

- Test manifest delivery, content type, required fields, and icon references.
- Test service-worker registration and scope.
- Test the complete cache allowlist.
- Prove APIs, authenticated HTML, database viewer, Socket.IO, reports, and mutation
  requests are never cached.
- Test obsolete cache cleanup.
- Test offline navigation and retry behavior.
- Test install-button visibility, dismissal, installed mode, Safari guidance, and
  unsupported-browser behavior.
- Test update notification and unsaved-form protection.
- Run all existing security, UI, authentication, Socket.IO, and business tests.

### Phase 6 — Local browser acceptance

- Test normal browser mode and installed standalone mode.
- Test Chrome or Edge desktop installation.
- Test an Android-sized browser and, when available, a real Android device.
- Test iPhone/iPad Safari guidance on a real device when available.
- Test phone, tablet, and desktop responsive layouts.
- Test online, slow-network, temporary disconnect, and reconnection behavior.
- Confirm no private response appears in Application → Cache Storage.
- Confirm logout/login works on a shared-device test profile.
- Run Lighthouse PWA checks as supporting evidence, not as the only acceptance
  test.

### Phase 7 — Controlled deployment

- Verify GitHub validation is green.
- Record the production commit and dirty runtime files.
- Create and verify fresh database and production-file backups.
- Pull with `git pull --ff-only`; never reset production changes.
- Restart the application only after preflight validation succeeds.
- Verify manifest, icons, worker script, offline page, and cache headers over the
  production HTTPS domain.
- Confirm Cloudflare does not cache private HTML or interfere with worker updates.

### Phase 8 — Production acceptance

- Install on one desktop and one mobile device using test accounts.
- Verify Cloudflare Access, Turnstile, app login, logout, and role permissions.
- Confirm one stable Socket.IO connection after launch.
- Confirm no reconnect loop or repeated bad requests.
- Verify orders, checkout, reports, uploads, and database viewing still require the
  live server.
- Deploy a harmless version change and verify the update prompt.
- Review browser console, network traffic, Cache Storage, server logs, and health
  endpoints.
- Monitor errors and installation feedback before promoting the feature broadly.

## Required tests

At minimum, automated and browser coverage must prove:

- Manifest is valid and served from the expected origin.
- Every referenced icon exists and has the declared dimensions.
- Worker registration cannot escape the intended scope.
- Only reviewed static assets enter Cache Storage.
- Auth pages, API JSON, database rows, finance data, reports, Socket.IO, and R2
  credentials never enter Cache Storage.
- Non-GET requests are never cached or replayed.
- Offline mode cannot claim that a business mutation succeeded.
- Install UI is hidden when unavailable or already installed.
- Safari receives instructions rather than a fake native prompt.
- An update never reloads a page with unsaved work without confirmation.
- Existing skeleton screens and page transitions continue to work.
- Modal inputs, report generation, login, RBAC, and Socket.IO do not regress.

## Operational notes

- Browser installation availability cannot be forced on every browser.
- Users can always continue using the ordinary website.
- A PWA installation is updated from the live website; it is not a separately
  maintained copy of the codebase.
- Web push notifications, background synchronization, and offline business writes
  are excluded from the first release. They require separate privacy, reliability,
  and permission plans.
- If public app-store distribution is later required, evaluate packaging the PWA
  separately rather than mixing it into this first installation release.

## Rollback strategy

- Keep the previous Git commit and production backups.
- Disable new service-worker registration if a serious issue appears.
- Ship a replacement worker that deletes only caches owned by IdeaFlow and then
  unregisters safely if full rollback is required.
- Do not delete unrelated browser storage.
- Do not change or restore the database for a PWA-only rollback.
- Preserve normal web access even when installation features are disabled.

## Resolved implementation decisions

1. Displayed and short app name: `IdeaFlow`.
2. Install artwork: the official `static/promotional/logo.png` logo.
3. Install-button location remains a Phase 3 decision; default to Login first.
4. Theme/background colors: `#2a4f43` and `#fef9f0`.
5. The first release remains online-only for all business operations.

## Phase 0–1 implementation record

- Baseline commit: `0676d1b`.
- App identity: `IdeaFlow`; installed start URL: `/welcome`.
- Brand source: `static/promotional/logo.png`; theme `#2a4f43`; background `#fef9f0`.
- Public static allowlist candidates: the manifest, PWA icons, generic offline page,
  and explicitly named public CSS/JavaScript assets only.
- Network-only documents: `/`, `/welcome`, `/login`, `/logout`, `/register`, and
  every authenticated page, including admin, staff, finance, inventory, ordering,
  booking, receipts, profile, and reporting pages.
- Network-only data/transports: every `/api/` request, `/socket.io/`, every
  non-GET request, report/export downloads, uploaded/R2 media, and any response
  marked `no-store`.
- Current app static assets use `public, max-age=3600, must-revalidate`; uploaded
  versioned media uses a one-year immutable cache. HTML/API responses are not
  candidates for the future service-worker cache.
- Local full-suite execution is currently unavailable because the checked-in
  `.venv` points to a removed Windows Store Python installation. Run the suite
  in the normal development environment before deployment; production does not
  need `pytest` installed.
- Phase 1 adds the manifest, 192/512 regular and maskable icons, Apple touch icon,
  shared metadata, and manifest/icon validation. It does not register a service
  worker and therefore does not change runtime caching yet.
- Phase 3 adds a hidden-by-default install control to the login experience. It
  uses the real Chromium install prompt when offered, gives Safari-only iPhone
  and iPad instructions, hides itself in standalone/unsupported browsers, and
  announces successful installation without weakening authentication.
- Phase 2 adds a root-scoped worker with a fixed public-shell allowlist, obsolete
  IdeaFlow-cache cleanup, and a generic offline navigation page. Dynamic pages,
  APIs, Socket.IO, reports, uploads, cross-origin media, and every non-GET request
  remain network-only and are never queued or written to runtime cache.
- Phase 4 detects waiting workers and shows a dismissible update notice. Activation
  occurs only after **Update now**, edited forms require an additional warning,
  and a controller-change plus session guard permits at most one controlled reload.
- Phase 5 keeps all PWA regression coverage in `tests/test_pwa_manifest.py`,
  including exact allowlist equality, private-route exclusions, offline fallback,
  cache cleanup, install-state behavior, and guarded update activation.
- Phase 6 local acceptance passed at 1280×720 desktop, 768×1024 tablet, and
  390×844 phone sizes for the promotional and welcome/login experiences, with no
  horizontal overflow. The offline page rendered its safe message and retry control,
  and the unsupported in-app browser correctly kept installation hidden.
- Native Chrome/Edge installation, standalone display mode, real Android/iOS,
  offline interception/reconnection, Cache Storage inspection, shared-device
  logout/login, and Lighthouse remain manual acceptance items because only the
  in-app browser is available here and it does not expose Service Worker storage.
- Phase 7 local preflight passed on baseline commit `0676d1b`: scoped diff and
  credential scans are clean, required assets exist, and local manifest, worker,
  offline page, icons, and update-controller headers return HTTP 200. GitHub CI,
  backup, VPS pull/restart, and production HTTPS checks remain deployment gates.
- Phase 8 local acceptance preparation passed: the public welcome page loads with
  the manifest and PWA controllers, has no horizontal overflow or browser-console
  errors, JavaScript syntax is valid, manifest identity is correct, and every icon
  matches its declared dimensions. Production acceptance remains pending until the
  Phase 7 commit is pushed, CI passes, and the VPS is deployed. Then verify desktop
  and mobile installation, authentication/RBAC, one stable Socket.IO connection,
  network-only business operations, Cache Storage, offline recovery, and one harmless
  update prompt on the live HTTPS origin.
