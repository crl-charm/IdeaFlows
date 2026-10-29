# System Updates icon beside IdeaFlow

**Date:** October 29, 2026  
**Status:** Implemented and verified on localhost on October 29, 2026, and included in this source release. This feature required no database migration. VPS deployment has not been performed.

## Goal

Help the owner and staff discover system changes and learn where to use them. Put a small bell icon immediately to the right of the IdeaFlow name in the existing top-left header. Clicking it opens **What's new in IdeaFlow**.

Keep the first view short. Each update has a title and one-sentence summary; expanding it shows its location, a short usage guide, and an **Open page** link where relevant.

## Implemented user flow

1. A signed-in admin or staff member sees the bell beside IdeaFlow. A small dot means there are new updates for this account on this browser/device.
2. Tap the bell to open one **System updates** modal. Show newest updates first, with their release date, title, short summary, and **View details** control.
3. Expand an update to see **What changed**, **Where to find it**, and **How to use it** in two to four steps.
4. Tap **Open page** to close the modal and navigate to the relevant page. For a feature inside an existing modal, open its parent page and explain which button to tap; do not trigger a financial or customer action automatically.
5. Opening the updates list clears the new dot for the visible entries on this browser. The user can reopen and read the history anytime. A later release adds the dot again.

The bell is its own button, outside the IdeaFlow dashboard link. Clicking it must not also navigate to Dashboard.

## Example update

**Summary shown first**

> **Monthly accountant PDF**  
> Export one monthly file containing sales, salaries, expenses, and employee attendance.  
> View details

**Expanded details**

- **What changed:** There is now one monthly report for the accountant. Salaries are included in Total Expenses once.
- **Where:** Reports & Exports → Monthly Accountant Report.
- **How to use:** Choose a month, tap Review / Refresh, review the sections and any notices, then tap Export Accountant PDF.
- **Before exporting:** Enter salary payments through Expenses → Salaries, selecting the employee and salary month. Resolve any older salary records marked for review.
- **Open page:** `/admin/reports?view=monthly`.
- **Audience:** Admins only.

This describes the feature. It contains no actual employee names, pay amounts, customer records, or business totals.

## Initial content to prepare

Use concise, verified notes for the recent features below. The entries become visible only in an application release that actually contains the feature; a local build must not be described as already deployed to production.

| Update | Audience | Location / usage summary |
| --- | --- | --- |
| Monthly accountant PDF | Admin | Reports & Exports → Monthly Accountant Report → choose month → review → export. |
| Customer statement PDF | Admin | Reports & Exports → Customer Statement → select a receivables customer → review the saved history → export. |
| Salaries in Expenses | Admin | Expenses → Log Expense / Salary → Salaries → choose employee, salary month, amount, and payment details. |
| Repairs / Maintenance category | Admin and staff | Expenses → Log Expense → Repairs / Maintenance → record the repair and payment details. |
| Late customer check-in | Admin and staff | Dashboard → + → Late Customer Check-in → choose an earlier arrival today in Manila time for Regular or Premium. |
| Pause and resume customer time | Admin and staff | Dashboard → customer actions → Pause time / Resume time → confirm. Food orders remain available while time is paused. |

Group related notes under the same release date, with one expandable entry per feature. Verify their wording and links against the version being released. Planned features, such as a change documented but not yet implemented, do not appear as completed updates.

## Admin and staff visibility

- Admins see all published entries relevant to their access. All current admin accounts use the same view.
- Staff see entries for the features/pages available to them, using the same access rules as the existing navigation. Admin-only salary, accountant-report, and customer-export entries are excluded before rendering the staff page.
- Shared entries use the correct destination for the signed-in role. For example, Expenses links to `/admin/expenses` for admins and `/expenses-view` for staff.
- The bell appears in the signed-in admin/staff layout. Public customer and login pages retain their existing headers.
- Opening an update does not change permissions. Destination pages keep their existing authorization checks.

## Header, modal, and mobile behavior

- Reuse the current IdeaFlow logo, fonts, colors, Bootstrap icons, and Bootstrap modal styling. The bell is the real `bi-bell` font icon, not an emoji.
- Desktop: logo + IdeaFlow + bell grouped on the left; existing header actions stay usable.
- On narrow phones, the header currently hides the IdeaFlow text. Keep the bell beside the logo and preserve room for Time In/Out, Cash Boxes, Orders, and the menu.
- Give the bell an accessible label/tooltip, **System updates**, and a comfortable touch target. The dot must not be the only way to identify the control.
- Use a single vertically scrolling modal with a visible title and close button. Stack content at phone widths; wrap titles, instructions, and links without horizontal scrolling.
- Use native expandable details or the existing Bootstrap disclosure behavior. Support keyboard activation, Escape, proper focus return, and screen-reader labels.
- Opening or closing the list preserves the user's current form and page. Follow existing navigation behavior when the user intentionally selects Open page; do not force an app reload or install an update.

## Minimal implementation approach

Use a small developer-maintained update catalog bundled with each application release. Each entry contains:

- Stable update ID and release date.
- Title and short summary.
- Allowed audience.
- What changed, location, and short usage steps.
- Optional internal destination, with role-specific paths where needed.

Implementation locations:

| File | Responsibility |
| --- | --- |
| `app/system_updates.py` | Small catalog and role filtering; plain structured text and trusted internal destinations. |
| `app/__init__.py` | Make the allowed entries available to the shared layout through a context processor. |
| `app/templates/layout.html` | Place the bell beside the brand link and include the modal once with the other shared controls. |
| `app/templates/partials/system_updates.html` | Render the summary list, expandable details, and destination links. |
| `static/js/system-updates.js` | Open/read-state handling using the current Bootstrap modal and browser storage. Reuse existing navigation conventions. |

Render the role-filtered content with Jinja and ordinary escaped text. Maintain the catalog alongside the feature it documents and review the note before release. A note about a newly changed instruction gets a new ID so it can appear as new again.

Keep read state in browser local storage, scoped to the current account ID and role. It stores only seen update IDs, not credentials or business data. This avoids a database migration for the first version. Read status is independent on another device; clearing browser storage may show the dot again. If storage is unavailable, the list still opens and works.

The current PWA banner in `static/js/pwa-register.js` already handles installing a waiting app version. Preserve that behavior: this bell explains changes in the running application and does not activate a waiting version. When the user finishes the existing app-update flow, the new release's notes become available.

## Verification before calling it complete

1. Admin sees all applicable entries; staff responses omit admin-only entries and destinations. Anonymous/public pages have no internal updates list.
2. Bell opens the modal without following the brand link. Close, Escape, keyboard navigation, and focus return work.
3. Summary-first layout and expansion work for every seeded entry; Open page reaches the correct role-specific page and performs no business write.
4. New dot clears after the list opens, stays cleared on refresh for the same account/browser, and returns when a new allowed update ID is added. Another account on the same device has its own read state.
5. Blocking local storage does not break the page or modal. Existing pages also load when real-time connectivity is unavailable.
6. Check 320, 375, 768, and 1366-pixel widths with long titles and expanded instructions. Header actions and modal have no sideways scrolling.
7. Check regular page loads and existing in-app navigation: one bell, one modal, no duplicate handlers, and the correct account's content after logout/login or Back navigation.
8. Verify the visible notes match the features actually included in that build. Keep payroll/account details and technical deployment messages out of the user-facing notes.

## Scope of the local delivery

The local implementation delivers the header bell, shared update modal, six initial notes, and per-account/device new-dot state. Publishing this source release to GitHub does not deploy it to the VPS; production rollout remains a separate requested step.

## Local verification completed

- **14 automated checks passed**, covering server-side audience filtering, correct role-specific destinations, the real icon markup, anonymous/public pages, account-scoped read state, new note IDs, blocked/corrupt storage, repeated script execution, and adjacent shared-page startup/request behavior.
- The browser confirmed the real Bootstrap icon font renders, summaries start collapsed, details work with the keyboard, Escape closes the modal, focus returns to the bell, and opening/closing preserves an unsaved form value.
- Expanded admin and staff notes fit **320, 375, 768, and 1366-pixel widths**. The header stays on one row and the modal has no horizontal scrolling. Desktop and phone screenshots were visually inspected.
- The actual Open page controls reached the monthly accountant report and staff Expenses page, with one bell/modal after navigation.
- Different accounts have independent new-dot state. Back navigation after switching accounts refreshes the full authenticated header when its account/role differs, reusing the existing navigation response.
- Login and public customer pages have no internal updates control. The modal still works with local storage blocked and real-time connections unavailable. There were **zero browser page errors**.
- All browser writes used isolated sample users in an in-memory database. This feature made no changes to business records.
- **Release verification, October 30:** all 460 distinct cases have passing results across the full regression and affected-suite follow-up runs. This includes rendering PDF templates without a browser request, and customer statement/API privacy independently of admin-only update instructions.

## Maintaining future notes

Add reviewed entries at the top of `SYSTEM_UPDATES` in `app/system_updates.py`, with a new stable ID, release date, short summary, instructions, and explicit role-specific `paths`. Only roles present in `paths` receive that note; the other paths are removed before the template receives it. Instructions are ordinary escaped text.

Ship a feature and its notes together. When instructions change materially, publish a new ID so the new-dot state can draw attention to that change. Read status stays local to each account/browser and does not sync across devices.
