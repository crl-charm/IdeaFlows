from hashlib import sha256
from pathlib import Path
from time import time

import pytest

from app import create_app, db
from app.models import User


TEMPLATES = Path(__file__).resolve().parents[1] / "app" / "templates"


@pytest.fixture
def app():
    return create_app()


def test_inventory_pages_show_zero_stock_as_out_of_stock():
    admin = (TEMPLATES / "admin" / "inventory.html").read_text(encoding="utf-8")
    staff = (TEMPLATES / "staff" / "inventory.html").read_text(encoding="utf-8")

    assert "Ingredients &amp; Stock" in admin and "Ingredients &amp; Stock" in staff
    assert "Out of stock" in admin and "Out of stock" in staff
    assert "InventoryUI.actions(item)" not in admin
    assert "InventoryUI.actions(item)" not in staff
    assert "InventoryUI.mealActions(item)" in admin and "InventoryUI.mealActions(item)" in staff
    assert "onclick=\"InventoryUI.openServings()\"" not in admin + staff


def test_staff_inventory_uses_current_script_and_loads_empty_snapshot(app):
    client = app.test_client()
    with client.session_transaction() as auth:
        auth.update(user_id=1, username="test_user", role="staff", last_activity=time())
    page = client.get("/inventory")
    assert page.status_code == 200
    script = (Path(app.static_folder) / "js" / "inventory-workflow.js").read_bytes()
    version = sha256(script).hexdigest()[:12]
    assert f"/static/js/inventory-workflow.js?v={version}".encode() in page.data
    deployed_script = client.get(
        f"/static/js/inventory-workflow.js?v={version}"
    )
    assert b"function setMeals(rows)" in deployed_script.data
    assert b"return {actions,status,open,openServings,openMealHistory,setMeals" in deployed_script.data
    assert deployed_script.headers["Cache-Control"] == "public, no-cache, must-revalidate"
    snapshot = client.get("/inventory/api/dashboard-items")
    assert snapshot.status_code == 200
    assert snapshot.get_json()["success"] is True
    assert snapshot.get_json()["direct_stock"] == []


def test_owner_inventory_renders_per_meal_dialogs(app):
    with app.app_context():
        owner = db.session.get(User, 1)
        owner.role = "admin"
        db.session.commit()
    client = app.test_client()
    with client.session_transaction() as auth:
        auth.update(user_id=1, username="test_user", role="admin", last_activity=time())
    page = client.get("/admin/inventory")
    assert page.status_code == 200
    assert b'id="servings-meal-name"' in page.data
    assert b'id="meal-history-dialog"' in page.data
    assert b'<select id="servings-meal"' not in page.data


def test_add_ingredient_form_uses_plain_language_and_keeps_fractional_stock():
    admin = (TEMPLATES / "admin" / "inventory.html").read_text(encoding="utf-8")

    assert "How much do you have now?" in admin
    assert 'id="startQty" class="form-control" value="0" min="0" max="999999" step="0.01"' in admin
    assert "Remind me to restock when this much is left" in admin
    assert "const startQty = Number(stockInput.value);" in admin


def test_add_menu_item_has_no_recipe_fields_and_stock_forms_show_units():
    menu = (TEMPLATES / "admin" / "menu.html").read_text(encoding="utf-8")
    admin = (TEMPLATES / "admin" / "inventory.html").read_text(encoding="utf-8")
    staff = (TEMPLATES / "staff" / "inventory.html").read_text(encoding="utf-8")
    add_form = menu.split('id="addItemModal"', 1)[1].split('id="editItemModal"', 1)[0]
    assert "Ingredients for one order" not in add_form
    assert "newRecipeRows" not in menu
    assert all(f'id="{field}"' in add_form for field in ("itemName", "category", "price", "description", "image"))
    assert 'id="adjustUnit"' in admin
    assert 'id="raw-stock-unit"' in staff
    assert "Unit measurements" in admin and "Unit measurements" in staff
    assert 'id="adjustConversionRatio"' in admin and 'id="raw-stock-conversion"' in staff
    reasons = admin.split('id="reason"', 1)[1].split('</select>', 1)[0]
    assert all(f'value="{reason}"' in reasons for reason in ("Restock", "Damaged", "Expired"))
    assert 'value="Inventory count"' not in reasons and 'value="Other"' not in reasons


def test_inventory_meal_cards_only_show_servings_and_availability():
    menu = (TEMPLATES / "admin" / "menu.html").read_text(encoding="utf-8")
    inventory = (TEMPLATES / "admin" / "inventory.html").read_text(encoding="utf-8")
    controls = (TEMPLATES / "inventory_controls.html").read_text(encoding="utf-8")
    workflow = (Path(__file__).resolve().parents[1] / "static" / "js" / "inventory-workflow.js").read_text(encoding="utf-8")

    assert 'id="inventoryMode"' not in menu
    assert 'id="editInventoryMode"' not in menu
    assert "stock_quantity'," not in menu
    card = inventory.split("function renderRecipeInventory()", 1)[1].split("function viewLogsOrInit", 1)[0]
    assert "InventoryUI.actions(item)" not in card
    assert "InventoryUI.mealActions(item)" in card
    assert "Advanced recipe tracking" not in card
    assert "Edit ingredients" not in card
    assert "Remove recipe" not in card
    assert "setupReviewFilter" in inventory
    assert "stock-mode" in controls and "stock-threshold" in controls
    assert "button('setup'" not in workflow
    assert all(f"button('{action}'" in workflow for action in ("add", "waste", "sold_out", "count"))
    assert "item.available_quantity + ' ' + item.display_unit" in card
    assert "InventoryUI.status(item)" in card
    assert 'id="meal-history-dialog"' in controls
    assert 'id="servings-meal-name"' in controls and '<select id="servings-meal"' not in controls
    assert all(f"'{unit}'" in workflow for unit in ("klg", "grams", "pieces", "packs", "trays", "liters", "ml"))
