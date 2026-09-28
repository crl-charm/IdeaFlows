# IdeaHub working agreements

- For coding, debugging, refactoring, and code review in this repository, load and follow the `ponytail` skill. Use its full mode unless the user chooses another level. Aim for the smallest working change after tracing the relevant code and callers.
- Keep behavior, authorization, input validation, financial and inventory integrity, and accessibility intact while simplifying. Reuse an existing path before adding a new layer or dependency.
- For an explicit code review, use the repo skill `ponytail-review-code`. Before finishing a code change, inspect the diff for needless code and regressions.

The Flask app factory is in `app/__init__.py`; HTTP endpoints are in `app/routes/` and `app/controllers/`, business logic in `app/services/`, persistence in `app/repositories/` and `app/models/`, and UI in `app/templates/` and root `static/`. Read only the parts relevant to the task.

Tests in `tests/` use isolated SQLite and disable external services through `tests/conftest.py`. Run the smallest relevant pytest target for changed behavior; use the full suite when the change crosses several domains.

## Financial auditability (mandatory)

- Every operation that creates, changes, collects, refunds, discounts, owes, or spends money must write an accurate, queryable history entry. This includes checkouts, orders with a financial effect, boardroom and whole-hub bookings, expenses, receivables and their payments, payables and their payments, discounts, refunds, and cash adjustments.
- Each history entry must retain the amount, payment method, business date/time, actor, related customer/order/session/booking or account, and enough before/after or remaining-balance detail to explain the change. Retries must not create duplicate financial records.
- Daily Balance is the reconciliation view for these records. Its live cards, generated reports, payment breakdowns, exports, and filters must use the same source records and the same Asia/Manila business-day boundaries. Receivable and payable payment history must be reflected in the appropriate daily totals without double-counting revenue.
- Never mark a money-related feature complete until its history can be reviewed from the relevant screen and its totals reconcile with Daily Balance for each payment method. Add a focused test for the ledger-to-Daily-Balance path whenever this behavior changes.
