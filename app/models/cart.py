from datetime import datetime, timezone

from sqlalchemy.orm import validates

from app.extensions import db


class Cart(db.Model):
    __tablename__ = "carts"

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False
    )
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    customer = db.relationship("User", back_populates="cart")
    items = db.relationship(
        "CartItem", back_populates="cart", cascade="all, delete-orphan"
    )


class CartItem(db.Model):
    __tablename__ = "cart_items"
    # The same product appears only once per cart (change its quantity instead).
    __table_args__ = (db.UniqueConstraint("cart_id", "product_id"),)

    id = db.Column(db.Integer, primary_key=True)
    cart_id = db.Column(db.Integer, db.ForeignKey("carts.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)

    cart = db.relationship("Cart", back_populates="items")
    product = db.relationship("Product")

    @validates("quantity")
    def validate_quantity(self, key, value):
        if value is None or value < 1:
            raise ValueError("Quantity must be at least 1")
        return value
