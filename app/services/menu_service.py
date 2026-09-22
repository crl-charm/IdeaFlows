from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from difflib import get_close_matches
from typing import Any, Optional
from uuid import uuid4

from app import db
from app.models import MenuItem, MenuItemIngredient, InventoryItem
from app.services.menu_availability import StockError
from app.utils.inventory_helpers import is_ingredient_category, normalize_unit
from app.repositories.menu_repository import MenuRepository
from app.core.cache import get_or_set_json, invalidate_menu_cache


@dataclass(frozen=True)
class MenuService:
    repo: MenuRepository

    def _set_recipe(self, item, rows):
        if not isinstance(rows, list):
            raise StockError("Ingredients must be a list.", "INVALID_RECIPE", 400)
        existing = MenuItem.query.filter(MenuItem.status != "deleted").all()
        ingredients = {}
        for candidate in existing:
            if is_ingredient_category(candidate.category):
                ingredients.setdefault(" ".join(candidate.name.split()).casefold(), []).append(candidate)
        mappings, used = [], set()
        units = {"pieces", "grams", "klg", "trays", "packs", "liters", "ml"}
        conversions = {("grams", "klg"): Decimal("0.001"),
                       ("klg", "grams"): Decimal("1000"),
                       ("ml", "liters"): Decimal("0.001"),
                       ("liters", "ml"): Decimal("1000")}
        for number, row in enumerate(rows, 1):
            if not isinstance(row, dict):
                raise StockError(f"Ingredient {number} is invalid.", "INVALID_RECIPE", 400)
            name = " ".join(str(row.get("name") or "").split())
            unit = normalize_unit(str(row.get("unit") or ""))
            try:
                amount = Decimal(str(row.get("quantity")))
            except (InvalidOperation, TypeError):
                amount = Decimal(0)
            if not name or len(name) > 100 or unit not in units or not amount.is_finite() or amount <= 0 or amount > 999999 or amount != amount.quantize(Decimal("0.01")):
                raise StockError(f"Check ingredient {number}: enter a name, positive amount (up to two decimals), and unit.", "INVALID_RECIPE", 400)
            if unit in {"pieces", "trays", "packs"} and amount != amount.to_integral_value():
                raise StockError(f"{name} must use a whole-number count.", "INVALID_RECIPE", 400)
            key = name.casefold()
            if key in used:
                raise StockError(f"{name} is listed twice in this meal.", "DUPLICATE_INGREDIENT", 400)
            used.add(key)
            matches = ingredients.get(key, [])
            if len(matches) > 1:
                raise StockError(f"Multiple stock records named {name} need owner review.", "DUPLICATE_INGREDIENT", 409)
            if matches:
                ingredient = matches[0]
            else:
                similar = get_close_matches(key, ingredients, n=1, cutoff=0.85)
                if similar:
                    raise StockError(f"{name} looks like {ingredients[similar[0]][0].name}. Use the same name or correct the spelling.", "SIMILAR_INGREDIENT", 400)
                ingredient = MenuItem(name=name, price=0, category="ingredient", is_available=True)
                db.session.add(ingredient)
                db.session.flush()
                ingredients[key] = [ingredient]
            stocks = InventoryItem.query.filter_by(menu_item_id=ingredient.id).all()
            if len(stocks) > 1:
                raise StockError(f"{name} has duplicate stock records. Ask the owner to review them.", "DUPLICATE_STOCK", 409)
            if stocks:
                stock_unit = normalize_unit(stocks[0].unit)
            else:
                stock_unit = unit
                db.session.add(InventoryItem(menu_item_id=ingredient.id, stock_qty=0, unit=unit))
            ratio = Decimal(1) if unit == stock_unit else conversions.get((unit, stock_unit))
            if ratio is None or amount * ratio != (amount * ratio).quantize(Decimal("0.01")):
                raise StockError(f"{name} is stored in {stock_unit}. Use a compatible amount and unit.", "INVALID_UNIT", 400)
            mappings.append(MenuItemIngredient(ingredient_item_id=ingredient.id,
                quantity_required=amount, unit=unit, conversion_ratio=ratio))
        item.ingredients = mappings
        db.session.flush()

    def list_all(self) -> list[dict[str, Any]]:
        def load():
            return [
                {
                    "id": item.id,
                    "name": item.name,
                    "description": item.description,
                    "price": float(item.price),
                    "category": item.category,
                    "is_available": item.is_available,
                    "inventory_mode": item.inventory_mode,
                    "image_url": item.image_url,
                }
                for item in self.repo.list_all()
            ]

        return get_or_set_json("menu:all", load)

    def list_available(self) -> list[dict[str, Any]]:
        def load():
            return [
                {
                    "id": item.id,
                    "name": item.name,
                    "description": item.description,
                    "price": float(item.price),
                    "category": item.category,
                    "image_url": item.image_url,
                }
                for item in self.repo.list_available()
            ]

        return get_or_set_json("menu:available", load)

    def list_for_ordering(self) -> list[dict[str, Any]]:
        def load():
            return [
                {
                    "id": item.id,
                    "name": item.name,
                    "description": item.description,
                    "price": float(item.price),
                    "category": item.category,
                    "image_url": item.image_url,
                    "is_available": bool(item.is_available),
                }
                for item in self.repo.list_for_ordering()
            ]

        return get_or_set_json("menu:ordering", load)

    def create(self, name: str, price: float, category: str, description: Optional[str] = None, image_url: Optional[str] = None,
               inventory_mode: str = "untracked", stock_quantity=0, stock_threshold=3, actor=None,
               recipe_ingredients=None) -> dict[str, Any]:
        from app.services.stock_management import change_stock
        item = self.repo.create(name, price, category)
        if description:
            item.description = description
        if image_url:
            item.image_url = image_url
        if recipe_ingredients is not None:
            if recipe_ingredients and inventory_mode not in {"untracked", "recipe"}:
                raise StockError("Use either recipe ingredients or a prepared count, not both.", "INVALID_MODE", 400)
            self._set_recipe(item, recipe_ingredients)
            inventory_mode = "recipe" if recipe_ingredients else inventory_mode
        change_stock(item.id, {"action": "setup", "inventory_mode": inventory_mode,
            "quantity": stock_quantity, "threshold": stock_threshold, "reason": "Menu item created"},
            actor, str(uuid4()), admin=True, commit=False)
        self.repo.save()
        invalidate_menu_cache()
        return {"success": True, "data": {"id": item.id}}

    def create_variants(
        self,
        base_name: str,
        variant_labels: list[str],
        variant_prices: list[float],
        category: str,
        description: Optional[str] = None,
        image_url: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Bulk-create variants like:
        base_name="Latte", labels=["Hot","Iced"] => "Hot Latte", "Iced Latte".
        """
        created_ids: list[int] = []
        for label, price in zip(variant_labels, variant_prices):
            # Prefix-only naming convention: "Hot Latte", "Iced Latte", etc.
            item_name = f"{label} {base_name}".strip()
            item = self.repo.create(item_name, price, category)
            item.inventory_mode = "untracked"
            if description is not None:
                item.description = description
            if image_url is not None:
                item.image_url = image_url
            created_ids.append(item.id)

        # Commit once for the whole variant batch.
        self.repo.save()
        invalidate_menu_cache()
        return {"created_ids": created_ids}

    def update(
        self, item_id: int, name: Optional[str] = None, price: Optional[float] = None, 
        category: Optional[str] = None, description: Optional[str] = None, image_url: Optional[str] = None,
        inventory_mode: Optional[str] = None, stock_quantity=0, stock_threshold=3, actor=None,
        recipe_ingredients=None, confirm_recipe_switch=False
    ) -> dict[str, Any] | tuple[dict[str, Any], int]:
        success = self.repo.update(item_id, name, price, category)
        if not success:
            return {"error": "Menu item not found"}, 404
        
        item = self.repo.get(item_id)
        if description is not None:
            item.description = description
        if image_url:
            item.image_url = image_url
        if recipe_ingredients is not None:
            if inventory_mode is not None:
                raise StockError("Change the recipe or stock mode, not both.", "INVALID_MODE", 400)
            if recipe_ingredients and item.inventory_mode in {"prepared", "direct"} and not confirm_recipe_switch:
                raise StockError("Confirm switching from counted stock to recipe ingredients.", "CONFIRM_REQUIRED", 400)
            had_recipe = bool(item.ingredients)
            self._set_recipe(item, recipe_ingredients)
            if recipe_ingredients:
                inventory_mode = "recipe"
            elif item.inventory_mode == "recipe" or had_recipe:
                inventory_mode = "untracked"
        if inventory_mode is not None and inventory_mode != item.inventory_mode:
            from app.services.stock_management import change_stock
            change_stock(item.id, {"action": "setup", "inventory_mode": inventory_mode,
                "quantity": stock_quantity, "threshold": stock_threshold, "reason": "Menu setup changed"},
                actor, str(uuid4()), admin=True, commit=False)
        
        self.repo.save()
        invalidate_menu_cache()
        return {"success": True}

    def toggle_availability(
        self, item_id: int
    ) -> dict[str, Any] | tuple[dict[str, Any], int]:
        success = self.repo.toggle_availability(item_id)
        if not success:
            return {"error": "Menu item not found"}, 404
        self.repo.save()
        invalidate_menu_cache()
        item = self.repo.get(item_id)
        return {"success": True, "is_available": item.is_available}

    def delete(self, item_id: int) -> dict[str, Any] | tuple[dict[str, Any], int]:
        success = self.repo.delete(item_id)
        if not success:
            return {"error": "Menu item not found"}, 404
        self.repo.save()
        invalidate_menu_cache()
        return {
            "success": True,
            "message": "Menu item removed from the menu.",
        }
