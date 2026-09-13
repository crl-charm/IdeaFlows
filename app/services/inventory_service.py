from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import func

from app.repositories.inventory_repository import InventoryRepository
from app.utils.inventory_helpers import is_ingredient_category, units_are_compatible

logger = logging.getLogger(__name__)

DEFAULT_LOW_STOCK_THRESHOLD = 10
DEFAULT_UNIT = "pieces"


@dataclass(frozen=True)
class InventoryService:
    repo: InventoryRepository

    @staticmethod
    def compute_stock_status(stock_qty: float | Decimal, threshold: int) -> dict[str, bool]:
        stock_val = float(stock_qty)
        is_out_of_stock = stock_val <= 0
        if threshold <= 0:
            is_low = False
        else:
            is_low = stock_val > 0 and stock_val <= threshold
        stock_ratio = stock_val / threshold if threshold > 0 else 0
        is_warning = (
            not is_out_of_stock
            and not is_low
            and threshold > 0
            and stock_ratio < 1.5
        )
        return {
            "is_low": is_low,
            "is_warning": is_warning,
            "is_out_of_stock": is_out_of_stock,
        }

    @staticmethod
    def snapshot_from_row(
        menu_item_id: int, inv: Any | None
    ) -> dict[str, Any]:
        if inv is not None:
            return {
                "menu_item_id": menu_item_id,
                "inventory_item_id": inv.id,
                "stock_qty": float(inv.stock_qty),
                "low_stock_threshold": inv.low_stock_threshold,
                "unit": inv.unit,
                "persisted": True,
            }
        return {
            "menu_item_id": menu_item_id,
            "inventory_item_id": None,
            "stock_qty": 0.0,
            "low_stock_threshold": DEFAULT_LOW_STOCK_THRESHOLD,
            "unit": DEFAULT_UNIT,
            "persisted": False,
        }

    def resolve_inventory_snapshot(
        self, menu_item_id: int, inventory_map: dict[int, Any] | None = None
    ) -> dict[str, Any]:
        if inventory_map is not None:
            return self.snapshot_from_row(menu_item_id, inventory_map.get(menu_item_id))
        inv = self.repo.get_by_menu_item_id(menu_item_id)
        return self.snapshot_from_row(menu_item_id, inv)

    def _ingredient_menu_items(self):
        from app.models.menu_item import MenuItem

        return [
            item
            for item in MenuItem.query.filter(MenuItem.status != "deleted").all()
            if is_ingredient_category(item.category)
        ]

    def _sellable_menu_items(self):
        from app.models.menu_item import MenuItem

        return [
            item
            for item in MenuItem.query.filter(MenuItem.status != "deleted").all()
            if not is_ingredient_category(item.category)
        ]

    def calculate_recipe_capacity(
        self,
        menu_item_id: int,
        inventory_map: dict[int, Any] | None = None,
    ) -> dict[str, Any]:
        from app.models.menu_item import MenuItem, MenuItemIngredient

        meal = MenuItem.query.get(menu_item_id)
        if not meal or meal.status == "deleted":
            return {
                "has_recipe": False,
                "capacity": 0,
                "is_available": False,
                "error": "MENU_ITEM_NOT_FOUND",
                "message": "Menu item not found.",
                "is_low": False,
                "is_warning": False,
                "is_out_of_stock": True,
            }

        mappings = MenuItemIngredient.query.filter_by(menu_item_id=menu_item_id).all()
        if not mappings:
            snap = self.resolve_inventory_snapshot(menu_item_id, inventory_map)
            status = self.compute_stock_status(
                snap["stock_qty"], snap["low_stock_threshold"]
            )
            capacity = int(float(snap["stock_qty"]))
            if not snap["persisted"]:
                return {
                    "has_recipe": False,
                    "capacity": 0,
                    "is_available": False,
                    "error": "INVENTORY_ROW_NOT_FOUND",
                    "message": f"'{meal.name}' has no inventory record.",
                    "is_low": False,
                    "is_warning": False,
                    "is_out_of_stock": True,
                }
            return {
                "has_recipe": False,
                "capacity": capacity,
                "is_available": capacity > 0,
                "error": None,
                "message": None,
                **status,
            }

        if inventory_map is None:
            ingredient_ids = [m.ingredient_item_id for m in mappings]
            inventory_map = self._build_inventory_map(ingredient_ids)

        caps: list[int] = []
        is_low = False
        is_warning = False

        for mapping in mappings:
            ing = mapping.ingredient
            ing_name = ing.name if ing else "Unknown"
            snap = self.resolve_inventory_snapshot(
                mapping.ingredient_item_id, inventory_map
            )
            if not snap["persisted"]:
                return {
                    "has_recipe": True,
                    "capacity": 0,
                    "is_available": False,
                    "error": "INVENTORY_ROW_NOT_FOUND",
                    "message": f"Recipe ingredient '{ing_name}' has no inventory record.",
                    "is_low": False,
                    "is_warning": False,
                    "is_out_of_stock": True,
                }

            if not units_are_compatible(
                mapping.unit, snap["unit"], float(mapping.conversion_ratio or 1.0)
            ):
                return {
                    "has_recipe": True,
                    "capacity": 0,
                    "is_available": False,
                    "error": "INVALID_UNIT_CONVERSION",
                    "message": (
                        f"Invalid unit conversion for ingredient '{ing_name}' "
                        f"(recipe: {mapping.unit or 'pieces'}, inventory: {snap['unit']})."
                    ),
                    "is_low": False,
                    "is_warning": False,
                    "is_out_of_stock": True,
                }

            ing_status = self.compute_stock_status(
                snap["stock_qty"], snap["low_stock_threshold"]
            )
            if ing_status["is_low"]:
                is_low = True
            elif ing_status["is_warning"]:
                is_warning = True

            qty_req = float(mapping.quantity_required) * float(
                mapping.conversion_ratio or 1.0
            )
            if qty_req > 0:
                caps.append(int(float(snap["stock_qty"]) / qty_req))
            else:
                caps.append(0)

        capacity = min(caps) if caps else 0
        status = self.compute_stock_status(capacity, 1)
        return {
            "has_recipe": True,
            "capacity": capacity,
            "is_available": capacity > 0,
            "error": None,
            "message": None,
            "is_low": is_low,
            "is_warning": is_warning,
            "is_out_of_stock": capacity <= 0,
        }

    def validate_order_stock(self, items: list[dict[str, Any]]) -> dict[str, Any] | None:
        from app.models.menu_item import MenuItem, MenuItemIngredient
        from app.models.inventory import InventoryItem

        ingredient_needs: dict[int, list[float, list[str], str | None]] = {}

        for item in items:
            menu_item_id = item.get("menu_item_id")
            qty = float(item.get("quantity", 1))
            menu_item = MenuItem.query.get(menu_item_id)
            if not menu_item:
                continue

            cap = self.calculate_recipe_capacity(menu_item_id)
            logger.info(
                "add_order capacity menu_item_id=%s name=%s capacity=%s error=%s",
                menu_item_id,
                menu_item.name,
                cap.get("capacity"),
                cap.get("error"),
            )
            if cap.get("error"):
                return {
                    "error": cap["error"],
                    "message": cap.get("message") or cap["error"],
                }
            if cap["capacity"] < qty:
                return {
                    "error": "INSUFFICIENT_STOCK",
                    "message": (
                        f"Insufficient stock to prepare {qty} × {menu_item.name} "
                        f"(capacity: {cap['capacity']})."
                    ),
                }

            recipe = MenuItemIngredient.query.filter_by(
                menu_item_id=menu_item_id
            ).all()
            logger.info(
                "add_order recipe menu_item_id=%s mappings=%s",
                menu_item_id,
                len(recipe),
            )
            if recipe:
                for comp in recipe:
                    ing = MenuItem.query.get(comp.ingredient_item_id)
                    ing_name = ing.name if ing else "Unknown"
                    logger.info(
                        "add_order ingredient id=%s name=%s category=%s",
                        comp.ingredient_item_id,
                        ing_name,
                        ing.category if ing else None,
                    )
                    ratio = float(comp.conversion_ratio or 1.0)
                    needed = qty * float(comp.quantity_required) * ratio
                    inv = InventoryItem.query.filter_by(
                        menu_item_id=comp.ingredient_item_id
                    ).first()
                    logger.info(
                        "add_order inventory exists=%s required=%s available=%s",
                        inv is not None,
                        needed,
                        float(inv.stock_qty) if inv else None,
                    )
                    if not inv:
                        return {
                            "error": "INVENTORY_ROW_NOT_FOUND",
                            "message": f"Recipe ingredient '{ing_name}' has no inventory record.",
                        }
                    if not units_are_compatible(
                        comp.unit, inv.unit, float(comp.conversion_ratio or 1.0)
                    ):
                        return {
                            "error": "INVALID_UNIT_CONVERSION",
                            "message": (
                                f"Invalid unit conversion for ingredient '{ing_name}' "
                                f"(recipe: {comp.unit or 'pieces'}, inventory: {inv.unit})."
                            ),
                        }
                    if comp.ingredient_item_id not in ingredient_needs:
                        ingredient_needs[comp.ingredient_item_id] = [0.0, [], None]
                    ingredient_needs[comp.ingredient_item_id][0] += needed
                    ingredient_needs[comp.ingredient_item_id][1].append(menu_item.name)
            else:
                inv = InventoryItem.query.filter_by(menu_item_id=menu_item_id).first()
                if not inv:
                    return {
                        "error": "INVENTORY_ROW_NOT_FOUND",
                        "message": f"'{menu_item.name}' has no inventory record.",
                    }
                if menu_item_id not in ingredient_needs:
                    ingredient_needs[menu_item_id] = [0.0, [], None]
                ingredient_needs[menu_item_id][0] += qty
                ingredient_needs[menu_item_id][1].append(menu_item.name)

        for ing_id, (needed_qty, meals, _) in ingredient_needs.items():
            inv = InventoryItem.query.filter_by(menu_item_id=ing_id).first()
            current_stock = float(inv.stock_qty) if inv else 0.0
            if current_stock < needed_qty:
                ing_item = MenuItem.query.get(ing_id)
                ing_name = ing_item.name if ing_item else "Ingredient"
                meal_list = ", ".join(set(meals))
                logger.info(
                    "add_order validation failure ingredient=%s need=%s have=%s meals=%s",
                    ing_name,
                    needed_qty,
                    current_stock,
                    meal_list,
                )
                return {
                    "error": "INSUFFICIENT_STOCK",
                    "message": (
                        f"Insufficient stock for '{ing_name}' "
                        f"(Need {needed_qty:.2f}, Have {current_stock:.2f}) "
                        f"to prepare {meal_list}."
                    ),
                }
        return None

    def get_inventory_summary(self) -> dict[str, int]:
        from app.models.inventory import InventoryItem
        from app.models.menu_item import MenuItem

        items = (
            InventoryItem.query.join(MenuItem, MenuItem.id == InventoryItem.menu_item_id)
            .filter(MenuItem.status != "deleted")
            .all()
        )
        low_stock = sum(
            1
            for item in items
            if float(item.stock_qty) > 0
            and float(item.stock_qty) <= item.low_stock_threshold
        )
        no_stock = sum(1 for item in items if float(item.stock_qty) <= 0)
        total_menu_items = len(self._sellable_menu_items())

        return {
            "low_stock": low_stock,
            "no_stock": no_stock,
            "total_menu_items": total_menu_items,
        }

    def ensure_inventory_row(
        self,
        menu_item_id: int,
        stock_qty: int = 0,
        low_stock_threshold: int = DEFAULT_LOW_STOCK_THRESHOLD,
        unit: str = DEFAULT_UNIT,
    ) -> Any:
        existing = self.repo.get_by_menu_item_id(menu_item_id)
        if existing:
            return existing
        item = self.repo.create(menu_item_id, stock_qty, low_stock_threshold, unit)
        self.repo.save()
        return item

    def _build_inventory_map(self, menu_item_ids: list[int]) -> dict[int, Any]:
        return self.repo.list_by_menu_item_ids(menu_item_ids)

    def _calculate_recipe_capacity_from_loaded(
        self,
        meal: Any,
        mappings: list[Any],
        inventory_map: dict[int, Any],
        item_map: dict[int, Any],
    ) -> dict[str, Any]:
        """Calculate capacity without issuing queries for each menu item."""
        if not mappings:
            snap = self.resolve_inventory_snapshot(meal.id, inventory_map)
            status = self.compute_stock_status(
                snap["stock_qty"], snap["low_stock_threshold"]
            )
            capacity = int(float(snap["stock_qty"]))
            if not snap["persisted"]:
                return {
                    "has_recipe": False,
                    "capacity": 0,
                    "is_available": False,
                    "error": "INVENTORY_ROW_NOT_FOUND",
                    "message": f"'{meal.name}' has no inventory record.",
                    "is_low": False,
                    "is_warning": False,
                    "is_out_of_stock": True,
                }
            return {
                "has_recipe": False,
                "capacity": capacity,
                "is_available": capacity > 0,
                "error": None,
                "message": None,
                **status,
            }

        capacities: list[int] = []
        is_low = False
        is_warning = False
        for mapping in mappings:
            ingredient = item_map.get(mapping.ingredient_item_id)
            ingredient_name = ingredient.name if ingredient else "Unknown"
            snap = self.resolve_inventory_snapshot(
                mapping.ingredient_item_id, inventory_map
            )
            if not snap["persisted"]:
                return {
                    "has_recipe": True,
                    "capacity": 0,
                    "is_available": False,
                    "error": "INVENTORY_ROW_NOT_FOUND",
                    "message": f"Recipe ingredient '{ingredient_name}' has no inventory record.",
                    "is_low": False,
                    "is_warning": False,
                    "is_out_of_stock": True,
                }
            if not units_are_compatible(
                mapping.unit, snap["unit"], float(mapping.conversion_ratio or 1.0)
            ):
                return {
                    "has_recipe": True,
                    "capacity": 0,
                    "is_available": False,
                    "error": "INVALID_UNIT_CONVERSION",
                    "message": (
                        f"Invalid unit conversion for ingredient '{ingredient_name}' "
                        f"(recipe: {mapping.unit or 'pieces'}, inventory: {snap['unit']})."
                    ),
                    "is_low": False,
                    "is_warning": False,
                    "is_out_of_stock": True,
                }

            ingredient_status = self.compute_stock_status(
                snap["stock_qty"], snap["low_stock_threshold"]
            )
            is_low = is_low or ingredient_status["is_low"]
            is_warning = is_warning or ingredient_status["is_warning"]
            required = float(mapping.quantity_required) * float(
                mapping.conversion_ratio or 1.0
            )
            capacities.append(
                int(float(snap["stock_qty"]) / required) if required > 0 else 0
            )

        capacity = min(capacities) if capacities else 0
        return {
            "has_recipe": True,
            "capacity": capacity,
            "is_available": capacity > 0,
            "error": None,
            "message": None,
            "is_low": is_low,
            "is_warning": is_warning,
            "is_out_of_stock": capacity <= 0,
        }

    def build_dashboard_snapshot(self) -> dict[str, Any]:
        """Load dashboard data in three bounded queries, independent of row count."""
        from app.models.menu_item import MenuItem, MenuItemIngredient

        menu_items = MenuItem.query.filter(MenuItem.status != "deleted").all()
        item_map = {item.id: item for item in menu_items}
        inventory_map = self._build_inventory_map(list(item_map))
        mappings = MenuItemIngredient.query.filter(
            MenuItemIngredient.menu_item_id.in_(item_map),
            MenuItemIngredient.ingredient_item_id.in_(item_map),
        ).all() if item_map else []

        mappings_by_meal: dict[int, list[Any]] = {}
        mappings_by_ingredient: dict[int, list[Any]] = {}
        for mapping in mappings:
            mappings_by_meal.setdefault(mapping.menu_item_id, []).append(mapping)
            mappings_by_ingredient.setdefault(mapping.ingredient_item_id, []).append(mapping)

        ingredients = [
            item for item in menu_items if is_ingredient_category(item.category)
        ]
        meals = [
            item for item in menu_items if not is_ingredient_category(item.category)
        ]

        recipe_items: list[dict[str, Any]] = []
        for meal in meals:
            capacity = self._calculate_recipe_capacity_from_loaded(
                meal,
                mappings_by_meal.get(meal.id, []),
                inventory_map,
                item_map,
            )
            row: dict[str, Any] = {
                "id": meal.id,
                "name": meal.name,
                "category": meal.category,
                "has_recipe": capacity["has_recipe"],
                "is_low": capacity.get("is_low", False),
                "is_warning": capacity.get("is_warning", False),
                "is_out_of_stock": capacity.get(
                    "is_out_of_stock", capacity["capacity"] <= 0
                ),
                "capacity": capacity["capacity"],
                "availability_error": capacity.get("error"),
            }
            if not capacity["has_recipe"]:
                snap = self.resolve_inventory_snapshot(meal.id, inventory_map)
                row.update(
                    inventory_item_id=snap["inventory_item_id"],
                    stock_qty=snap["stock_qty"],
                    unit=snap["unit"],
                    low_stock_threshold=snap["low_stock_threshold"],
                    persisted=snap["persisted"],
                )
            recipe_items.append(row)

        direct_stock: list[dict[str, Any]] = []
        for ingredient in ingredients:
            snap = self.resolve_inventory_snapshot(ingredient.id, inventory_map)
            links = mappings_by_ingredient.get(ingredient.id, [])
            names = [
                item_map[link.menu_item_id].name
                for link in links
                if link.menu_item_id in item_map
            ]
            direct_stock.append(
                {
                    "id": ingredient.id,
                    "menu_item_id": ingredient.id,
                    "name": ingredient.name,
                    "inventory_item_id": snap["inventory_item_id"],
                    "stock_qty": snap["stock_qty"],
                    "unit": snap["unit"],
                    "low_stock_threshold": snap["low_stock_threshold"],
                    "persisted": snap["persisted"],
                    "recipe_count": len(links),
                    "is_linked": bool(links),
                    "linked_meal_names": names,
                    **self.compute_stock_status(
                        snap["stock_qty"], snap["low_stock_threshold"]
                    ),
                }
            )

        active_inventory = [
            inventory_map[item.id]
            for item in menu_items
            if item.id in inventory_map
        ]
        summary = {
            "low_stock": sum(
                1
                for item in active_inventory
                if 0 < float(item.stock_qty) <= item.low_stock_threshold
            ),
            "no_stock": sum(
                1 for item in active_inventory if float(item.stock_qty) <= 0
            ),
            "total_menu_items": len(meals),
        }
        return {"data": recipe_items, "direct_stock": direct_stock, "summary": summary}

    def build_direct_stock_items(self) -> list[dict[str, Any]]:
        from app.models.menu_item import MenuItem, MenuItemIngredient

        ingredients = self._ingredient_menu_items()
        if not ingredients:
            return []

        ingredient_ids = [i.id for i in ingredients]
        inventory_map = self._build_inventory_map(ingredient_ids)

        recipe_counts = dict(
            MenuItemIngredient.query.with_entities(
                MenuItemIngredient.ingredient_item_id,
                func.count(MenuItemIngredient.id),
            )
            .filter(MenuItemIngredient.ingredient_item_id.in_(ingredient_ids))
            .group_by(MenuItemIngredient.ingredient_item_id)
            .all()
        )

        mappings = MenuItemIngredient.query.filter(
            MenuItemIngredient.ingredient_item_id.in_(ingredient_ids)
        ).all()
        meals_by_ingredient: dict[int, list[str]] = {iid: [] for iid in ingredient_ids}
        for m in mappings:
            if m.menu_item and m.menu_item.name:
                meals_by_ingredient.setdefault(m.ingredient_item_id, []).append(
                    m.menu_item.name
                )

        results: list[dict[str, Any]] = []
        for ing in ingredients:
            snap = self.resolve_inventory_snapshot(ing.id, inventory_map)
            status = self.compute_stock_status(
                snap["stock_qty"], snap["low_stock_threshold"]
            )
            count = recipe_counts.get(ing.id, 0)
            results.append(
                {
                    "id": ing.id,
                    "menu_item_id": ing.id,
                    "name": ing.name,
                    "inventory_item_id": snap["inventory_item_id"],
                    "stock_qty": snap["stock_qty"],
                    "unit": snap["unit"],
                    "low_stock_threshold": snap["low_stock_threshold"],
                    "persisted": snap["persisted"],
                    "recipe_count": count,
                    "is_linked": count > 0,
                    "linked_meal_names": meals_by_ingredient.get(ing.id, []),
                    **status,
                }
            )
        return results

    def build_recipe_inventory_items(self) -> list[dict[str, Any]]:
        meals = self._sellable_menu_items()
        if not meals:
            return []

        data: list[dict[str, Any]] = []
        for meal in meals:
            cap = self.calculate_recipe_capacity(meal.id)
            meal_data: dict[str, Any] = {
                "id": meal.id,
                "name": meal.name,
                "category": meal.category,
                "has_recipe": cap["has_recipe"],
                "is_low": cap.get("is_low", False),
                "is_warning": cap.get("is_warning", False),
                "is_out_of_stock": cap.get("is_out_of_stock", cap["capacity"] <= 0),
                "capacity": cap["capacity"],
                "availability_error": cap.get("error"),
            }
            if not cap["has_recipe"]:
                snap = self.resolve_inventory_snapshot(meal.id)
                meal_data["inventory_item_id"] = snap["inventory_item_id"]
                meal_data["stock_qty"] = snap["stock_qty"]
                meal_data["unit"] = snap["unit"]
                meal_data["low_stock_threshold"] = snap["low_stock_threshold"]
                meal_data["persisted"] = snap["persisted"]
            data.append(meal_data)

        return data

    def build_recipe_detail(self, menu_item_id: int) -> list[dict[str, Any]]:
        from app.models.menu_item import MenuItemIngredient

        mappings = MenuItemIngredient.query.filter_by(menu_item_id=menu_item_id).all()
        if not mappings:
            return []

        ingredient_ids = [m.ingredient_item_id for m in mappings]
        inventory_map = self._build_inventory_map(ingredient_ids)

        data: list[dict[str, Any]] = []
        for m in mappings:
            snap = self.resolve_inventory_snapshot(m.ingredient_item_id, inventory_map)
            data.append(
                {
                    "id": m.id,
                    "menu_item_id": m.menu_item_id,
                    "ingredient_item_id": m.ingredient_item_id,
                    "ingredient_name": m.ingredient.name if m.ingredient else "Unknown",
                    "quantity_required": float(m.quantity_required),
                    "unit": m.unit,
                    "conversion_ratio": float(m.conversion_ratio or 1.0),
                    "stock_qty": float(snap["stock_qty"]),
                    "ingredient_unit": snap["unit"],
                    "inventory_item_id": snap["inventory_item_id"],
                    "persisted": snap["persisted"],
                }
            )
        return data

    def list_ingredients_for_picker(
        self, query: str | None = None
    ) -> list[dict[str, Any]]:
        from app.models.menu_item import MenuItem, MenuItemIngredient

        q = MenuItem.query.filter(MenuItem.status != "deleted")
        if query and query.strip():
            q = q.filter(MenuItem.name.ilike(f"%{query.strip()}%"))
        ingredients = [
            item for item in q.order_by(MenuItem.name).all()
            if is_ingredient_category(item.category)
        ]
        if not ingredients:
            return []

        ingredient_ids = [i.id for i in ingredients]
        inventory_map = self._build_inventory_map(ingredient_ids)
        recipe_counts = dict(
            MenuItemIngredient.query.with_entities(
                MenuItemIngredient.ingredient_item_id,
                func.count(MenuItemIngredient.id),
            )
            .filter(MenuItemIngredient.ingredient_item_id.in_(ingredient_ids))
            .group_by(MenuItemIngredient.ingredient_item_id)
            .all()
        )

        results: list[dict[str, Any]] = []
        for ing in ingredients:
            snap = self.resolve_inventory_snapshot(ing.id, inventory_map)
            results.append(
                {
                    "id": ing.id,
                    "name": ing.name,
                    "recipe_count": recipe_counts.get(ing.id, 0),
                    "stock_qty": snap["stock_qty"],
                    "unit": snap["unit"],
                    "low_stock_threshold": snap["low_stock_threshold"],
                }
            )
        return results

    def list_all(self) -> list[dict[str, Any]]:
        items = self.repo.list_all()
        return [
            {
                "id": item.id,
                "menu_item_id": item.menu_item_id,
                "menu_item_name": item.menu_item.name if item.menu_item else "Unknown",
                "stock_qty": float(item.stock_qty),
                "low_stock_threshold": item.low_stock_threshold,
                "unit": item.unit,
                "is_low": float(item.stock_qty) > 0
                and float(item.stock_qty) <= item.low_stock_threshold,
            }
            for item in items
        ]

    def get_item(self, item_id: int) -> dict[str, Any] | tuple[dict[str, Any], int]:
        item = self.repo.get_item(item_id)
        if not item:
            return {"error": "Inventory item not found"}, 404
        return {
            "id": item.id,
            "menu_item_id": item.menu_item_id,
            "menu_item_name": item.menu_item.name,
            "stock_qty": float(item.stock_qty),
            "low_stock_threshold": item.low_stock_threshold,
            "unit": item.unit,
        }

    def create(
        self, menu_item_id: int, stock_qty: float | int, low_stock_threshold: int, unit: str
    ) -> dict[str, Any]:
        existing = self.repo.get_by_menu_item_id(menu_item_id)
        if existing:
            existing.stock_qty = float(stock_qty)
            existing.low_stock_threshold = int(low_stock_threshold)
            if unit:
                existing.unit = unit
            self.repo.save()
            return {"success": True, "data": {"id": existing.id}}
        item = self.repo.create(menu_item_id, stock_qty, low_stock_threshold, unit)
        self.repo.save()
        return {"success": True, "data": {"id": item.id}}

    def update_stock(
        self,
        item_id: int | None,
        new_qty: int,
        reason: str,
        user_id: Optional[int],
        menu_item_id: int | None = None,
    ) -> dict[str, Any] | tuple[dict[str, Any], int]:
        if item_id:
            item = self.repo.get_item_for_update(item_id)
        elif menu_item_id is not None:
            item = self.ensure_inventory_row(menu_item_id)
        else:
            return {"error": "Inventory item not found"}, 404

        if not item:
            return {"error": "Inventory item not found"}, 404

        if new_qty < 0:
            return {"error": "Stock quantity cannot be less than zero"}, 400

        old_qty = float(item.stock_qty)
        change = float(new_qty) - old_qty

        from app.models.user import User

        user = User.query.get(user_id) if user_id else None
        username = user.username if user else "System"

        formatted_reason = f"{username} adjusted {change:+.2f} ({old_qty:.2f} → {new_qty:.2f}) - {reason}"
        formatted_reason = formatted_reason[:100]

        if change > 0:
            self.repo.add(item.id, change, formatted_reason, user_id)
        elif change < 0:
            self.repo.deduct(item.id, abs(change), formatted_reason, user_id)

        self.repo.save()
        return {"success": True, "data": {"inventory_item_id": item.id}}

    def delete_raw_ingredient(
        self, menu_item_id: int
    ) -> dict[str, Any] | tuple[dict[str, Any], int]:
        from app.models.menu_item import MenuItem, MenuItemIngredient

        menu_item = MenuItem.query.get(menu_item_id)
        if not menu_item or not is_ingredient_category(menu_item.category):
            return {"error": "Raw ingredient not found"}, 404
        if menu_item.status == "deleted":
            return {"error": "Raw ingredient not found"}, 404

        recipe_count = MenuItemIngredient.query.filter_by(
            ingredient_item_id=menu_item_id
        ).count()
        if recipe_count > 0:
            return {
                "error": (
                    f"Cannot delete: ingredient is used in {recipe_count} "
                    "recipe(s). Remove recipe links first."
                )
            }, 400

        inv = self.repo.get_by_menu_item_id(menu_item_id)
        if inv:
            self.repo.delete(inv.id)

        menu_item.status = "deleted"
        menu_item.is_available = False
        self.repo.save()
        return {"success": True}

    def delete(self, item_id: int) -> dict[str, Any] | tuple[dict[str, Any], int]:
        item = self.repo.get_item(item_id)
        if not item:
            return {"error": "Inventory item not found"}, 404
        success = self.repo.delete(item_id)
        if success:
            self.repo.save()
            return {"success": True}
        return {"error": "Failed to delete inventory item"}, 500

    def deduct_on_order(
        self, menu_item_id: int, qty: float, *, commit: bool = True
    ) -> bool:
        from app.models.menu_item import MenuItemIngredient
        from app.core.socketio_handlers import emit_inventory_low_stock

        ingredients = MenuItemIngredient.query.filter_by(menu_item_id=menu_item_id).all()

        if ingredients:
            success = True
            for recipe_component in ingredients:
                ratio = float(recipe_component.conversion_ratio or 1.0)
                total_deduction = float(qty * recipe_component.quantity_required) * ratio
                item = self.repo.get_by_menu_item_id_for_update(
                    recipe_component.ingredient_item_id
                )
                if item:
                    deducted = self.repo.deduct(
                        item.id,
                        total_deduction,
                        f"Order deduction for {recipe_component.menu_item.name}",
                        None,
                    )
                    if deducted:
                        if float(item.stock_qty) < item.low_stock_threshold:
                            emit_inventory_low_stock(
                                {
                                    "item_id": item.id,
                                    "menu_item": item.menu_item.name,
                                    "stock_qty": float(item.stock_qty),
                                    "threshold": item.low_stock_threshold,
                                }
                            )
                    else:
                        success = False
            if success and commit:
                self.repo.save()
            return success
        else:
            item = self.repo.get_by_menu_item_id_for_update(menu_item_id)
            if not item:
                return False
            success = self.repo.deduct(item.id, qty, "Order deduction", None)
            if success and commit:
                self.repo.save()
                if float(item.stock_qty) < item.low_stock_threshold:
                    emit_inventory_low_stock(
                        {
                            "item_id": item.id,
                            "menu_item": item.menu_item.name,
                            "stock_qty": float(item.stock_qty),
                            "threshold": item.low_stock_threshold,
                        }
                    )
            return success

    def get_low_stock(self) -> list[dict[str, Any]]:
        items = self.repo.list_low_stock()
        return [
            {
                "id": item.id,
                "menu_item": item.menu_item.name,
                "stock_qty": float(item.stock_qty),
                "threshold": item.low_stock_threshold,
            }
            for item in items
        ]

    def get_logs(self, item_id: int) -> list[dict[str, Any]]:
        logs = self.repo.get_logs(item_id)
        return [
            {
                "id": log.id,
                "change_qty": float(log.change_qty),
                "reason": log.reason,
                "changed_by": log.changed_by_user.username if log.changed_by_user else "System",
                "created_at": log.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            }
            for log in logs
        ]
