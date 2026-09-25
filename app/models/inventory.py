from datetime import datetime
from app import db


class InventoryItem(db.Model):
    __tablename__ = "inventory_items"

    id = db.Column(db.Integer, primary_key=True)
    menu_item_id = db.Column(db.Integer, db.ForeignKey("menu_items.id"), nullable=False)
    stock_qty = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    low_stock_threshold = db.Column(db.Integer, nullable=False, default=10)
    unit = db.Column(db.String(50), nullable=False, default="pieces")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    menu_item = db.relationship("MenuItem", backref="inventory_item")


class InventoryLog(db.Model):
    __tablename__ = "inventory_logs"

    id = db.Column(db.Integer, primary_key=True)
    inventory_item_id = db.Column(
        db.Integer, db.ForeignKey("inventory_items.id"), nullable=False
    )
    change_qty = db.Column(db.Numeric(10, 2), nullable=False)
    reason = db.Column(db.String(100), nullable=False)
    changed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    changed_by_user = db.relationship("User", backref="inventory_logs")


class OrderInventoryAllocation(db.Model):
    __tablename__ = "order_inventory_allocations"

    id = db.Column(db.Integer, primary_key=True)
    # Snapshot IDs deliberately survive deletion of a fully voided order item.
    order_id = db.Column(db.Integer, nullable=False, index=True)
    order_item_id = db.Column(db.Integer, nullable=False, index=True)
    menu_item_id = db.Column(db.Integer, nullable=True, index=True)
    inventory_item_id = db.Column(db.Integer, db.ForeignKey("inventory_items.id"), nullable=False)
    inventory_mode = db.Column(db.String(16), nullable=False)
    unit = db.Column(db.String(50), nullable=False)
    quantity_per_unit = db.Column(db.Numeric(10, 2), nullable=False)
    ordered_units = db.Column(db.Integer, nullable=True)
    quantity_deducted = db.Column(db.Numeric(10, 2), nullable=False)
    quantity_restored = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class InventoryAction(db.Model):
    """Durable audit and retry key for setup, kitchen movements and voids."""
    __tablename__ = "inventory_actions"

    id = db.Column(db.Integer, primary_key=True)
    request_key = db.Column(db.String(200), unique=True, nullable=False)
    menu_item_id = db.Column(db.Integer, nullable=False, index=True)
    order_item_id = db.Column(db.Integer, nullable=True)
    item_name = db.Column(db.String(100), nullable=False)
    action = db.Column(db.String(32), nullable=False)
    quantity = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    reason = db.Column(db.String(200), nullable=False)
    changed_by = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
