from decimal import Decimal, InvalidOperation

VALID_PAYMENT_METHODS = frozenset({"cash", "gcash", "bdo", "bpi", "queenbank"})


def normalize_payment_method(value: str | None) -> str:
    method = (value or "cash").strip().lower()
    return method if method in VALID_PAYMENT_METHODS else "cash"


def payment_method_label(value: str | None) -> str:
    method = normalize_payment_method(value)
    if method == "gcash":
        return "GCash"
    elif method == "bdo":
        return "BDO"
    elif method == "bpi":
        return "BPI"
    elif method == "queenbank":
        return "QueenBank"
    return "Cash"


def parse_money_amount(value) -> Decimal:
    if value is None or str(value).strip() == "":
        raise ValueError("Invalid amount tendered.")
    try:
        parsed = Decimal(str(value)).quantize(Decimal("0.01"))
        if parsed < 0:
            raise ValueError("Invalid amount tendered.")
        return parsed
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Invalid amount tendered.")


def compute_change(total, tendered) -> float | None:
    if tendered is None or total is None:
        return None
    try:
        total_dec = Decimal(str(total))
        tendered_dec = Decimal(str(tendered))
        change = tendered_dec - total_dec
        if change < 0:
            return 0.0
        return float(change.quantize(Decimal("0.01")))
    except (InvalidOperation, ValueError, TypeError):
        return None
