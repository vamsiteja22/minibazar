"""Shopkeeper module: shop profile, product management and incoming orders.

Authorization (two layers on every route):
1. @role_required / @shop_required  -> only shopkeepers who own a shop get in.
2. Every lookup is filtered by the logged-in user's own shop, so an id that
   belongs to another shop is simply "not found" (404).
"""
from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user

from app.decorators import role_required, shop_required
from app.extensions import db
from app.models.product import Product
from app.models.user import ROLE_SHOPKEEPER
from app.services import (
    analytics_service,
    inventory_service,
    order_service,
    product_service,
    shop_service,
)

shopkeeper_bp = Blueprint("shopkeeper", __name__, url_prefix="/shopkeeper")


# ---- shop profile ------------------------------------------------------------
@shopkeeper_bp.route("/shop")
@shop_required
def shop_profile():
    return render_template("shopkeeper/shop_profile.html", shop=current_user.shop)


@shopkeeper_bp.route("/shop/create", methods=["GET", "POST"])
@role_required(ROLE_SHOPKEEPER)
def shop_create():
    if current_user.shop is not None:
        return redirect(url_for("shopkeeper.shop_profile"))

    values = request.form
    if request.method == "POST":
        cleaned, errors = shop_service.validate_shop_form(request.form)
        if errors:
            for message in errors:
                flash(message, "error")
        else:
            shop_service.create_shop(current_user, cleaned)
            flash("Your shop has been created. Now add your first product!", "success")
            return redirect(url_for("shopkeeper.product_new"))
    return render_template("shopkeeper/shop_form.html", values=values, editing=False)


@shopkeeper_bp.route("/shop/edit", methods=["GET", "POST"])
@shop_required
def shop_edit():
    shop = current_user.shop
    values = shop
    if request.method == "POST":
        values = request.form
        cleaned, errors = shop_service.validate_shop_form(request.form)
        if errors:
            for message in errors:
                flash(message, "error")
        else:
            shop_service.update_shop(shop, cleaned)
            flash("Shop details updated.", "success")
            return redirect(url_for("shopkeeper.shop_profile"))
    return render_template("shopkeeper/shop_form.html", values=values, editing=True)


# ---- products ----------------------------------------------------------------
def _load_product_or_404(product_id):
    product = product_service.get_shop_product_or_none(current_user.shop, product_id)
    if product is None:
        abort(404)  # missing OR belongs to another shop - same answer on purpose
    return product


@shopkeeper_bp.route("/products")
@shop_required
def products():
    only_low = request.args.get("stock") == "low"
    query = (
        inventory_service.low_stock_query(current_user.shop)
        if only_low
        else Product.query.filter_by(shop_id=current_user.shop.id)
    )
    items = query.order_by(Product.created_at.desc(), Product.id.desc()).all()
    return render_template(
        "shopkeeper/products.html",
        products=items,
        only_low=only_low,
        low_threshold=inventory_service.threshold(),
        low_count=inventory_service.low_stock_count(current_user.shop),
    )


@shopkeeper_bp.route("/products/new", methods=["GET", "POST"])
@shop_required
def product_new():
    values = request.form
    if request.method == "POST":
        cleaned, image_file, errors = product_service.validate_product_form(
            request.form, request.files
        )
        if errors:
            for message in errors:
                flash(message, "error")
        else:
            product_service.create_product(current_user.shop, cleaned, image_file)
            flash("Product added.", "success")
            return redirect(url_for("shopkeeper.products"))
    elif not values:
        values = {"is_available": "on", "stock_quantity": "0"}
    return render_template(
        "shopkeeper/product_form.html",
        values=values,
        product=None,
        categories=product_service.category_choices(),
    )


@shopkeeper_bp.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
@shop_required
def product_edit(product_id):
    product = _load_product_or_404(product_id)
    values = {
        "name": product.name,
        "description": product.description or "",
        "price": product.price,
        "stock_quantity": product.stock_quantity,
        "category_id": product.category_id,
        "is_available": "on" if product.is_available else "",
    }
    if request.method == "POST":
        values = request.form
        cleaned, image_file, errors = product_service.validate_product_form(
            request.form, request.files
        )
        if errors:
            for message in errors:
                flash(message, "error")
        else:
            product_service.update_product(
                product, cleaned, image_file,
                remove_image=request.form.get("remove_image") == "on",
            )
            flash("Product updated.", "success")
            return redirect(url_for("shopkeeper.products"))
    return render_template(
        "shopkeeper/product_form.html",
        values=values,
        product=product,
        categories=product_service.category_choices(),
    )


@shopkeeper_bp.route("/products/<int:product_id>/delete", methods=["POST"])
@shop_required
def product_delete(product_id):
    product = _load_product_or_404(product_id)
    name = product.name
    if product_service.delete_product(product):
        flash(f"“{name}” was deleted.", "success")
    else:
        flash(
            f"“{name}” is part of past orders, so it was hidden from customers "
            "instead of being deleted.",
            "success",
        )
    return redirect(url_for("shopkeeper.products"))


@shopkeeper_bp.route("/products/<int:product_id>/toggle", methods=["POST"])
@shop_required
def product_toggle(product_id):
    product = _load_product_or_404(product_id)
    product.is_available = not product.is_available
    db.session.commit()
    state = "available" if product.is_available else "unavailable"
    flash(f"“{product.name}” is now {state}.", "success")
    return redirect(url_for("shopkeeper.products"))


@shopkeeper_bp.route("/products/<int:product_id>/quick-update", methods=["POST"])
@shop_required
def product_quick_update(product_id):
    """Change only price and stock from the product list."""
    product = _load_product_or_404(product_id)
    price, price_error = product_service.parse_price(request.form.get("price"))
    stock, stock_error = product_service.parse_stock(request.form.get("stock_quantity"))
    errors = [e for e in (price_error, stock_error) if e]
    if errors:
        for message in errors:
            flash(f"{product.name}: {message}", "error")
    else:
        product.price = price
        product.stock_quantity = stock
        db.session.commit()
        flash(f"“{product.name}” price and stock updated.", "success")
    return redirect(url_for("shopkeeper.products"))


# ---- analytics -----------------------------------------------------------------
@shopkeeper_bp.route("/analytics")
@shop_required
def analytics():
    days = analytics_service.parse_period(request.args.get("days"))
    return render_template(
        "shopkeeper/analytics.html",
        report=analytics_service.sales_report(current_user.shop, days),
        period_options=analytics_service.PERIOD_OPTIONS,
        days=days,
    )


# ---- orders ------------------------------------------------------------------
@shopkeeper_bp.route("/orders")
@shop_required
def orders():
    shop = current_user.shop
    filter_key = request.args.get("status", "all")
    if filter_key not in order_service.FILTERS:
        filter_key = "all"
    return render_template(
        "shopkeeper/orders.html",
        orders=order_service.shop_orders(shop, filter_key),
        filters=order_service.FILTERS,
        counts=order_service.filter_counts(shop),
        active_filter=filter_key,
        actions_for=lambda order: order_service.available_actions(order, order_service.ACTOR_SHOPKEEPER),
    )


@shopkeeper_bp.route("/orders/<int:order_id>")
@shop_required
def order_detail(order_id):
    order = order_service.get_shop_order_or_none(current_user.shop, order_id) or abort(404)
    return render_template(
        "shopkeeper/order_detail.html",
        order=order,
        subtotal=order_service.subtotal(order),
        delivery_fee=order_service.delivery_fee(order),
        actions=order_service.available_actions(order, order_service.ACTOR_SHOPKEEPER),
        steps=order_service.PROGRESS_STEPS,
        step_index=order_service.PROGRESS_INDEX.get(order.status),
    )


@shopkeeper_bp.route("/orders/<int:order_id>/<action>", methods=["POST"])
@shop_required
def order_action(order_id, action):
    order = order_service.get_shop_order_or_none(current_user.shop, order_id) or abort(404)
    try:
        message = order_service.apply_action(order, action, order_service.ACTOR_SHOPKEEPER)
        flash(message, "success")
    except ValueError as error:
        flash(str(error), "error")
    return redirect(url_for("shopkeeper.order_detail", order_id=order.id))
