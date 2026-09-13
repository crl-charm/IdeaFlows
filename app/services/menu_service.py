from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from app.repositories.menu_repository import MenuRepository
from app.core.cache import get_or_set_json, invalidate_menu_cache


@dataclass(frozen=True)
class MenuService:
    repo: MenuRepository

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

    def create(self, name: str, price: float, category: str, description: Optional[str] = None, image_url: Optional[str] = None) -> dict[str, Any]:
        item = self.repo.create(name, price, category)
        if description:
            item.description = description
        if image_url:
            item.image_url = image_url
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
        category: Optional[str] = None, description: Optional[str] = None, image_url: Optional[str] = None
    ) -> dict[str, Any] | tuple[dict[str, Any], int]:
        success = self.repo.update(item_id, name, price, category)
        if not success:
            return {"error": "Menu item not found"}, 404
        
        item = self.repo.get(item_id)
        if description is not None:
            item.description = description
        if image_url:
            item.image_url = image_url
        
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
