"""Monthly recorded costs and work shifts; cash dates remain on the original ledger."""
from collections import defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import and_, or_
from sqlalchemy.orm import selectinload

from app import db
from app.models import Expense, StaffShift, User
from app.repositories.sales_repository import SalesRepository
from app.utils.dates import MANILA_OFFSET, manila_date, month_bounds
from app.utils.expense_categories import EXPENSE_CATEGORIES

ZERO = Decimal("0.00")


def stamp(value):
    return (value + MANILA_OFFSET).strftime("%Y-%m-%d %I:%M %p") if value else "Not recorded"


def elapsed_microseconds(start, end):
    delta = end - start
    return delta.days * 86400000000 + delta.seconds * 1000000 + delta.microseconds


def duration(microseconds):
    seconds = microseconds // 1000000
    return f"{seconds // 3600}h {(seconds % 3600) // 60:02d}m {seconds % 60:02d}s"


class AccountantReportService:
    @staticmethod
    def build(month, prepared_by, *, now=None):
        start, end = month_bounds(month)
        first = datetime.combine(start, time.min) - MANILA_OFFSET
        stop = datetime.combine(end, time.min) - MANILA_OFFSET
        last_day = end - timedelta(days=1)
        now = now or datetime.utcnow()
        preparer = db.session.get(User, prepared_by)
        if not preparer:
            raise ValueError("The preparing admin could not be found. Please log in again.")
        notes, issues = [], []
        if start <= manila_date(now) < end:
            notes.append("This month is still in progress. Totals contain only records available at generation time.")
        elif start > manila_date(now):
            notes.append("A future month is selected. Only entries already recorded for this month are included.")

        # Same void/refund/retained-credit policy as Daily Balance, with exact decimal output.
        live = SalesRepository().daily_ledger(start, last_day, decimal_values=True)
        fields = {"cowork_bill": "cowork_bill", "cafe_bill": "cafe_bill", "discounts": "discounts_total",
                  "cowork_discounts": "cowork_discounts", "cafe_discounts": "cafe_discounts",
                  "checkout_sales": "total_revenue", "refunds": "total_refunds",
                  "reconciliation_difference": "sales_reconciliation_difference"}
        sales = {key: sum((row[field] for row in live.values()), ZERO) for key, field in fields.items()}
        sales["after_refunds"] = sales["checkout_sales"] - sales["refunds"]
        if sales["reconciliation_difference"]:
            notes.append("Some older checkout component amounts do not match their saved sales totals. The reconciliation difference is shown; no missing item breakdown was invented.")
        days = []
        for n in range((end - start).days):
            day = start + timedelta(days=n)
            row = live.get(day, {})
            days.append({"date": day.isoformat(), **{key: row.get(field, ZERO) for key, field in fields.items()}})

        salary_incomplete = and_(Expense.is_salary, Expense.voided_at.is_(None), or_(
            Expense.salary_month.is_(None), Expense.salary_employee_id.is_(None), Expense.salary_employee_name.is_(None)))
        rows = (Expense.query.filter(or_(
            and_(Expense.salary_month >= start, Expense.salary_month < end),
            and_(Expense.expense_date >= start, Expense.expense_date < end),
            and_(Expense.created_at >= first, Expense.created_at < stop),
            and_(Expense.voided_at >= first, Expense.voided_at < stop), salary_incomplete,
        )).options(selectinload(Expense.logged_by_user), selectinload(Expense.voided_by_user))
                .order_by(Expense.expense_date, Expense.id).all())
        salary_groups, categories = {}, defaultdict(lambda: ZERO)
        salary_payments, expenses, payment_history, unassigned = [], [], [], []
        sources = defaultdict(lambda: ZERO)
        total_expenses = salary_total = ZERO
        allocated_here_paid_elsewhere = paid_here_other_salary_month = ZERO
        for row in rows:
            salary = row.is_salary
            complete = bool(row.salary_month and row.salary_employee_id and row.salary_employee_name)
            if salary and complete and row.salary_month.day != 1:
                complete = False
            allocated = row.salary_month if salary else row.expense_date
            in_cost_month = allocated is not None and start <= allocated < end
            in_payment_month = start <= row.expense_date < end
            actor = row.logged_by_user
            item = {"id": row.id, "reference": f"E-{row.id}", "category": "salaries" if salary else row.category,
                    "category_label": "Salaries" if salary else EXPENSE_CATEGORIES.get(row.category, row.category),
                    "description": row.description, "amount": row.amount, "is_salary": salary,
                    "employee_id": row.salary_employee_id if salary else None,
                    "employee": row.salary_employee_name if salary else None,
                    "salary_month": row.salary_month.strftime("%Y-%m") if row.salary_month else None,
                    "cost_month": allocated.strftime("%Y-%m") if allocated else "Unassigned",
                    "payment_date": row.expense_date.isoformat(), "recorded_at": stamp(row.created_at),
                    "posting_date": (manila_date(row.created_at) if row.funding_source and row.created_at else row.expense_date).isoformat(),
                    "method": (row.payment_method or "Unknown").upper(),
                    "source": ("Owner paid directly" if row.payment_method == "cash" and row.funding_source == "external" else
                               "Owner / external funds" if row.funding_source == "external" else
                               f"{row.cash_box.title()} cash box" if row.cash_box else
                               "Business funds" if row.funding_source else "Older record: funding unknown"),
                    "recorded_by": (actor.full_name or actor.username) if actor else "Not recorded",
                    "voided_at": stamp(row.voided_at) if row.voided_at else None,
                    "void_reason": row.void_reason, "voided_by": row.voided_by_user.username if row.voided_by_user else None,
                    "original_category": row.salary_original_category,
                    "classified_at": stamp(row.salary_assigned_at) if row.salary_assigned_at else None,
                    "classified_by": row.salary_assigned_by}
            if salary and not complete and not row.voided_at:
                unassigned.append(item)
                continue
            payment_history.append(item)
            if row.voided_at or not in_cost_month:
                if salary and not row.voided_at and in_payment_month:
                    paid_here_other_salary_month += row.amount
                continue
            total_expenses += row.amount
            categories[item["category_label"]] += row.amount
            sources[row.funding_source or "unknown"] += row.amount
            if salary:
                salary_total += row.amount
                salary_payments.append(item)
                if not in_payment_month:
                    allocated_here_paid_elsewhere += row.amount
                group = salary_groups.setdefault(row.salary_employee_id, {
                    "employee_id": row.salary_employee_id, "name": row.salary_employee_name,
                    "total": ZERO, "payments": [],
                })
                group["total"] += row.amount
                group["payments"].append(item)
            else:
                expenses.append(item)
        if unassigned:
            issues.append("Older salary entries need an employee and salary month. Open Admin Expenses, choose Show All, then Classify salary. They are excluded from cost totals until assigned; a final PDF is blocked.")
        posted_expenses = sum((row["total_expenses"] for row in live.values()), ZERO)
        notes.append("Salaries are already included in Total Expenses. Recorded payments are not an automatic payroll, gross-pay, tax or profit calculation.")
        notes.append("Cost month, entered payment date and actual posting date can differ. Posted expense totals include all funding sources; owner/external-funded costs are not business cash outflows. Daily Balance keeps the posting/reversal history; supplier payments, owner reimbursements and withdrawals are not added again as operating expenses.")

        shifts = (StaffShift.query.filter(StaffShift.time_in < stop, or_(
            StaffShift.time_in >= first, StaffShift.time_out > first, StaffShift.time_out.is_(None)))
                  .options(selectinload(StaffShift.user)).order_by(StaffShift.time_in, StaffShift.id).all())
        employees = {}
        attendance_rows = []
        for shift in shifts:
            person = shift.user
            name = (person.full_name or person.username) if person else f"Employee #{shift.user_id}"
            group = employees.setdefault(shift.user_id, {"employee_id": shift.user_id, "name": name,
                                                       "shifts": [], "intervals": [], "incomplete": 0,
                                                       "overlap": False, "invalid": 0})
            item = {"reference": f"S-{shift.id}", "employee_id": shift.user_id, "employee": name,
                    "time_in": stamp(shift.time_in), "time_out": stamp(shift.time_out) if shift.time_out else None,
                    "role": shift.shift_role, "recorded_at": stamp(shift.recorded_at),
                    "out_recorded_at": stamp(shift.time_out_recorded_at) if shift.time_out_recorded_at else None,
                    "duration": "Not counted", "status": "Incomplete / Missing Time Out"}
            if shift.time_out is None:
                group["incomplete"] += 1
                if shift.time_in < first:
                    item["status"] += " (started before this month)"
            elif shift.time_out <= shift.time_in:
                item["status"] = "Invalid interval: review Time In/Out"
                group["invalid"] += 1
            else:
                beginning, ending = max(first, shift.time_in), min(stop, shift.time_out)
                item["duration"] = duration(elapsed_microseconds(beginning, ending))
                item["status"] = "Completed" if beginning == shift.time_in and ending == shift.time_out else "Completed / month portion only"
                group["intervals"].append((beginning, ending))
            group["shifts"].append(item)
            attendance_rows.append(item)
        total_time = incomplete = invalid = overlapping = 0
        for group in employees.values():
            merged = []
            for beginning, ending in sorted(group.pop("intervals")):
                if merged and beginning < merged[-1][1]:
                    group["overlap"] = True
                if merged and beginning <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(ending, merged[-1][1]))
                else:
                    merged.append((beginning, ending))
            counted = sum(elapsed_microseconds(beginning, ending) for beginning, ending in merged)
            group["duration"] = duration(counted)
            group["hours"] = (Decimal(counted) / Decimal("3600000000")).quantize(Decimal("0.01"))
            total_time += counted
            incomplete += group["incomplete"]
            invalid += group["invalid"]
            overlapping += int(group["overlap"])
        if incomplete or invalid or overlapping:
            notes.append("Attendance needs review: incomplete/invalid shifts are not counted; overlapping intervals count once per employee. No absent, late, break, or overtime assumptions are made.")
        return {
            "month": month, "month_label": start.strftime("%B %Y"), "start_date": start.isoformat(),
            "end_date": last_day.isoformat(), "generated_at": stamp(now),
            "prepared_by": preparer.full_name or preparer.username,
            "sales": sales, "sales_days": days, "salary_total": salary_total,
            "total_expenses": total_expenses, "other_expenses": total_expenses - salary_total,
            "expense_categories": [{"category": name, "amount": value} for name, value in sorted(categories.items())],
            "expense_sources": dict(sources), "expenses": expenses,
            "salary_employees": sorted(salary_groups.values(), key=lambda row: (row["name"], row["employee_id"])),
            "salary_payments": salary_payments, "expense_payment_history": payment_history,
            "unassigned_salaries": unassigned,
            "reconciliation": {"allocated_here_paid_elsewhere": allocated_here_paid_elsewhere,
                               "paid_here_other_salary_month": paid_here_other_salary_month,
                               "net_posted_expenses": posted_expenses,
                               "cost_minus_posted": total_expenses - posted_expenses},
            "attendance": {"employees": sorted(employees.values(), key=lambda row: (row["name"], row["employee_id"])),
                           "rows": attendance_rows, "employee_count": len(employees),
                           "duration": duration(total_time), "hours": (Decimal(total_time) / Decimal("3600000000")).quantize(Decimal("0.01")),
                           "incomplete": incomplete, "invalid": invalid, "overlap_count": overlapping},
            "notes": notes, "issues": issues, "can_export": not issues,
        }
