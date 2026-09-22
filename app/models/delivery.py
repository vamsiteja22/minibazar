from datetime import datetime, timezone

from sqlalchemy.orm import validates

from app.extensions import db

DELIVERY_ASSIGNED = "assigned"          # an admin picked a partner
DELIVERY_ACCEPTED = "accepted"          # the partner took the job
DELIVERY_PICKED_UP = "picked_up"        # the partner collected it from the shop
DELIVERY_OUT = "out_for_delivery"       # on the way to the customer
DELIVERY_DELIVERED = "delivered"
DELIVERY_STATUSES = (
    DELIVERY_ASSIGNED,
    DELIVERY_ACCEPTED,
    DELIVERY_PICKED_UP,
    DELIVERY_OUT,
    DELIVERY_DELIVERED,
)


class Delivery(db.Model):
    __tablename__ = "deliveries"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(
        db.Integer, db.ForeignKey("orders.id"), unique=True, nullable=False
    )
    delivery_partner_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    status = db.Column(db.String(20), nullable=False, default=DELIVERY_ASSIGNED)
    assigned_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    delivered_at = db.Column(db.DateTime)  # stays empty until delivered

    order = db.relationship("Order", back_populates="delivery")
    delivery_partner = db.relationship("User", back_populates="deliveries")

    @validates("status")
    def validate_status(self, key, value):
        if value not in DELIVERY_STATUSES:
            raise ValueError(f"Status must be one of {DELIVERY_STATUSES}")
        return value
