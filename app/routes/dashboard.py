from flask import Blueprint, redirect, render_template, url_for
from flask_login import current_user, login_required

from app.decorators import role_required
from app.models.user import ROLE_ADMIN, ROLE_CUSTOMER, ROLE_DELIVERY, ROLE_SHOPKEEPER
from app.services import (
    admin_service,
    auth_service,
    cart_service,
    catalog_service,
    inventory_service,
    order_service,
    shop_service,
)

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")


@dashboard_bp.route("/")
@login_required
def index():
    """Send the logged-in user to the dashboard that matches their role."""
    return redirect(url_for(auth_service.dashboard_endpoint(current_user)))


@dashboard_bp.route("/customer")
@role_required(ROLE_CUSTOMER)
def customer():
    orders = order_service.customer_orders(current_user)
    active = [o for o in orders if o.status not in order_service.FINISHED_STATUSES]
    return render_template(
        "dashboard/customer.html",
        orders=orders,
        active_order=active[0] if active else None,
        steps=order_service.PROGRESS_STEPS,
        progress_index=order_service.PROGRESS_INDEX,
        stats={
            "total_orders": len(orders),
            "active_orders": len(active),
            "cart_items": cart_service.item_count(current_user),
        },
        suggestions=catalog_service.popular_products(limit=4),
    )


@dashboard_bp.route("/shopkeeper")
@role_required(ROLE_SHOPKEEPER)
def shopkeeper():
    shop = current_user.shop
    return render_template(
        "shopkeeper/dashboard.html",
        shop=shop,
        stats=shop_service.dashboard_stats(shop) if shop else None,
        recent_orders=order_service.shop_orders(shop)[:5] if shop else [],
        low_stock=inventory_service.low_stock_products(shop) if shop else None,
        low_threshold=inventory_service.threshold(),
    )


@dashboard_bp.route("/delivery")
@role_required(ROLE_DELIVERY)
def delivery():
    from app.routes.delivery import dashboard_context

    return render_template("delivery/dashboard.html", **dashboard_context())


@dashboard_bp.route("/admin")
@role_required(ROLE_ADMIN)
def admin():
    return render_template(
        "admin/dashboard.html",
        stats=admin_service.platform_stats(),
        status_labels=order_service.STATUS_LABELS,
    )
