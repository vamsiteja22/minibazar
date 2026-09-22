"""Everything the admin can do: statistics, users, shop approval, categories, orders.

Every function here is called only from routes that require the admin role.
"""
from sqlalchemy import func, or_

from app.extensions import db
from app.models.category import Category
from app.models.delivery import Delivery
from app.models.order import ORDER_STATUSES, Order, OrderItem
from app.models.product import Product
from app.models.shop import Shop
from app.models.user import ROLE_ADMIN, ROLE_CUSTOMER, ROLE_DELIVERY, ROLE_SHOPKEEPER, User
from app.services import delivery_service, order_service

MANAGED_ROLES = (ROLE_CUSTOMER, ROLE_SHOPKEEPER, ROLE_DELIVERY)
MAX_ROWS = 200  # keeps list pages small


class AdminError(ValueError):
    """A problem to show to the admin (its text is a friendly message)."""


# ---- statistics ---------------------------------------------------------------------
def platform_stats():
    role_counts = dict(db.session.query(User.role, func.count(User.id)).group_by(User.role).all())
    status_counts = dict(db.session.query(Order.status, func.count(Order.id)).group_by(Order.status).all())
    delivered_sales = (
        db.session.query(func.coalesce(func.sum(OrderItem.price_at_purchase * OrderItem.quantity), 0))
        .join(Order, Order.id == OrderItem.order_id)
        .filter(Order.status == "delivered")
        .scalar()
    )
    return {
        "users_total": sum(role_counts.values()),
        "customers": role_counts.get(ROLE_CUSTOMER, 0),
        "shopkeepers": role_counts.get(ROLE_SHOPKEEPER, 0),
        "partners": role_counts.get(ROLE_DELIVERY, 0),
        "admins": role_counts.get(ROLE_ADMIN, 0),
        "shops_total": Shop.query.count(),
        "shops_approved": Shop.query.filter_by(is_approved=True).count(),
        "shops_pending": Shop.query.filter(Shop.is_approved.is_(False), Shop.rejection_reason.is_(None)).count(),
        "shops_rejected": Shop.query.filter(Shop.is_approved.is_(False), Shop.rejection_reason.isnot(None)).count(),
        "products_total": Product.query.count(),
        "products_available": Product.query.filter_by(is_available=True).count(),
        "orders_total": sum(status_counts.values()),
        "orders_by_status": {status: status_counts.get(status, 0) for status in ORDER_STATUSES},
        "orders_active": sum(count for status, count in status_counts.items()
                             if status not in order_service.FINISHED_STATUSES),
        "delivered_sales": delivered_sales,
        "deliveries_active": Delivery.query.filter(
            Delivery.status.in_(delivery_service.ACTIVE_STATUSES)).count(),
        "needs_partner": len(delivery_service.eligible_orders()),
    }


# ---- users ------------------------------------------------------------------------------
def list_users(role=None, text=None):
    """Customers, shopkeepers and delivery partners (admins are managed with the terminal command)."""
    query = User.query.filter(User.role.in_(MANAGED_ROLES))
    if role in MANAGED_ROLES:
        query = query.filter(User.role == role)
    text = (text or "").strip()
    if text:
        like = f"%{text.replace('%', '').replace('_', '')}%"
        query = query.filter(or_(User.name.ilike(like), User.email.ilike(like)))
    return query.order_by(User.created_at.desc(), User.id.desc()).limit(MAX_ROWS).all()


def get_manageable_user_or_none(user_id):
    user = db.session.get(User, user_id)
    return user if user is not None and user.role in MANAGED_ROLES else None


def deactivate_user(user):
    """Stop a user from logging in. A deactivated shopkeeper's shop is taken off the site."""
    if user.role not in MANAGED_ROLES:
        raise AdminError("Admin accounts cannot be managed here.")
    if not user.is_active:
        raise AdminError(f"{user.name} is already deactivated.")
    if user.role == ROLE_DELIVERY and delivery_service.active_count(user.id):
        raise AdminError(
            f"{user.name} has deliveries in progress. Wait until they are finished before deactivating."
        )
    user.is_active = False
    if user.role == ROLE_SHOPKEEPER and user.shop is not None:
        user.shop.is_approved = False
        user.shop.rejection_reason = "Owner account deactivated."
    db.session.commit()


def reactivate_user(user):
    if user.role not in MANAGED_ROLES:
        raise AdminError("Admin accounts cannot be managed here.")
    if user.is_active:
        raise AdminError(f"{user.name} is already active.")
    user.is_active = True  # a shop stays unapproved: approve it again on the Shops page
    db.session.commit()


# ---- shops ------------------------------------------------------------------------------
SHOP_FILTERS = {
    "all": "All",
    "pending": "Waiting for approval",
    "approved": "Approved",
    "rejected": "Rejected",
}


def list_shops(state="all"):
    query = Shop.query
    if state == "approved":
        query = query.filter(Shop.is_approved.is_(True))
    elif state == "pending":
        query = query.filter(Shop.is_approved.is_(False), Shop.rejection_reason.is_(None))
    elif state == "rejected":
        query = query.filter(Shop.is_approved.is_(False), Shop.rejection_reason.isnot(None))
    return query.order_by(Shop.created_at.desc(), Shop.id.desc()).limit(MAX_ROWS).all()


def approve_shop(shop):
    if not shop.owner.is_active:
        raise AdminError(f"{shop.owner.name}'s account is deactivated. Reactivate it first.")
    shop.is_approved = True
    shop.rejection_reason = None
    db.session.commit()


def reject_shop(shop, reason):
    reason = " ".join((reason or "").split())
    if not 5 <= len(reason) <= 255:
        raise AdminError("Please give a reason (5 to 255 characters) so the shopkeeper knows what to fix.")
    shop.is_approved = False
    shop.rejection_reason = reason
    db.session.commit()


# ---- categories -------------------------------------------------------------------------
def categories_with_counts():
    return (
        db.session.query(Category, func.count(Product.id))
        .outerjoin(Product, Product.category_id == Category.id)
        .group_by(Category.id)
        .order_by(Category.name)
        .all()
    )


def _clean_category_name(name, exclude_id=None):
    name = " ".join((name or "").split())
    if not 2 <= len(name) <= 80:
        raise AdminError("Category name must be 2 to 80 characters.")
    clash = Category.query.filter(func.lower(Category.name) == name.lower())
    if exclude_id:
        clash = clash.filter(Category.id != exclude_id)
    if clash.first():
        raise AdminError(f"A category called “{name}” already exists.")
    return name


def create_category(name):
    category = Category(name=_clean_category_name(name))
    db.session.add(category)
    db.session.commit()
    return category


def rename_category(category, name):
    category.name = _clean_category_name(name, exclude_id=category.id)
    db.session.commit()


def delete_category(category):
    in_use = Product.query.filter_by(category_id=category.id).count()
    if in_use:
        raise AdminError(
            f"“{category.name}” is used by {in_use} product{'' if in_use == 1 else 's'}, so it cannot be deleted."
        )
    db.session.delete(category)
    db.session.commit()


# ---- orders -----------------------------------------------------------------------------
ORDER_FILTERS = {
    "all": "All",
    "pending": "Pending",
    "needs_partner": "Needs a delivery partner",
    "active": "In progress",
    "delivered": "Delivered",
    "closed": "Rejected / cancelled",
}


def list_orders(filter_key="all"):
    if filter_key == "needs_partner":
        return delivery_service.eligible_orders()
    statuses = {
        "pending": order_service.FILTERS["pending"][1],
        "active": order_service.FILTERS["active"][1],
        "delivered": order_service.FILTERS["completed"][1],
        "closed": order_service.FILTERS["closed"][1],
    }.get(filter_key)
    query = Order.query
    if statuses:
        query = query.filter(Order.status.in_(statuses))
    return query.order_by(Order.created_at.desc(), Order.id.desc()).limit(MAX_ROWS).all()


def get_order_or_none(order_id):
    return db.session.get(Order, order_id)


# ---- delivery partners ------------------------------------------------------------------
def partner_rows():
    """One row per delivery partner with their workload."""
    rows = []
    for partner in User.query.filter_by(role=ROLE_DELIVERY).order_by(User.name, User.id).all():
        counts = delivery_service.partner_counts(partner)
        rows.append({
            "partner": partner,
            "active": delivery_service.active_count(partner.id),
            "delivered": counts["delivered"],
        })
    return rows
