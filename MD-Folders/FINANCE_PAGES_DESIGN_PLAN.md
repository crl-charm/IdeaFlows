# Finance pages design plan (for review)

Status: proposal only. Do not change the live finance pages until approved.

## What stays the same

- Keep the existing gold, red, yellow, and blue colors. Do not replace the brand palette.
- Keep the sidebar, top bar, current features, data, and buttons.
- Keep the three pages separate: Expenses, Receivables, and Payables.

## What changes visually

1. Give all three pages the same title, summary-card, filter, and table layout.
2. Align the main button with the page title and use consistent spacing.
3. Keep the current card colors, but give cards matching size, padding, and type hierarchy.
4. Make filters compact and easy to scan. Show the selected filter clearly.
5. Use softer table borders, more row breathing room, and clear status badges.
6. When a list is empty, show a short explanation and the relevant action instead of a large blank table.
7. On narrow screens, stack cards and filters and preserve the existing usable table/mobile view.

## Simpler words to review

| Current wording | Suggested wording |
| --- | --- |
| Payables / Supplier Debt Tracker | Bills to Pay |
| Receivables / Debt Tracker | Customer Bills |
| Total Unpaid Payables | Still to Pay |
| Unpaid Count | Unpaid Bills |
| Outstanding Balance | Amount Left |
| Soonest Due Date | Due Date |
| Incurred Date | Date Added |
| Log Expense | Add Expense |
| New Receivable | Add Customer Bill |
| New Payable | Add Supplier Bill |

Use short helper text only where needed. Keep financial amounts and statuses unambiguous: “Still to Pay” is for supplier bills, while “To Collect” is for customer bills.

## Page-specific details

- **Expenses:** Date controls first, total beside or just below them, then the expense list. Empty text: “No expenses for these dates.”
- **Customer Bills:** Show “To Collect” and “Unpaid Bills” above the customer list. Keep paid customers visible when showing all records.
- **Bills to Pay:** Show “Still to Pay” and “Unpaid Bills” above the supplier list. Keep All, Unpaid, Partly Paid, and Paid filters.

## Before implementation

Confirm the wording, especially “Customer Bills” and “Bills to Pay.” The earlier interactive preview explored layout only; its changed colors and longer labels are **not** part of this plan.
