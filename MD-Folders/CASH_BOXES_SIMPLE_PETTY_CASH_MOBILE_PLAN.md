# Cash Boxes: simple petty cash entry and mobile history

**Status: implemented locally — October 25, 2026.** Production deployment remains separate.

## Goal

Make Cash Boxes easy for staff and admin to use: enter petty cash, save it once, and see who recorded it in readable history. Every form and history entry must fit a phone screen without sideways scrolling.

## Design decisions

- Make **Add petty cash** the main action. Remove the top-level Action dropdown from the normal workflow.
- Show one main balance: **Petty cash available**. Keep the explanation short: “Cash remaining from recorded petty cash entries and spending. Unused cash carries forward.”
- Show only the amount and the required owner repayment choice in the main form. Default the date to today in Asia/Manila and get the actor from the signed-in account.
- Keep date changes and notes under **Change date or add a note**.
- Put cash withdrawals under a collapsed **Other actions** section. This preserves the previously requested withdrawal workflow without making it part of adding petty cash.
- Replace the history table with expandable cards at every screen size. Full audit details stay available inside each card.
- Keep the permanent Cash Boxes button already added to Daily Balance and the shared navigation shortcut.

## What currently causes the clutter

- `app/templates/partials/cash_boxes.html` has separate first-entry and later-entry forms, an Action dropdown, withdrawal fields, correction fields, and a nine-column history table in one modal.
- `static/js/cash-boxes.js::balances()` displays Petty cash, Customer cash, and Total held together. These compete with the simple petty cash action the user wants.
- The history filter puts two dates and two buttons on one unwrapped row. The table requires horizontal scrolling on phones.
- The existing history endpoint returns opening entries, owner top-ups, withdrawals, and corrections. It does not return every checkout, collection, expense, or supplier payment. The new layout must not describe that list as a complete transaction ledger.

## Proposed default view

```text
Cash Boxes                                      Close

Petty cash available                         ₱300.00
Unused petty cash carries forward.

Add petty cash
Amount (₱)                                  [       ]
Does the business need to pay the owner back?
[Choose Yes or No                              v]
  Yes — add the amount owed to Payables
  No — no repayment is needed

> Change date or add a note
[ Add petty cash ]

Cash entry history
[Today] [All history] [Choose dates]

> +₱300.00  Petty cash added
  Oct 25, 2026 · recorded by staff name

> Other actions
```

The form starts with an empty amount and no repayment choice selected. Do not silently default a new entry to creating an owner debt or to waiving repayment.

## Add petty cash flow

1. Open Cash Boxes. Load the latest petty cash balance and history, showing a loading state until the server responds.
2. Enter an amount and choose whether the owner must be repaid. The normal date is today's Manila date; the signed-in actor is automatic and cannot be typed into the form.
3. Optionally open **Change date or add a note**. Show the selected date visibly when it differs from today. Keep the existing permitted date range and server validation.
4. Press **Add petty cash** once. Reuse `runButtonAction`, the existing request key, server validation, and error handling. A normal top-up does not need another confirmation dialog.
5. After the server confirms success, show the amount added and refreshed petty balance, clear the amount/note/repayment choice, refresh Daily Balance, and display the saved entry in history. For a backdated entry, select its effective date so the user can immediately review it.
6. Keep entered values available after a failed request. Show an inline explanation; never show an unverified success or turn a failed balance request into ₱0.

Use the same visible form for first-time and later additions. On first use, call the existing `/api/cash-boxes/opening` path, which establishes zero baselines and records the actual first top-up. On subsequent use, call `/api/cash-boxes/entries`. Do not recreate an existing opening baseline or ask users to enter customer cash during the main petty cash flow.

## History without side scrolling

- Default to **Today**, with **All history** and **Choose dates** available. The date range opens a small responsive form; inputs and buttons stack on narrow screens.
- Show newest effective dates first, preserving the existing order within each date.
- Each closed card shows its plain action label, signed amount, effective Manila date, recorded-by name, and a visible status such as **Corrected** when applicable.
- Expanding a card reveals the exact recorded time in Manila, cash box, note, recipient, owner repayment choice for a top-up, entry number, and recorded before/after balances when available.
- Label before/after values as balances **when the entry was recorded**. Later backdated entries can change the recomputed daily balance; do not present old posting snapshots as a fresh cash count.
- Show linked original, reversal, and replacement entry numbers. An original corrected entry remains readable, with its linked correction visible. Do not rely on color alone to explain an addition, withdrawal, or correction.
- Use readable action labels: **Petty cash added**, **Cash taken out**, **Entry correction**, and **Tracking started** instead of raw database names.
- Give zero opening records a compact Tracking started card with details available. Preserve older customer-box events in history with their cash box clearly labeled.
- Include a short scope note: this history contains cash additions, withdrawals, and corrections; the source histories in Checkout Records, Receivables, Expenses, and Payables explain their own payments.

Use native `<details>/<summary>` or the existing accessible expansion pattern. Keep buttons such as **Correct entry** inside the expanded details, rather than turning the whole card into a money action.

## Other actions and corrections

- **Record cash taken out** stays collapsed by default and uses its own form. Choose the box, amount, recipient, purpose, and Manila date. Show the selected box's balance only within that workflow; avoid Customer cash and Total held summaries above the main petty cash form.
- Preserve the existing owner-debt repayment guard. A repayment of a recorded owner payable uses Payables, so it reduces the debt and cash once.
- Keep a short inline withdrawal confirmation with box, amount, and expected remaining balance. Keep the existing negative-balance warning.
- **Correct entry** opens an inline correction section from that history card. Require a reason, preserve the original, and show the linked reversal. Keep the replacement amount field only for an opening-count correction.
- Hidden or collapsed withdrawal fields must not block the petty cash form with unrelated required-field validation. Canceling a correction returns focus to the initiating control.

## Mobile and accessibility rules

- Use Bootstrap's existing responsive layout and scoped modal styles; add no UI library.
- At phone width, use a full-width modal with comfortable margins or Bootstrap's existing small-screen fullscreen option. Allow ordinary vertical scrolling inside the dialog.
- Remove the history table and its `.table-responsive` wrapper. Do not hide overflowing content with `overflow-x: hidden` as a substitute for fitting it.
- Give the modal, forms, filter controls, cards, and their children `min-width: 0` where needed. Wrap long names, recipients, and notes with `overflow-wrap` so no entry forces a wider viewport.
- Keep amount labels, dates, button text, and focus outlines readable at 320 px. Stack controls instead of squeezing several columns onto a small screen.
- Retain the dialog's accessible title, Close button, focus behavior, labeled inputs, visible errors, and announced save feedback. All expansion and correction controls must work by keyboard.

## Implementation boundaries and files

1. **`app/templates/partials/cash_boxes.html`:** simplify the default form, collapse Other actions, replace the history table/filter row, and add scoped responsive layout where needed.
2. **`static/js/cash-boxes.js`:** render the simpler balance and expandable history, route the shared form to the existing first/subsequent entry APIs, preserve retries/corrections, and keep `cash-boxes-updated` refresh behavior. Escape all user-entered history text as today.
3. **`app/templates/layout.html`:** verify shared modal loading and use the repository's existing asset-versioning pattern if the changed script/markup requires a cache update.
4. **Existing cash service/routes:** reuse their current payloads and authorization. No schema migration or calculation change is expected for this presentation task.
5. **`tests/test_cash_boxes.py` and existing finance checks:** rerun relevant cash/owner-debt reconciliation coverage. Add a new money test only if implementation changes an actual money behavior.

This plan covers the shared modal. The broader Daily Balance cards/reports/export redesign remains in [DAILY_BALANCE_NO_SIDE_SCROLL_REDESIGN_PLAN.md](DAILY_BALANCE_NO_SIDE_SCROLL_REDESIGN_PLAN.md).

## Financial rules to preserve

- Every addition, withdrawal, and correction keeps the amount, cash box, actor, actual recording time, effective Manila date, and linked before/after or reversal information.
- An owner top-up increases petty cash and contributes no checkout revenue. A repayable top-up creates one linked owner payable; later reimbursement does not become another expense.
- Cash balances carry forward at midnight. Daily movement and dated views continue to use the same Manila boundaries as Daily Balance.
- A retry creates no duplicate cash entry or owner debt. Correcting an entry retains history and existing snapshot differences.
- Staff and admin retain their current permissions. Expired login, authorization, and server failures remain explicit errors.

## Verification and acceptance

1. First-time and later additions both use the same short form. Test a ₱300 addition with each repayment choice; verify one history entry, the correct petty balance, and the matching Daily Balance/Payables effect.
2. Check duplicate taps, retry after a network failure, invalid amounts, missing repayment choice, and a permitted backdate. Confirm successful saves appear in the selected history view.
3. Check withdrawal and correction from Other actions, including recipient/purpose, correction reason, reversal links, and the opening correction field. Existing audit and idempotency tests must continue to pass.
4. Test staff and admin on phone widths of 320/375 px, tablet width, and desktop. Open long notes and history details; the modal body and expanded cards must fit without horizontal scrolling or clipped amounts.
5. Verify keyboard expansion, focus on errors, close/cancel behavior, loading/empty/error states, and working access from both the navigation shortcut and Daily Balance button.
6. Compare representative cash history and Daily Balance figures before/after. This layout change must produce the same financial results.

**Ready when:** staff can open Cash Boxes, enter the amount and repayment choice, save once, and immediately review the dated actor-attributed entry on a phone without scrolling sideways.

**Deployment:** prepare and verify locally. Production deployment remains a separate user-requested step.

## Implementation and verification

- One amount-and-repayment form now handles first-time and subsequent petty cash additions. Manila date and actor are automatic; date/note remain optional details. Only Petty cash available appears above it.
- History uses expandable cards with Today/All/Choose dates filters, exact recorded time, effective date, actor, method, repayment choice, notes, posting balances, and correction/replacement links. Backdated saves select their own history date.
- Withdrawals stay under Other actions, with a separate form, owner-payable guard, inline amount/box/remaining-balance confirmation, and negative warning. Corrections require a reason and preserve the original; cancel restores focus.
- Preserved the previously dropped first-entry note. Cash mutations now replay matching durable record keys under the existing cash lock, instead of a temporary duplicate-request rejection. Changed payloads or actors cannot reuse another entry's key. No schema or cash calculation changes.
- Automated checks: 42 cash/ledger/expense/payable tests passed. A second 13-test run covering requests, idempotency, and opening-correction replay also passed (54 distinct tests across both runs). JavaScript syntax and Jinja parsing passed.
- Browser checks used synthetic in-memory records for staff and admin: first/later additions, both repayment choices, a committed save with simulated failed response followed by close/reopen/retry, backdating, required choices/reasons, withdrawals, opening corrections, audit links, date errors, and keyboard cancel/expansion. Saved records reconciled to Daily Balance with no duplicate top-up or payable.
- At 320/375/768/1280 px, expanded long notes, history cards, dates, and withdrawal controls had no horizontal overflow for either role. A failed balance request showed an unavailable value, explicit error, disabled saving, and a refresh action rather than zero. Closing the dialog returned keyboard focus to the launch button.
- Local sample screenshot: `instance/cash-modal-preview/cash-boxes-mobile.png`. The disposable preview server was stopped after verification; no VPS or production records were changed.
