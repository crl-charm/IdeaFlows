"""Admin-only customer statement preview, membership review and PDF download."""
from base64 import b64encode
from io import BytesIO
from pathlib import Path

from flask import Blueprint, current_app, jsonify, render_template, request, send_file, session

from app import db
from app.core.idempotency import idempotent_request
from app.models import ReceivableAccount, ReceivableTab
from app.services.customer_statement_service import CustomerStatementService
from app.services.export_service import ExportService
from app.services.accountant_report_service import AccountantReportService
from app.utils.dates import manila_date
from datetime import datetime

reports_bp = Blueprint("reports", __name__, url_prefix="/admin/reports")
service = CustomerStatementService()


def positive(value, default=None):
    if value in (None, ""):
        return default
    if isinstance(value, bool) or not str(value).isdigit() or not 1 <= int(value) <= 2147483647:
        raise ValueError("Choose a valid account or record reference.")
    return int(value)


@reports_bp.after_request
def private_report(response):
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


@reports_bp.get("")
def reports():
    view = request.args.get("view") or ("customer-statements" if any(
        key in request.args for key in ("account_id", "tab_id", "q", "review_q")) else "monthly")
    if view == "monthly":
        try:
            report = monthly_data()
            return render_template("admin/monthly_accountant_report.html", report=report)
        except ValueError as exc:
            return render_template("admin/monthly_accountant_report.html", error=str(exc), month=request.args.get("month", "")), 400
    if view != "customer-statements":
        return render_template("admin/reports.html", error="Choose Monthly Accountant Report or Customer Statement."), 400
    try:
        search = request.args.get("q", "").strip()
        review_search = request.args.get("review_q", "").strip()
        if max(len(search), len(review_search)) > 100:
            raise ValueError("Search must be at most 100 characters.")
        account_id = positive(request.args.get("account_id"))
        tab_id = positive(request.args.get("tab_id"))
        if tab_id:
            tab = db.session.get(ReceivableTab, tab_id)
            if not tab:
                return render_template("admin/reports.html", error="Customer cycle not found."), 404
            account_id = tab.account_id
        selected = service.build(account_id, request.args.get("attention", "")) if account_id else None
        if account_id and not selected:
            return render_template("admin/reports.html", error="Customer account not found."), 404
        accounts = service.accounts(search, positive(request.args.get("page"), 1))
        account = db.session.get(ReceivableAccount, account_id) if selected else None
        candidates = service.candidates(account, review_search, positive(request.args.get("review_page"), 1)) if account else None
        unassigned = service.unassigned(review_search, positive(request.args.get("unassigned_page"), 1))
        return render_template("admin/reports.html", statement=selected, accounts=accounts,
                               candidates=candidates, unassigned=unassigned, search=search,
                               review_search=review_search)
    except ValueError as exc:
        return render_template("admin/reports.html", error=str(exc)), 400


@reports_bp.post("/api/accounts/<int:account_id>/review")
@idempotent_request("admin-review-receivable-account")
def review_history(account_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(success=False, error="Invalid history review."), 400
    try:
        action = data.get("action")
        if action not in {"confirm", "associate"}:
            raise ValueError("Choose a valid history action.")
        if action == "confirm" and data.get("confirmed") is not True:
            raise ValueError("Confirm that you reviewed this customer's complete recorded history.")
        service.review(account_id, session["user_id"], confirm=action == "confirm",
                       tab_id=positive(data.get("tab_id")), receivable_id=positive(data.get("receivable_id")))
        return jsonify(success=True)
    except ValueError as exc:
        db.session.rollback()
        return jsonify(success=False, error=str(exc)), 400


@reports_bp.get("/api/customer-statements/<int:account_id>")
def preview(account_id):
    try:
        statement = service.build(account_id, request.args.get("attention", ""))
    except ValueError as exc:
        return jsonify(success=False, error=str(exc)), 400
    if not statement:
        return jsonify(success=False, error="Customer account not found."), 404
    return jsonify(success=True, data=statement)


@reports_bp.get("/api/customer-statements/<int:account_id>/pdf")
def customer_pdf(account_id):
    try:
        statement = service.build(account_id, request.args.get("attention", ""))
        if not statement:
            return jsonify(success=False, error="Customer account not found."), 404
        if not statement["can_export"]:
            return jsonify(success=False, error="Review the customer history and resolve balance warnings before exporting."), 409
        image = report_logo()
        pdf = ExportService(db).render_pdf_bytes("admin/customer_statement_pdf.html", statement=statement, logo=image)
    except ValueError as exc:
        return jsonify(success=False, error=str(exc)), 400
    except (RuntimeError, OSError):
        current_app.logger.exception("Customer statement PDF rendering failed")
        return jsonify(success=False, error="Could not create the PDF. Please retry; no financial records were changed."), 503
    filename = f"IdeaFlow-Customer-Statement-{statement['account']['reference']}-{statement['generated_day']}.pdf"
    return send_file(BytesIO(pdf), mimetype="application/pdf", as_attachment=True, download_name=filename)


def report_logo():
    logo = Path(current_app.static_folder) / "css" / "images" / "logo.png"
    return "data:image/png;base64," + b64encode(logo.read_bytes()).decode("ascii")


def monthly_data():
    month = request.args.get("month", manila_date(datetime.utcnow()).strftime("%Y-%m"))
    return AccountantReportService.build(month, session["user_id"])


@reports_bp.get("/api/monthly-accountant")
def monthly_preview():
    try:
        return jsonify(success=True, data=monthly_data())
    except ValueError as exc:
        return jsonify(success=False, error=str(exc)), 400


@reports_bp.get("/api/monthly-accountant/pdf")
def monthly_pdf():
    try:
        report = monthly_data()
        if not report["can_export"]:
            return jsonify(success=False, error="Assign the older salary entries in Admin Expenses before exporting this report."), 409
        pdf = ExportService(db).render_pdf_bytes("admin/monthly_accountant_pdf.html", report=report, logo=report_logo())
    except ValueError as exc:
        return jsonify(success=False, error=str(exc)), 400
    except (RuntimeError, OSError):
        current_app.logger.exception("Monthly accountant PDF rendering failed")
        return jsonify(success=False, error="Could not create the PDF. Please retry; no records were changed."), 503
    return send_file(BytesIO(pdf), mimetype="application/pdf", as_attachment=True,
                     download_name=f"IdeaFlow-Accountant-Report-{report['month']}.pdf")
