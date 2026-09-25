from hashlib import sha256
from pathlib import Path
from time import time

import pytest

from app import create_app


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
    assert "Set available servings" in admin and "Set available servings" in staff


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
    assert b"return {actions,status,open,openServings,setMeals" in deployed_script.data
    assert deployed_script.headers["Cache-Control"] == "public, no-cache, must-revalidate"
    snapshot = client.get("/inventory/api/dashboard-items")
    assert snapshot.status_code == 200
    assert snapshot.get_json()["success"] is True
    assert snapshot.get_json()["direct_stock"] == []


def test_add_ingredient_form_uses_plain_language_and_keeps_fractional_stock():
    admin = (TEMPLATES / "admin" / "inventory.html").read_text(encoding="utf-8")

    assert "How much do you have now?" in admin
    assert 'id="startQty" class="form-control" value="0" min="0" max="999999" step="0.01"' in admin
    assert "Remind me to restock when this much is left" in admin
    assert "const startQty = Number(stockInput.value);" in admin


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
    assert "History</button>" not in card
    assert "Advanced recipe tracking" not in card
    assert "Edit ingredients" not in card
    assert "Remove recipe" not in card
    assert "setupReviewFilter" in inventory
    assert "stock-mode" in controls and "stock-threshold" in controls
    assert "button('setup'" not in workflow
    assert all(f"button('{action}'" in workflow for action in ("add", "waste", "sold_out", "count"))
    assert "item.available_quantity + ' ' + item.display_unit" in card
    assert "InventoryUI.status(item)" in card
