from datetime import datetime, timezone

from sqlalchemy.orm import validates

from app.extensions import db

ORDER_PENDING = "pending"
ORDER_CONFIRMED = "confirmed"
ORDER_PREPARING = "preparing"
ORDER_READY = "ready_for_pickup"
ORDER_OUT_FOR_DELIVERY = "out_for_delivery"
ORDER_DELIVERED = "delivered"
ORDER_REJECTED = "rejected"  # the shopkeeper declined the order
ORDER_CANCELLED = "cancelled"
ORDER_STATUSES = (
    ORDER_PENDING,
    ORDER_CONFIRMED,
    ORDER_PREPARING,
    ORDER_READY,
    ORDER_OUT_FOR_DELIVERY,
    ORDER_DELIVERED,
    ORDER_REJECTED,
    ORDER_CANCELLED,
)

PAYMENT_PENDING = "pending"
PAYMENT_PAID = "paid"
PAYMENT_STATUSES = (PAYMENT_PENDING, PAYMENT_PAID)


class Order(db.Model):
    """One order belongs to exactly one shop (Version 1 rule)."""

    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    shop_id = db.Column(db.Integer, db.ForeignKey("shops.id"), nullable=False)
    total_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    delivery_address = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), nullable=False, default=ORDER_PENDING)
    payment_status = db.Column(db.String(20), nullable=False, default=PAYMENT_PENDING)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    customer = db.relationship("User", back_populates="orders")
    shop = db.relationship("Shop", back_populates="orders")
    items = db.relationship(
        "OrderItem", back_populates="order", cascade="all, delete-orphan"
    )
    delivery = db.relationship("Delivery", back_populates="order", uselist=False)

    @validates("status")
    def validate_status(self, key, value):
        if value not in ORDER_STATUSES:
            raise ValueError(f"Status must be one of {ORDER_STATUSES}")
        return value

    @validates("payment_status")
    def validate_payment_status(self, key, value):
        if value not in PAYMENT_STATUSES:
            raise ValueError(f"Payment status must be one of {PAYMENT_STATUSES}")
        return value


class OrderItem(db.Model):
    __tablename__ = "order_items"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    # Price copied at purchase time so later price changes do not alter old orders.
    price_at_purchase = db.Column(db.Numeric(10, 2), nullable=False)

    order = db.relationship("Order", back_populates="items")
    product = db.relationship("Product")

    @validates("quantity")
    def validate_quantity(self, key, value):
        if value is None or value < 1:
            raise ValueError("Quantity must be at least 1")
        return value
