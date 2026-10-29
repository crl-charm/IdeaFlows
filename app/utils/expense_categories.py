"""Shared category choices; historical custom categories remain readable."""
EXPENSE_CATEGORIES = {
    "supplies": "Supplies", "utilities": "Utilities", "food": "Food",
    "transport": "Transport", "repairs_maintenance": "Repairs / Maintenance",
    "misc": "Miscellaneous", "salaries": "Salaries",
}
SALARY_CATEGORIES = ("salary", "salaries", "payroll")


def expense_category(value):
    value = value.strip().lower() if isinstance(value, str) else ""
    return "salaries" if value in SALARY_CATEGORIES else value
