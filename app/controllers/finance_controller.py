from __future__ import annotations

from flask import Blueprint, Response, jsonify, render_template, request

from app.controllers.base_controller import BaseController
from app.services.finance_oop_service import FinanceService
from app.utils.auth import admin_required
from app import csrf
from app.core.idempotency import idempotent_request


class FinanceController(BaseController):
    """Serves finance section pages and API operations."""

    def __init__(self, db) -> None:
        self._service = FinanceService(db)
        self.blueprint = Blueprint("finance_page", __name__)
        self._register_routes()

    def _render(self, template_name: str):
        data = self._service.get_summary()
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return render_template("finance/_content.html", **data)
        return render_template(template_name, **data)

    def _register_routes(self) -> None:
        @self.blueprint.get("/finance")
        @admin_required
        def finance_home():
            return self._render("finance/index.html")

        @self.blueprint.get("/finance/budget")
        @admin_required
        def finance_budget():
            return self._render("finance/budget.html")

        @self.blueprint.get("/finance/expenses")
        @admin_required
        def finance_expenses():
            return self._render("finance/expenses.html")

        @self.blueprint.get("/finance/reports")
        @admin_required
        def finance_reports():
            return self._render("finance/index.html")

        @self.blueprint.get("/api/finance/summary")
        @admin_required
        def finance_summary():
            return jsonify({"success": True, "data": self._service.get_summary()})

        @self.blueprint.post("/api/finance/transaction")
        @admin_required
        @csrf.exempt
        @idempotent_request("admin-create-finance-transaction")
        def finance_add_transaction():
            payload = request.get_json(silent=True) or {}
            txn_type = str(payload.get("type", "expense")).strip()
            amount_val = payload.get("amount")
            description = payload.get("description")
            
            if txn_type not in {"income", "expense"}:
                return jsonify({"success": False, "error": "Invalid transaction type"}), 400
            
            try:
                amount = float(amount_val)
                if amount <= 0:
                    return jsonify({"success": False, "error": "Amount must be greater than zero"}), 400
            except (TypeError, ValueError):
                return jsonify({"success": False, "error": "Invalid amount"}), 400
                
            from app.utils.auth import sanitize_input
            sanitized_description = sanitize_input(description)
            
            result = self._service.add_transaction(
                budget_id=int(payload.get("budget_id", 1)),
                txn_type=txn_type,
                amount=amount,
                description=sanitized_description,
            )
            return jsonify({"success": True, "data": result})

        @self.blueprint.get("/api/finance/export")
        @admin_required
        def finance_export():
            pdf = self._service.render_pdf_bytes("finance/_content.html", **self._service.get_summary())
            return Response(
                pdf,
                mimetype="application/pdf",
                headers={"Content-Disposition": "attachment; filename=finance-summary.pdf"},
            )

    def get_dashboard_data(self) -> dict:
        return self._service.get_dashboard_data()
