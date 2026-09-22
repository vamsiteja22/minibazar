"""Admin pages. Every route requires the admin role (@role_required)."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.decorators import role_required
from app.extensions import db
from app.models.category import Category
from app.models.shop import Shop
from app.models.user import ROLE_ADMIN, User
from app.services import admin_service, delivery_service

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

admin_only = role_required(ROLE_ADMIN)


def _report(action):
    """Run an admin action; show its error (if any) as a message. Returns True on success."""
    try:
        action()
        return True
    except (admin_service.AdminError, delivery_service.DeliveryError) as error:
        flash(str(error), "error")
        return False


def _back_to(endpoint, **values):
    return redirect(url_for(endpoint, **values))


# ---- users ---------------------------------------------------------------------------
@admin_bp.route("/users")
@admin_only
def users():
    role = request.args.get("role", "")
    text = request.args.get("q", "")
    return render_template(
        "admin/users.html",
        users=admin_service.list_users(role or None, text),
        active_role=role if role in admin_service.MANAGED_ROLES else "",
        text=text,
    )


def _user_or_404(user_id):
    return admin_service.get_manageable_user_or_none(user_id) or abort(404)


@admin_bp.route("/users/<int:user_id>/deactivate", methods=["POST"])
@admin_only
def user_deactivate(user_id):
    user = _user_or_404(user_id)
    if _report(lambda: admin_service.deactivate_user(user)):
        flash(f"{user.name} was deactivated.", "success")
    return _back_to("admin.users", role=request.form.get("role", ""))


@admin_bp.route("/users/<int:user_id>/reactivate", methods=["POST"])
@admin_only
def user_reactivate(user_id):
    user = _user_or_404(user_id)
    if _report(lambda: admin_service.reactivate_user(user)):
        flash(f"{user.name} was reactivated.", "success")
    return _back_to("admin.users", role=request.form.get("role", ""))


# ---- shops ---------------------------------------------------------------------------
@admin_bp.route("/shops")
@admin_only
def shops():
    state = request.args.get("state", "pending")
    if state not in admin_service.SHOP_FILTERS:
        state = "pending"
    return render_template(
        "admin/shops.html",
        shops=admin_service.list_shops(state),
        filters=admin_service.SHOP_FILTERS,
        active_state=state,
    )


def _shop_or_404(shop_id):
    return db.session.get(Shop, shop_id) or abort(404)


@admin_bp.route("/shops/<int:shop_id>/approve", methods=["POST"])
@admin_only
def shop_approve(shop_id):
    shop = _shop_or_404(shop_id)
    if _report(lambda: admin_service.approve_shop(shop)):
        flash(f"“{shop.name}” is approved and now visible to customers.", "success")
    return _back_to("admin.shops", state=request.form.get("state", "pending"))


@admin_bp.route("/shops/<int:shop_id>/reject", methods=["POST"])
@admin_only
def shop_reject(shop_id):
    shop = _shop_or_404(shop_id)
    if _report(lambda: admin_service.reject_shop(shop, request.form.get("reason"))):
        flash(f"“{shop.name}” was rejected and is hidden from customers.", "success")
    return _back_to("admin.shops", state=request.form.get("state", "pending"))


# ---- categories ----------------------------------------------------------------------
@admin_bp.route("/categories", methods=["GET", "POST"])
@admin_only
def categories():
    if request.method == "POST":  # add a new category
        if _report(lambda: admin_service.create_category(request.form.get("name"))):
            flash("Category added.", "success")
        return _back_to("admin.categories")
    return render_template("admin/categories.html", rows=admin_service.categories_with_counts())


@admin_bp.route("/categories/<int:category_id>/rename", methods=["POST"])
@admin_only
def category_rename(category_id):
    category = db.session.get(Category, category_id) or abort(404)
    if _report(lambda: admin_service.rename_category(category, request.form.get("name"))):
        flash("Category renamed.", "success")
    return _back_to("admin.categories")


@admin_bp.route("/categories/<int:category_id>/delete", methods=["POST"])
@admin_only
def category_delete(category_id):
    category = db.session.get(Category, category_id) or abort(404)
    name = category.name
    if _report(lambda: admin_service.delete_category(category)):
        flash(f"Category “{name}” was deleted.", "success")
    return _back_to("admin.categories")


# ---- orders and delivery assignment ---------------------------------------------------
@admin_bp.route("/orders")
@admin_only
def orders():
    key = request.args.get("status", "all")
    if key not in admin_service.ORDER_FILTERS:
        key = "all"
    return render_template(
        "admin/orders.html",
        orders=admin_service.list_orders(key),
        filters=admin_service.ORDER_FILTERS,
        active_filter=key,
    )


def _order_or_404(order_id):
    return admin_service.get_order_or_none(order_id) or abort(404)


@admin_bp.route("/orders/<int:order_id>")
@admin_only
def order_detail(order_id):
    from app.services import order_service

    order = _order_or_404(order_id)
    return render_template(
        "admin/order_detail.html",
        order=order,
        subtotal=order_service.subtotal(order),
        delivery_fee=order_service.delivery_fee(order),
        partners=delivery_service.available_partners(),
        can_assign=order.status == "ready_for_pickup" and order.delivery is None,
        can_reassign=order.delivery is not None and order.delivery.status == "assigned",
        max_active=delivery_service.MAX_ACTIVE_DELIVERIES,
        steps=delivery_service.DELIVERY_STEPS,
        delivery_step=(delivery_service.DELIVERY_PROGRESS[order.delivery.status]
                       if order.delivery else None),
    )


@admin_bp.route("/orders/<int:order_id>/assign", methods=["POST"])
@admin_only
def order_assign(order_id):
    order = _order_or_404(order_id)
    partner_id = request.form.get("partner_id", "")
    partner = db.session.get(User, int(partner_id)) if partner_id.isdigit() else None

    def do_assign():
        if order.delivery is None:
            delivery_service.assign(order, partner)
        else:
            if partner is None:
                raise delivery_service.DeliveryError("Please choose a delivery partner.")
            delivery_service.reassign(order.delivery, partner)

    if _report(do_assign):
        flash(f"Order #{order.id} is assigned to {partner.name}.", "success")
    return _back_to("admin.order_detail", order_id=order.id)


# ---- delivery partners ----------------------------------------------------------------
@admin_bp.route("/delivery-partners")
@admin_only
def partners():
    return render_template("admin/partners.html", rows=admin_service.partner_rows(),
                           max_active=delivery_service.MAX_ACTIVE_DELIVERIES)
