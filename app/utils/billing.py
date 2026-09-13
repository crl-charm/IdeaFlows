"""Per-session seating charges using started billing blocks."""

from decimal import Decimal, ROUND_CEILING


def calculate_time_bill(space, minutes) -> Decimal:
    elapsed = max(Decimal(str(minutes)), Decimal(0))
    name = (space.name if space else "").strip().lower()
    if name == "boardroom":
        hours = max(Decimal(1), (elapsed / 60).to_integral_value(rounding=ROUND_CEILING))
        return (hours * 250).quantize(Decimal("0.01"))
    if name in {"regular lounge", "premium lounge"}:
        hourly = Decimal(10 if name == "regular lounge" else 20)
        extra = (max(elapsed - 60, Decimal(0)) / 30).to_integral_value(rounding=ROUND_CEILING)
        return (hourly + extra * hourly / 2).quantize(Decimal("0.01"))
    rate = Decimal(str(space.rate_per_minute or 0)) if space else Decimal(0)
    return (elapsed * rate).quantize(Decimal("0.01"))
