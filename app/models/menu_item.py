from datetime import datetime
from app import db

class MenuItem(db.Model):
    __tablename__ = "menu_items"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    price = db.Column(db.Numeric(10,2))
    category = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(20), default="active")
    is_available = db.Column(db.Boolean, default=True, nullable=False)
    image_url = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MenuItemIngredient(db.Model):
    __tablename__ = "menu_item_ingredients"

    id = db.Column(db.Integer, primary_key=True)
    menu_item_id = db.Column(db.Integer, db.ForeignKey("menu_items.id", ondelete="CASCADE"), nullable=False)
    ingredient_item_id = db.Column(db.Integer, db.ForeignKey("menu_items.id", ondelete="CASCADE"), nullable=False)
    quantity_required = db.Column(db.Numeric(10, 2), nullable=False, default=1.00)
    unit = db.Column(db.String(50), nullable=True)
    conversion_ratio = db.Column(db.Numeric(10, 4), nullable=False, default=1.0000)

    menu_item = db.relationship("MenuItem", foreign_keys=[menu_item_id], backref=db.backref("ingredients", cascade="all, delete-orphan"))
    ingredient = db.relationship("MenuItem", foreign_keys=[ingredient_item_id])