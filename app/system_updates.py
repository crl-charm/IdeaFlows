"""Published patch notes with fixed dates; code edits never generate or rewrite them."""

from datetime import date

SYSTEM_UPDATES = (
    {
        "id": "2026-10-30-customer-visit-filters",
        "date": "2026-10-30",
        "title": "Customer visits by day or month",
        "summary": "See today's customer visits, yesterday's visits or a chosen month without losing older records.",
        "changed": "The Customer visits card starts with Today in Manila time. Each visit counts separately, including repeat visits, food-only visits and started Boardroom bookings. Cancelled check-ins are excluded. A new day changes the view, not the saved history.",
        "location": "Admin Panel → Customer visits → Customer Records",
        "steps": (
            "Open Admin Panel and tap the Customer visits card.",
            "Choose Today, Yesterday or a month and year. The current month shows visits up to now.",
            "Choose Show All to review older visits. The card total follows the selected period.",
        ),
        "paths": {"admin": "/admin"},
    },
    {
        "id": "2026-10-30-staff-attendance-filters",
        "date": "2026-10-30",
        "title": "Staff Time In/Out by day or month",
        "summary": "Find staff attendance events for Today, Yesterday or a selected month.",
        "changed": "Staff Time In/Out now has its own date filters using each event's Manila date. Staff Members, Active / Online and Offline still show the current staff account counts.",
        "location": "Admin Panel → Staff Members → Staff Time In/Out",
        "steps": (
            "Open Admin Panel and tap the Staff Members card.",
            "Choose Today, Yesterday or a month and year to review the attendance events.",
            "Choose Show All for the full saved history. These filters do not change Customer Records.",
        ),
        "paths": {"admin": "/admin"},
    },
    {
        "id": "2026-10-30-checkout-records-layout",
        "date": "2026-10-30",
        "title": "Checkout records fit your screen",
        "summary": "Read each customer's bill, payment and checkout actions without scrolling sideways.",
        "changed": "Checkout Records uses cards that fit desktop, tablet and phone screens. The time and food bills, discounts, payment details, status and available actions stay together. Billing amounts and saved records are unchanged.",
        "location": "Checkout Records",
        "steps": (
            "Open Checkout Records and use the existing date or search filters to find a checkout.",
            "Read the customer's card for the full bill and payment breakdown.",
            "Use the available Details, Time history or void controls as before. Use Load older for more records.",
        ),
        "paths": {"admin": "/checkout-records", "staff": "/checkout-records"},
    },
    {
        "id": "2026-10-29-monthly-accountant",
        "date": "2026-10-29",
        "title": "Monthly accountant PDF",
        "summary": "Export sales, salaries, expenses and employee attendance in one monthly file.",
        "changed": "The monthly report brings these four sections together. Salaries are included in Total Expenses once.",
        "location": "Reports & Exports → Monthly Accountant Report",
        "steps": (
            "Record salary payments in Expenses → Salaries, choosing the employee and salary month.",
            "Choose the report month and tap Review / Refresh.",
            "Review the sections and resolve any older salary records marked for review.",
            "Tap Export Accountant PDF and give the downloaded file to the accountant.",
        ),
        "paths": {"admin": "/admin/reports?view=monthly"},
    },
    {
        "id": "2026-10-29-customer-statement",
        "date": "2026-10-29",
        "title": "Customer statement PDF",
        "summary": "Give a receivables customer a statement showing their saved purchases, payments and balance.",
        "changed": "Each customer account has its own statement, including saved food details and payment history. Older descriptions are preserved.",
        "location": "Reports & Exports → Customer Statement",
        "steps": (
            "Search for and select the receivables customer or building account.",
            "Review the recorded history and any records needing account confirmation.",
            "Tap Export Customer Statement PDF and give the file to that customer.",
        ),
        "paths": {"admin": "/admin/reports?view=customer-statements"},
    },
    {
        "id": "2026-10-29-salary-expenses",
        "date": "2026-10-29",
        "title": "Record salaries by employee and month",
        "summary": "Choose whose salary was paid and which month it belongs to.",
        "changed": "Salary month and payment date are separate. An October salary paid in November stays in October's salary costs, with its payment date shown separately.",
        "location": "Expenses → Log Expense / Salary → Salaries",
        "steps": (
            "Choose Salaries, the employee and the salary month.",
            "Enter the amount, salary payment date, payment method and cash source when needed.",
            "Add an optional note and save. Record another release as a separate payment.",
        ),
        "paths": {"admin": "/admin/expenses"},
    },
    {
        "id": "2026-10-29-repairs-maintenance",
        "date": "2026-10-29",
        "title": "Repairs / Maintenance expense category",
        "summary": "Keep repair and maintenance spending together under its own category.",
        "changed": "Use Repairs / Maintenance for costs such as an aircon repair. These remain ordinary expenses.",
        "location": "Expenses → Log Expense → Repairs / Maintenance",
        "steps": (
            "Open the expense form and choose Repairs / Maintenance.",
            "Describe the work and enter the amount, expense date and payment details.",
            "Save the expense. It will appear in expense history and the relevant totals.",
        ),
        "paths": {"admin": "/admin/expenses", "staff": "/expenses-view"},
    },
    {
        "id": "2026-10-29-late-customer-checkin",
        "date": "2026-10-29",
        "title": "Late customer check-in",
        "summary": "Use a customer's actual arrival time when their Regular or Premium check-in was recorded late.",
        "changed": "An earlier arrival today in Manila time can start the bill correctly. Normal check-in still uses the current time.",
        "location": "Dashboard → + → Late Customer Check-in",
        "steps": (
            "Tap + and enter the customer details and Regular or Premium space.",
            "Tap Late Customer Check-in and select the actual arrival time earlier today in Manila time.",
            "Review the time and tap Check In Customer. The visit's Time history shows when it was recorded.",
        ),
        "paths": {"admin": "/dashboard", "staff": "/dashboard"},
    },
    {
        "id": "2026-10-29-pause-customer-time",
        "date": "2026-10-29",
        "title": "Pause and resume customer time",
        "summary": "Pause a Regular or Premium customer's time charge while keeping their food orders available.",
        "changed": "Pausing stops billable time. The customer stays checked in and still occupies their seat; resuming continues the same visit.",
        "location": "Dashboard → Customer actions → Pause time / Resume time",
        "steps": (
            "Find the Regular or Premium customer and tap Pause time, then confirm.",
            "Add or view food orders as usual while the time bill is paused.",
            "Tap Resume time and confirm when billing should continue. Time history keeps the actions.",
        ),
        "paths": {"admin": "/dashboard", "staff": "/dashboard"},
    },
)


def updates_for(role):
    notes = []
    for update in SYSTEM_UPDATES:
        if role in update["paths"]:
            note = update.copy()
            note["url"] = note.pop("paths")[role]
            released_on = date.fromisoformat(note["date"])
            note["date_label"] = f"{released_on:%B} {released_on.day}, {released_on.year}"
            notes.append(note)
    return notes
