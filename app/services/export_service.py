from __future__ import annotations

from io import BytesIO

from flask import render_template

from app.services.base_service import BaseService


class ExportService(BaseService):
    """Provides PDF export behavior for inheriting services."""

    def render_pdf_bytes(self, template_path: str, **context) -> bytes:
        try:
            from weasyprint import HTML

            html = render_template(template_path, pdf_backend="weasyprint", **context)
            return HTML(string=html).write_pdf()
        except Exception:
            pass
        try:
            from xhtml2pdf import pisa

            html = render_template(template_path, pdf_backend="xhtml2pdf", **context)
            buffer = BytesIO()
            result = pisa.CreatePDF(html, dest=buffer, encoding="utf-8")
            pdf = buffer.getvalue()
            if not result.err and pdf.startswith(b"%PDF"):
                return pdf
        except Exception:
            pass
        raise RuntimeError("PDF export is unavailable on this server.")
