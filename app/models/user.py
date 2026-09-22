from datetime import datetime, timezone

from flask_login import UserMixin
from sqlalchemy.orm import validates
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db

ROLE_CUSTOMER = "customer"
ROLE_SHOPKEEPER = "shopkeeper"
ROLE_DELIVERY = "delivery_partner"
ROLE_ADMIN = "admin"
ROLES = (ROLE_CUSTOMER, ROLE_SHOPKEEPER, ROLE_DELIVERY, ROLE_ADMIN)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default=ROLE_CUSTOMER)
    # An admin can deactivate an account: it can no longer log in.
    # (Overrides the always-True is_active that Flask-Login's UserMixin provides.)
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # A user may own one shop, have one cart, and place many orders.
    shop = db.relationship("Shop", back_populates="owner", uselist=False)
    cart = db.relationship("Cart", back_populates="customer", uselist=False)
    orders = db.relationship("Order", back_populates="customer")
    reviews = db.relationship("Review", back_populates="customer")
    deliveries = db.relationship("Delivery", back_populates="delivery_partner")

    @validates("email")
    def validate_email(self, key, value):
        value = (value or "").strip().lower()
        if "@" not in value:
            raise ValueError("Invalid email address")
        return value

    @validates("role")
    def validate_role(self, key, value):
        if value not in ROLES:
            raise ValueError(f"Role must be one of {ROLES}")
        return value

    def set_password(self, password):
        """Hash the password. The plain password is never stored."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.email} ({self.role})>"
