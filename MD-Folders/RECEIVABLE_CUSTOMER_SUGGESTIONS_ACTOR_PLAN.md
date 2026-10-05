# Receivable customer suggestions and automatic staff attribution

**Week of October 5, 2026 · Status: implemented locally October 6, 2026; not deployed.** Customer utang means money the customer owes the business. This task changes how staff choose a customer for a **new** debt; it must preserve all earlier debt and collection history.

## Confirmed behavior

- From **+ New Receivable** on the staff page, typing a name or contact shows matching customers already in the database, including customers whose old tabs are fully paid. Suggestions search across **all dates** even when the page currently shows only today's Date Taken.
- Staff can select an existing customer identity or enter a new one. If the selected customer has an **open tab**, the new debt joins that tab. If their old tab is fully paid, the new debt starts a **fresh tab** and the old paid history stays under the prior cycle.
- A new debt taken today remains on today's Date Taken view even if the customer's earlier debt was taken yesterday. It also contributes to the current open tab's all-date balance. No old paid orders are copied into the new tab.
- **Approved by staff** fills automatically from the signed-in account (for example, Carl). Staff do not type or override that identity. The durable `created_by` user ID and the displayed name must agree.
- Existing **Add order** on a Customer tab remains a shortcut. The new customer suggestions also make the top-level **+ New Receivable** useful when today's date filter hides a customer's earlier open tab.

## Current code and gap

- `app/models/receivable.py` already has `ReceivableTab` with normalized name/contact, `active_key`, open/closed timestamps, and `Receivable` with `created_by`, `approved_by_staff`, Date Taken, items, amount, and `tab_id`. The earlier dated-tabs implementation keeps paid tabs out of the active list.
- `static/js/receivables-dated.js::suggestions` calls the tabs endpoint and suggests **open tabs only**. It only runs after typing in the Add Receivable modal, uses the name as its query, and cannot find a customer whose last tab closed. The Customer tabs table is filtered by selected Date Taken, so an older open tab may not appear on today's page.
- `app/templates/partials/receivables_workspace.html` has an editable **Approved by staff** input. Both `app/routes/staff_receivables.py` and `app/routes/receivables.py` currently forward browser-supplied `approved_by_staff` into `ReceivableService.create`; this allows a name that differs from the authenticated actor.
- `app/repositories/receivable_repository.py::create` already reuses an open tab with the same normalized name+nonblank contact, creates a fresh tab after closure, and validates an explicitly selected open tab. Keep this transaction/uniqueness logic; do not rebuild tab rules in JavaScript.
- The shared Receivables workspace/JS is used by admin and staff. Reuse it so suggestions work consistently while keeping the role-specific API prefixes. Staff must not need `/admin/...` requests.

## Read API and matching

1. Add a small authenticated customer-suggestion endpoint under each existing Receivables prefix, backed by **one** shared repository/service query. Search distinct normalized name+contact identities from `ReceivableTab` (plus legacy receivables without a tab if present), not just current open tabs. No date filter. Return at most 10–20 matches with safe display name, contact, `open_tab_id` or null, and an **Open tab** or **Past customer—new tab** label. Do not return debt amounts or private history unless required to distinguish identities.
2. Require a minimum useful query length, cap input length, use bound SQL parameters, and escape wildcard characters and all rendered text. Sort exact name/contact matches first, then recent identities. Send a normal error response on failed authorization instead of an empty suggestion list.
3. Normalize whitespace/case the same way as `ReceivableTab.identity`. The same name with different contacts is separate; show the contact in each suggestion. For same-name blank-contact customers, never auto-merge solely on a name. Require explicit selection of the matching **open tab** when joining one, or allow a deliberately new tab.
4. A selected open-tab suggestion sets its `tab_id` and locks/fills name/contact in the modal. A selected paid-history suggestion fills name/contact but leaves `tab_id` empty; the next save opens a fresh cycle. If another user closes the tab before save, the server returns a clear conflict and the modal refreshes suggestions.

## Form and write path

1. In `static/js/receivables-dated.js`, debounce name/contact search, ignore stale responses, show accessible suggestion buttons or a labelled select, and let staff keep typing **New customer** without choosing a suggestion. Clear the selected identity and tab ID if the text is edited afterward; never submit an old tab ID for a new name. The suggestion request must remain independent of the Date Taken filter.
2. In the shared modal, display **Approved by staff: [signed-in username]** as read-only text, or omit the editable field entirely. The server must derive the stored `approved_by_staff` from the authenticated `created_by` user/account, ignoring any submitted value. Keep `created_by` as the permanent user-ID link and preserve historical free-text values.
3. Apply the same server-side actor rule to both staff and admin create routes. Keep existing CSRF, idempotency, amount validation, date validation, and tab locking. Do not let a suggested name alter money, create an order, or mark an old debt paid by itself.
4. After save, refresh today's dated records, customer tabs, and all-date outstanding total. A debt entered with yesterday's Date Taken appears under yesterday even if entered today; only its true Date Taken determines the debt view. Collections still post to Daily Balance by **payment date**, not Date Taken.

## Examples

- Carl borrowed ₱100 on September 30 and still owes it. On October 5, staff search **Carl**, choose his open tab, and record ₱50 of new items with Date Taken October 5. September 30 shows ₱100 taken; October 5 shows ₱50 taken; the one open tab shows ₱150 owed across dates.
- Carl pays all ₱150. His active tab disappears. On October 8, staff select him from **Past customer** suggestions and record ₱30. A new tab ID starts at ₱30; the old debts and payments remain visible in history.
- Two people named Carl with different contacts appear as separate suggestions. A blank contact never silently joins the wrong person's debt.

## Verification and acceptance

- Tests for same name/different contact, case/spacing normalization, blank-contact ambiguity, an open tab from yesterday suggested while Today is selected, a fully paid historical identity creating a new tab, stale/closed tab conflict, new customer, and retry not creating duplicate debt.
- Test that a crafted request with `approved_by_staff="someone else"` stores the authenticated username and `created_by` ID for staff and admin. Verify old historical approved names are unchanged.
- Financial test: the new October 5 debt increases outstanding balance but does **not** increase today's cash or checkout revenue; a later partial/full payment produces the existing `ReceivablePayment` history and appears once in Daily Balance on the Manila **payment** day and correct payment method.
- Manual staff test: open Today's Receivables, type a customer who borrowed yesterday, select the suggestion, save today's debt, and verify today's record and all-date tab balance. Repeat with a fully paid customer and a brand-new customer.

**Done when:** staff can find past or active customers from the new-debt form, each debt joins only the correct open cycle or creates a fresh one, and the stored approver is the actual signed-in account.
