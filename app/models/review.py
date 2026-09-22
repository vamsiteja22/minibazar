from datetime import datetime, timezone

from sqlalchemy.orm import validates

from app.extensions import db


class Review(db.Model):
    __tablename__ = "reviews"
    # A customer can review a given product only once.
    __table_args__ = (db.UniqueConstraint("customer_id", "product_id"),)

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    customer = db.relationship("User", back_populates="reviews")
    product = db.relationship("Product", back_populates="reviews")

    @validates("rating")
    def validate_rating(self, key, value):
        if value is None or not 1 <= value <= 5:
            raise ValueError("Rating must be between 1 and 5")
        return value
