from __future__ import annotations

import csv
from datetime import date, datetime
from io import BytesIO, StringIO
from typing import Any

from flask import Response, send_file
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from app.services.export_service import ExportService


class DailyBalanceExportService(ExportService):
    """CSV, PDF, and Excel exports for daily sales balance reports."""

    PDF_TEMPLATE = "admin/daily_balance_report_pdf.html"
    METHODS = ("cash", "gcash", "bdo", "bpi", "queenbank", "unclassified")
    FLOWS = ("checkout", "collection", "adjustment_income", "expense", "external_expense",
             "expense_paid", "expense_void", "payable", "external_payable", "payable_paid",
             "adjustment_expense", "refund", "credit_received", "credit_applied")

    @staticmethod
    def _period_label(reports: list[dict[str, Any]]) -> str:
        if not reports:
            return ""
        return f"{reports[-1]['report_date']} to {reports[0]['report_date']}"

    @staticmethod
    def _payment_totals(reports: list[dict[str, Any]]) -> dict[str, float | int]:
        return {
            "total_cash": sum(r.get("cash_total", 0) for r in reports),
            "total_gcash": sum(r.get("gcash_total", 0) for r in reports),
            "total_bdo": sum(r.get("bdo_total", 0) for r in reports),
            "total_bpi": sum(r.get("bpi_total", 0) for r in reports),
            "total_queenbank": sum(r.get("queenbank_total", 0) for r in reports),
            "cash_count": sum(r.get("cash_count", 0) for r in reports),
            "gcash_count": sum(r.get("gcash_count", 0) for r in reports),
            "bdo_count": sum(r.get("bdo_count", 0) for r in reports),
            "bpi_count": sum(r.get("bpi_count", 0) for r in reports),
            "queenbank_count": sum(r.get("queenbank_count", 0) for r in reports),
        }

    @staticmethod
    def _method_rows(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = []
        for method in DailyBalanceExportService.METHODS:
            values = {flow: sum(r.get(f"{flow}_methods", {}).get(method, 0) for r in reports)
                      for flow in DailyBalanceExportService.FLOWS}
            if method == "unclassified" and not any(values.values()):
                continue
            net = (
                values["checkout"] - values.get("credit_applied", 0) + values.get("credit_received", 0)
                + values["collection"] + values["adjustment_income"]
                - values["expense"] - values["payable"] - values["adjustment_expense"]
                - values.get("refund", 0)
            )
            rows.append({"method": method, **values, "net": net})
        return rows

    def build_pdf_context(
        self,
        reports: list[dict[str, Any]],
        soft_entries: list[dict[str, Any]],
    ) -> dict[str, Any]:
        payments = self._payment_totals(reports)
        return {
            "reports": reports,
            "soft_entries": soft_entries,
            "total_revenue": sum(r["total_revenue"] for r in reports),
            "cowork_bill": sum(r.get("cowork_bill", 0) for r in reports),
            "cafe_bill": sum(r.get("cafe_bill", 0) for r in reports),
            "discounts_total": sum(r.get("discounts_total", 0) for r in reports),
            "sales_reconciliation_difference": sum(r.get("sales_reconciliation_difference", 0) for r in reports),
            "total_refunds": sum(r.get("total_refunds", 0) for r in reports),
            "total_expenses": sum(r["total_expenses"] for r in reports),
            "total_business_expenses": sum(r.get("total_business_expenses", 0) for r in reports),
            "total_external_expenses": sum(r.get("total_external_expenses", 0) for r in reports),
            "total_collections": sum(r.get("total_collections", 0) for r in reports),
            "total_payables_paid": sum(r.get("total_payables_paid", 0) for r in reports),
            "total_business_payables_paid": sum(r.get("total_business_payables_paid", 0) for r in reports),
            "total_external_payables_paid": sum(r.get("total_external_payables_paid", 0) for r in reports),
            "total_other_income": sum(r.get("total_other_income", 0) for r in reports),
            "total_budget_spend": sum(r.get("total_budget_spend", 0) for r in reports),
            "net_balance": sum(r["net_balance"] for r in reports),
            "method_rows": self._method_rows(reports),
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "period_label": self._period_label(reports),
            **payments,
        }

    def export_pdf(
        self,
        reports: list[dict[str, Any]],
        soft_entries: list[dict[str, Any]],
    ) -> Response:
        pdf_bytes = self.render_pdf_bytes(
            self.PDF_TEMPLATE,
            **self.build_pdf_context(reports, soft_entries),
        )
        filename = f"daily_sales_balance_{date.today().isoformat()}.pdf"
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    @staticmethod
    def export_csv(reports: list[dict[str, Any]]):
        output = StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "Report Date",
                "Cowork Bill",
                "Cafe Bill",
                "Discounts",
                "Checkout Sales",
                "Refunds Paid",
                "Sales Reconciliation Difference",
                "Debt Collected",
                "Cash",
                "GCash",
                "BDO",
                "BPI",
                "QueenBank",
                "Unclassified Checkout",
                "Total Expenses",
                "Business Expenses",
                "External-funded Expenses",
                "Supplier Paid",
                "Business Supplier Paid",
                "External-funded Supplier Paid",
                "Other Income",
                "Budget Spent",
                "Net Balance",
                "Total Orders",
                "Timed Sessions",
                "Generated By",
                "Generated At",
                "Notes",
            ] + [f"{flow.title()} {method.title()}" for flow in DailyBalanceExportService.FLOWS
                 for method in DailyBalanceExportService.METHODS],
        )
        writer.writeheader()
        for report in reports:
            values = {
                "Report Date": report["report_date"],
                "Cowork Bill": f"₱{report.get('cowork_bill', 0):.2f}",
                "Cafe Bill": f"₱{report.get('cafe_bill', 0):.2f}",
                "Discounts": f"₱{report.get('discounts_total', 0):.2f}",
                "Checkout Sales": f"₱{report['total_revenue']:.2f}",
                "Refunds Paid": f"₱{report.get('total_refunds', 0):.2f}",
                "Sales Reconciliation Difference": f"₱{report.get('sales_reconciliation_difference', 0):.2f}",
                "Debt Collected": f"₱{report.get('total_collections', 0):.2f}",
                "Cash": f"₱{report.get('cash_total', 0):.2f}",
                "GCash": f"₱{report.get('gcash_total', 0):.2f}",
                "BDO": f"₱{report.get('bdo_total', 0):.2f}",
                "BPI": f"₱{report.get('bpi_total', 0):.2f}",
                "QueenBank": f"₱{report.get('queenbank_total', 0):.2f}",
                "Unclassified Checkout": f"₱{report.get('unclassified_total', 0):.2f}",
                "Total Expenses": f"₱{report['total_expenses']:.2f}",
                "Business Expenses": f"₱{report.get('total_business_expenses', 0):.2f}",
                "External-funded Expenses": f"₱{report.get('total_external_expenses', 0):.2f}",
                "Supplier Paid": f"₱{report.get('total_payables_paid', 0):.2f}",
                "Business Supplier Paid": f"₱{report.get('total_business_payables_paid', 0):.2f}",
                "External-funded Supplier Paid": f"₱{report.get('total_external_payables_paid', 0):.2f}",
                "Other Income": f"₱{report.get('total_other_income', 0):.2f}",
                "Budget Spent": f"₱{report.get('total_budget_spend', 0):.2f}",
                "Net Balance": f"₱{report['net_balance']:.2f}",
                "Total Orders": report["total_orders"],
                "Timed Sessions": report["total_sessions"],
                "Generated By": report["generated_by"],
                "Generated At": report.get("generated_at") or "",
                "Notes": report["notes"] or "",
            }
            values.update({f"{flow.title()} {method.title()}": f"₱{report.get(f'{flow}_methods', {}).get(method, 0):.2f}"
                           for flow in DailyBalanceExportService.FLOWS
                           for method in DailyBalanceExportService.METHODS})
            writer.writerow(values)
        output.seek(0)
        bytes_output = BytesIO(output.getvalue().encode("utf-8"))
        return send_file(
            bytes_output,
            mimetype="text/csv",
            as_attachment=True,
            download_name="sales_report.csv",
        )

    def export_excel(self, reports: list[dict[str, Any]]):
        wb = Workbook()
        wb.remove(wb.active)

        ws_summary = wb.create_sheet("Summary")
        self._create_summary_sheet(ws_summary, reports)

        ws_details = wb.create_sheet("Daily Reports")
        self._create_details_sheet(ws_details, reports)

        ws_methods = wb.create_sheet("Payment Methods")
        ws_methods.append(["Date", "Flow", *self.METHODS])
        for report in reports:
            for flow in self.FLOWS:
                ws_methods.append([report["report_date"], flow,
                                   *(report.get(f"{flow}_methods", {}).get(m, 0) for m in self.METHODS)])

        if len(reports) >= 2:
            ws_comparison = wb.create_sheet("Period Comparison")
            self._create_comparison_sheet(ws_comparison, reports)

        ws_trends = wb.create_sheet("Trends")
        self._create_trends_sheet(ws_trends, reports)

        bytes_output = BytesIO()
        wb.save(bytes_output)
        bytes_output.seek(0)
        return send_file(
            bytes_output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"sales_report_{date.today().isoformat()}.xlsx",
        )

    @staticmethod
    def _create_summary_sheet(ws, reports: list[dict[str, Any]]) -> None:
        ws["A1"] = "SALES SUMMARY REPORT"
        ws["A1"].font = Font(bold=True, size=14)
        ws.merge_cells("A1:H1")

        ws["A3"] = "Key Metrics"
        ws["A3"].font = Font(bold=True, size=11)

        total_revenue = sum(r["total_revenue"] for r in reports)
        total_expenses = sum(r["total_expenses"] for r in reports)
        total_net = sum(r["net_balance"] for r in reports)
        total_cash = sum(r.get("cash_total", 0) for r in reports)
        total_gcash = sum(r.get("gcash_total", 0) for r in reports)
        total_bdo = sum(r.get("bdo_total", 0) for r in reports)
        total_bpi = sum(r.get("bpi_total", 0) for r in reports)
        total_queenbank = sum(r.get("queenbank_total", 0) for r in reports)

        ws["A4"] = "Checkout Sales:"
        ws["B4"] = total_revenue
        ws["B4"].number_format = "₱#,##0.00"

        ws["A5"] = "Cash Payments:"
        ws["B5"] = total_cash
        ws["B5"].number_format = "₱#,##0.00"

        ws["A6"] = "GCash Payments:"
        ws["B6"] = total_gcash
        ws["B6"].number_format = "₱#,##0.00"

        ws["A7"] = "BDO Payments:"
        ws["B7"] = total_bdo
        ws["B7"].number_format = "₱#,##0.00"

        ws["A8"] = "BPI Payments:"
        ws["B8"] = total_bpi
        ws["B8"].number_format = "₱#,##0.00"

        ws["A9"] = "Total Expenses:"
        ws["B9"] = total_expenses
        ws["B9"].number_format = "₱#,##0.00"

        ws["A10"] = "Net Balance:"
        ws["B10"] = total_net
        ws["B10"].number_format = "₱#,##0.00"
        ws["B10"].font = Font(bold=True, color="008000")

        ws["A11"] = "Total Orders:"
        ws["B11"] = sum(r["total_orders"] for r in reports)

        ws["A12"] = "Timed Sessions:"
        ws["B12"] = sum(r["total_sessions"] for r in reports)

        ws["A15"] = "QueenBank Payments:"
        ws["B15"] = total_queenbank
        ws["B15"].number_format = "₱#,##0.00"

        ws["A13"] = "Period:"
        if reports:
            ws["B13"] = DailyBalanceExportService._period_label(reports)
        ws["A16"] = "Debt Collected:"
        ws["B16"] = sum(r.get("total_collections", 0) for r in reports)
        ws["A17"] = "Supplier Paid:"
        ws["B17"] = sum(r.get("total_payables_paid", 0) for r in reports)
        ws["A18"] = "Other Income:"
        ws["B18"] = sum(r.get("total_other_income", 0) for r in reports)
        ws["A19"] = "Budget Spent:"
        ws["B19"] = sum(r.get("total_budget_spend", 0) for r in reports)
        ws["A20"] = "Business Expenses:"
        ws["B20"] = sum(r.get("total_business_expenses", 0) for r in reports)
        ws["A21"] = "External-funded Expenses:"
        ws["B21"] = sum(r.get("total_external_expenses", 0) for r in reports)
        ws["A22"] = "Business Supplier Paid:"
        ws["B22"] = sum(r.get("total_business_payables_paid", 0) for r in reports)
        ws["A23"] = "External-funded Supplier Paid:"
        ws["B23"] = sum(r.get("total_external_payables_paid", 0) for r in reports)
        for row, label, key in (
            (24, "Cowork Bill:", "cowork_bill"),
            (25, "Cafe Bill:", "cafe_bill"),
            (26, "Discounts:", "discounts_total"),
            (27, "Refunds Paid:", "total_refunds"),
            (28, "Sales Reconciliation Difference:", "sales_reconciliation_difference"),
        ):
            ws.cell(row=row, column=1, value=label)
            ws.cell(row=row, column=2, value=sum(r.get(key, 0) for r in reports)).number_format = "₱#,##0.00"

    @staticmethod
    def _create_details_sheet(ws, reports: list[dict[str, Any]]) -> None:
        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF", size=11)
        border = Border(
            left=Side(style="thin"),
            right=Side(style="thin"),
            top=Side(style="thin"),
            bottom=Side(style="thin"),
        )

        headers = [
            "Report Date",
            "Checkout Sales",
            "Debt Collected",
            "Cash",
            "GCash",
            "BDO",
            "BPI",
            "QueenBank",
            "Unclassified Checkout",
            "Expenses",
            "Supplier Paid",
            "Net Balance",
            "Orders",
            "Timed Sessions",
            "Generated By",
            "Generated At",
            "Notes",
            "Other Income",
            "Budget Spent",
            "Business Expenses",
            "External-funded Expenses",
            "Business Supplier Paid",
            "External-funded Supplier Paid",
            "Cowork Bill",
            "Cafe Bill",
            "Discounts",
            "Refunds Paid",
            "Sales Reconciliation Difference",
        ]
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col)
            cell.value = header
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = border

        for row_idx, report in enumerate(reports, 2):
            values = [
                report["report_date"],
                report["total_revenue"],
                report.get("total_collections", 0),
                report.get("cash_total", 0),
                report.get("gcash_total", 0),
                report.get("bdo_total", 0),
                report.get("bpi_total", 0),
                report.get("queenbank_total", 0),
                report.get("unclassified_total", 0),
                report["total_expenses"],
                report.get("total_payables_paid", 0),
                report["net_balance"],
                report["total_orders"],
                report["total_sessions"],
                report["generated_by"],
                report.get("generated_at") or "",
                report["notes"] or "",
                report.get("total_other_income", 0),
                report.get("total_budget_spend", 0),
                report.get("total_business_expenses", 0),
                report.get("total_external_expenses", 0),
                report.get("total_business_payables_paid", 0),
                report.get("total_external_payables_paid", 0),
                report.get("cowork_bill", 0),
                report.get("cafe_bill", 0),
                report.get("discounts_total", 0),
                report.get("total_refunds", 0),
                report.get("sales_reconciliation_difference", 0),
            ]
            for col, value in enumerate(values, 1):
                cell = ws.cell(row=row_idx, column=col)
                cell.value = value
                cell.border = border
                if 2 <= col <= 12 or col in (18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28):
                    cell.number_format = "₱#,##0.00"

        for col, width in zip("ABCDEFGHIJKLMNOPQRSTUVW", [15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 10, 10, 15, 25, 25, 15, 15, 15, 15, 15, 15]):
            ws.column_dimensions[col].width = width
        for col in ("X", "Y", "Z", "AA"):
            ws.column_dimensions[col].width = 15
        ws.column_dimensions["AB"].width = 32

    @staticmethod
    def _create_comparison_sheet(ws, reports: list[dict[str, Any]]) -> None:
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF", size=11)

        ws["A1"] = "Period Comparison"
        ws["A1"].font = Font(bold=True, size=12)

        current = reports[0]
        previous = reports[1] if len(reports) > 1 else None

        for col, label in enumerate(["Metric", "Current Period", "Previous Period", "Change", "% Change"], 1):
            cell = ws.cell(row=3, column=col)
            cell.value = label
            cell.fill = header_fill
            cell.font = header_font

        metrics = [
            ("Revenue", "total_revenue"),
            ("Expenses", "total_expenses"),
            ("Net Balance", "net_balance"),
            ("Orders", "total_orders"),
            ("Timed Sessions", "total_sessions"),
        ]

        for row_idx, (label, key) in enumerate(metrics, 4):
            ws.cell(row=row_idx, column=1).value = label
            ws.cell(row=row_idx, column=2).value = current[key]
            prev_val = previous[key] if previous else 0
            ws.cell(row=row_idx, column=3).value = prev_val
            change = current[key] - prev_val
            ws.cell(row=row_idx, column=4).value = change
            pct_change = (change / prev_val * 100) if prev_val else 0
            ws.cell(row=row_idx, column=5).value = pct_change
            ws.cell(row=row_idx, column=5).number_format = '0.0"%"'
            if isinstance(current[key], float):
                for c in (2, 3, 4):
                    ws.cell(row=row_idx, column=c).number_format = "₱#,##0.00"

    @staticmethod
    def _create_trends_sheet(ws, reports: list[dict[str, Any]]) -> None:
        ws["A1"] = "Trends & Analysis"
        ws["A1"].font = Font(bold=True, size=12)
        ws["A3"] = "Analysis"
        ws["A3"].font = Font(bold=True, size=11)

        if not reports:
            return

        n = len(reports)
        ws["A4"] = "Average Daily Revenue:"
        ws["B4"] = sum(r["total_revenue"] for r in reports) / n
        ws["B4"].number_format = "₱#,##0.00"

        ws["A5"] = "Average Daily Expenses:"
        ws["B5"] = sum(r["total_expenses"] for r in reports) / n
        ws["B5"].number_format = "₱#,##0.00"

        ws["A6"] = "Average Daily Orders:"
        ws["B6"] = sum(r["total_orders"] for r in reports) / n
        ws["B6"].number_format = "0"

        max_revenue_report = max(reports, key=lambda r: r["total_revenue"])
        ws["A7"] = "Highest Revenue Day:"
        ws["B7"] = f"{max_revenue_report['report_date']} (₱{max_revenue_report['total_revenue']:.2f})"

        ws["A8"] = "Total Days Tracked:"
        ws["B8"] = n

        ws.column_dimensions["A"].width = 25
        ws.column_dimensions["B"].width = 30
