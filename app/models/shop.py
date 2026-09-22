from datetime import datetime, timezone

from app.extensions import db


class Shop(db.Model):
    __tablename__ = "shops"

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False
    )
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text)
    address = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(20))
    # Optional map position (decimal degrees). Used only for "shops near me".
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    # New shops wait for admin approval before customers can see them.
    is_approved = db.Column(db.Boolean, nullable=False, default=False)
    # Set when an admin rejects (or suspends) the shop; cleared on approval.
    rejection_reason = db.Column(db.String(255))
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    owner = db.relationship("User", back_populates="shop")
    products = db.relationship("Product", back_populates="shop")
    orders = db.relationship("Order", back_populates="shop")

    @property
    def has_location(self):
        return self.latitude is not None and self.longitude is not None

    @property
    def approval_state(self):
        """'approved', 'rejected' (an admin said no) or 'pending' (not reviewed yet)."""
        if self.is_approved:
            return "approved"
        return "rejected" if self.rejection_reason else "pending"

    def __repr__(self):
        return f"<Shop {self.name}>"
