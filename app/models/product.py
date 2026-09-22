from datetime import datetime, timezone

from sqlalchemy.orm import validates

from app.extensions import db


class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey("shops.id"), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"))
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    stock_quantity = db.Column(db.Integer, nullable=False, default=0)
    image = db.Column(db.String(255))  # file name inside static/uploads/products
    is_available = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    shop = db.relationship("Shop", back_populates="products")
    category = db.relationship("Category", back_populates="products")
    reviews = db.relationship("Review", back_populates="product")

    @property
    def in_stock(self):
        return self.stock_quantity > 0

    @property
    def review_count(self):
        return len(self.reviews)

    @property
    def average_rating(self):
        """Average of all review ratings, or None when nobody has reviewed yet."""
        if not self.reviews:
            return None
        return sum(review.rating for review in self.reviews) / len(self.reviews)

    @validates("price")
    def validate_price(self, key, value):
        if value is None or float(value) < 0:
            raise ValueError("Price cannot be negative")
        return value

    @validates("stock_quantity")
    def validate_stock(self, key, value):
        if value is None or value < 0:
            raise ValueError("Stock cannot be negative")
        return value

    def __repr__(self):
        return f"<Product {self.name}>"
