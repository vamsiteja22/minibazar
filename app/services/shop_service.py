"""Shop profile rules and the numbers shown on the shopkeeper dashboard."""
import re

from sqlalchemy import func

from app.extensions import db
from app.models.order import ORDER_DELIVERED, ORDER_PENDING, Order, OrderItem
from app.models.product import Product
from app.models.shop import Shop
from app.services import location_service

PHONE_PATTERN = re.compile(r"^(\+91)?[6-9]\d{9}$")


def validate_shop_form(form):
    """Return (cleaned_values, errors). Errors is a list of messages."""
    name = form.get("name", "").strip()
    address = form.get("address", "").strip()
    phone = re.sub(r"[\s-]", "", form.get("phone", ""))
    description = form.get("description", "").strip()

    errors = []
    if not 2 <= len(name) <= 120:
        errors.append("Shop name must be between 2 and 120 characters.")
    if not 5 <= len(address) <= 255:
        errors.append("Please enter the shop address (5 to 255 characters).")
    if phone and not PHONE_PATTERN.match(phone):
        errors.append("Phone must be a valid 10-digit mobile number.")
    if len(description) > 500:
        errors.append("Description can be at most 500 characters.")

    # Optional map position, used by "shops near me". Both blank means "no location".
    latitude = longitude = None
    try:
        latitude, longitude = location_service.parse_coordinates(
            form.get("latitude"), form.get("longitude")
        )
    except location_service.LocationError as error:
        errors.append(str(error))

    cleaned = {
        "name": name,
        "address": address,
        "phone": phone or None,
        "description": description or None,
        "latitude": latitude,
        "longitude": longitude,
    }
    return cleaned, errors


def create_shop(owner, cleaned):
    """Create the owner's shop. It starts unapproved (an admin approves it later)."""
    shop = Shop(owner=owner, **cleaned)
    db.session.add(shop)
    db.session.commit()
    return shop


def update_shop(shop, cleaned):
    for field, value in cleaned.items():
        setattr(shop, field, value)
    if not shop.is_approved and shop.rejection_reason:
        shop.rejection_reason = None  # edited after a rejection: back to "waiting for review"
    db.session.commit()
    return shop


def dashboard_stats(shop):
    """Numbers for the summary cards. Every query is limited to this shop."""
    product_count = Product.query.filter_by(shop_id=shop.id).count()
    available_count = Product.query.filter_by(shop_id=shop.id, is_available=True).count()
    pending = Order.query.filter_by(shop_id=shop.id, status=ORDER_PENDING).count()
    completed = Order.query.filter_by(shop_id=shop.id, status=ORDER_DELIVERED).count()

    # Sales = what the shop sold (item prices x quantities). The order total also
    # contains the delivery fee, which does not belong to the shop.
    total_sales = (
        db.session.query(
            func.coalesce(func.sum(OrderItem.price_at_purchase * OrderItem.quantity), 0)
        )
        .join(Order, Order.id == OrderItem.order_id)
        .filter(Order.shop_id == shop.id, Order.status == ORDER_DELIVERED)
        .scalar()
    )
    top_products = (
        db.session.query(Product.name, func.sum(OrderItem.quantity).label("sold"))
        .join(OrderItem, OrderItem.product_id == Product.id)
        .join(Order, Order.id == OrderItem.order_id)
        .filter(Order.shop_id == shop.id, Order.status == ORDER_DELIVERED)
        .group_by(Product.id)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(3)
        .all()
    )
    return {
        "total_products": product_count,
        "available_products": available_count,
        "pending_orders": pending,
        "completed_orders": completed,
        "total_sales": total_sales,
        "top_products": top_products,
    }
