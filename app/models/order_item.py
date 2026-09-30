from app import db

class OrderItem(db.Model):
    __tablename__ = "order_items"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    menu_item_id = db.Column(db.Integer, db.ForeignKey("menu_items.id", ondelete="SET NULL"), nullable=True)

    quantity = db.Column(db.Integer, default=1)
    price = db.Column(db.Numeric(10,2))
    name_snapshot = db.Column(db.String(100), nullable=True)
    base_price = db.Column(db.Numeric(10,2), nullable=True)
    no_rice = db.Column(db.Boolean, default=False, nullable=False)
    no_egg = db.Column(db.Boolean, default=False, nullable=False)
    unit_deduction = db.Column(db.Numeric(10,2), default=0, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="preparing")

    order = db.relationship("Order", backref="items")
    menu_item = db.relationship("MenuItem")

    @property
    def display_name(self):
        name = self.name_snapshot or (self.menu_item.name if self.menu_item else "Unknown Item")
        choices = [label for selected, label in ((self.no_rice, "No rice"), (self.no_egg, "No egg")) if selected]
        return f"{name} ({', '.join(choices)})" if choices else name
