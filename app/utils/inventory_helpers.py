from __future__ import annotations


def is_ingredient_category(category: str | None) -> bool:
    return (category or "").strip().lower() == "ingredient"


_UNIT_ALIASES: dict[str, str] = {
    "piece": "pieces",
    "pieces": "pieces",
    "pcs": "pieces",
    "pc": "pieces",
    "kg": "klg",
    "klg": "klg",
    "kilogram": "klg",
    "kilograms": "klg",
    "gram": "grams",
    "grams": "grams",
    "g": "grams",
    "tray": "trays",
    "trays": "trays",
    "pack": "packs",
    "packs": "packs",
    "liter": "liters",
    "liters": "liters",
    "l": "liters",
    "ml": "ml",
}


def normalize_unit(unit: str | None) -> str:
    raw = (unit or "").strip().lower()
    if not raw:
        return "pieces"
    return _UNIT_ALIASES.get(raw, raw)


def units_are_compatible(
    recipe_unit: str | None,
    inventory_unit: str | None,
    conversion_ratio: float | None = 1.0,
) -> bool:
    """Units match directly, or admin configured an explicit conversion ratio."""
    if not (recipe_unit or "").strip():
        return True
    if normalize_unit(recipe_unit) == normalize_unit(inventory_unit):
        return True
    return float(conversion_ratio or 1.0) != 1.0
