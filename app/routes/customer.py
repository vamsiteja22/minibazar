"""Customer-only pages: the cart, checkout, order confirmation and order history.

Authorization: every route needs a logged-in CUSTOMER, and the cart is always
taken from `current_user` - the browser never says "which cart", so nobody can
reach another customer's cart. Cart items are loaded through
cart_service.get_item_or_none(), which only finds items in the caller's own cart.
Orders work the same way: they are loaded through
order_service.get_customer_order_or_none(), which only finds the caller's own orders
(anything else is a 404).
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

from app.decorators import role_required
from app.models.user import ROLE_CUSTOMER
from app.services import (
    auth_service,
    cart_service,
    catalog_service,
    checkout_service,
    order_service,
    review_service,
)

customer_bp = Blueprint("customer", __name__)


def _go_back(default_endpoint="customer.cart"):
    """Redirect to the page the customer came from (only local paths), else the cart."""
    target = request.form.get("next")
    if auth_service.is_safe_redirect(target):
        return redirect(target)
    return redirect(url_for(default_endpoint))


def _visible_product_from_form():
    """The product named in the form, or None if it doesn't exist / isn't visible."""
    product_id = request.form.get("product_id", "")
    if not product_id.isdigit():
        return None
    return catalog_service.get_visible_product(int(product_id))


# ---- cart page ---------------------------------------------------------------
@customer_bp.route("/cart")
@role_required(ROLE_CUSTOMER)
def cart():
    return render_template("customer/cart.html", cart=cart_service.summary(current_user))


# ---- cart actions (all POST) -------------------------------------------------
@customer_bp.route("/cart/add", methods=["POST"])
@role_required(ROLE_CUSTOMER)
def cart_add():
    product = _visible_product_from_form()
    if product is None:
        flash("Sorry, that product is not available.", "error")
        return _go_back("shop.product_list")

    try:
        quantity = cart_service.parse_quantity(request.form.get("quantity", "1"))
        cart_service.add_item(current_user, product, quantity)
    except cart_service.ShopConflict as conflict:
        # Don't mix shops silently: ask the customer what to do.
        return render_template(
            "customer/cart_conflict.html",
            conflict=conflict,
            quantity=quantity,
            next_url=request.form.get("next", ""),
        ), 409
    except cart_service.CartError as error:
        flash(str(error), "error")
        return _go_back()  # back to the page they were on, so they can adjust

    flash(f"Added {quantity} × {product.name} to your cart.", "success")
    return _go_back()


@customer_bp.route("/cart/replace", methods=["POST"])
@role_required(ROLE_CUSTOMER)
def cart_replace():
    """After a shop conflict: clear the old cart and start a new one with this product."""
    product = _visible_product_from_form()
    if product is None:
        flash("Sorry, that product is not available.", "error")
        return redirect(url_for("customer.cart"))
    try:
        quantity = cart_service.parse_quantity(request.form.get("quantity", "1"))
        cart_service.replace_cart_with(current_user, product, quantity)
    except cart_service.CartError as error:
        flash(str(error), "error")
        return redirect(url_for("customer.cart"))
    flash(f"Started a new cart with {quantity} × {product.name}.", "success")
    return redirect(url_for("customer.cart"))


@customer_bp.route("/cart/items/<int:item_id>/update", methods=["POST"])
@role_required(ROLE_CUSTOMER)
def cart_update(item_id):
    try:
        quantity = cart_service.parse_quantity(request.form.get("quantity"))
        cart_service.set_quantity(current_user, item_id, quantity)
        flash("Quantity updated.", "success")
    except LookupError:
        abort(404)  # not in THIS customer's cart
    except cart_service.CartError as error:
        flash(str(error), "error")
    return redirect(url_for("customer.cart"))


@customer_bp.route("/cart/items/<int:item_id>/remove", methods=["POST"])
@role_required(ROLE_CUSTOMER)
def cart_remove(item_id):
    try:
        name = cart_service.remove_item(current_user, item_id)
    except LookupError:
        abort(404)
    flash(f"Removed {name} from your cart.", "success")
    return redirect(url_for("customer.cart"))


@customer_bp.route("/cart/clear", methods=["POST"])
@role_required(ROLE_CUSTOMER)
def cart_clear():
    cart_service.clear_cart(current_user)
    flash("Your cart is now empty.", "success")
    return redirect(url_for("customer.cart"))


# ---- checkout ------------------------------------------------------------------
def _checkout_values():
    """What to show in the form: what the customer typed, or sensible defaults."""
    if request.method == "POST":
        return request.form
    return {"full_name": current_user.name}


@customer_bp.route("/checkout", methods=["GET", "POST"])
@role_required(ROLE_CUSTOMER)
def checkout():
    summary = cart_service.summary(current_user)
    if summary["is_empty"]:
        flash("Your cart is empty. Add something before checking out.", "error")
        return redirect(url_for("customer.cart"))
    if summary["has_problems"]:
        flash("Please fix the highlighted items in your cart first.", "error")
        return redirect(url_for("customer.cart"))

    if request.method == "POST":
        cleaned, errors = checkout_service.validate_checkout_form(request.form)
        if errors:
            for message in errors:
                flash(message, "error")
        else:
            try:
                # Only the delivery details come from the browser. The amount is
                # worked out again on the server; "expected_total" just catches price changes.
                order = checkout_service.place_order(
                    current_user, cleaned, expected_total=request.form.get("expected_total")
                )
            except checkout_service.CheckoutError as error:
                flash(str(error), "error")
                target = "customer.cart" if error.go_to_cart else "customer.checkout"
                return redirect(url_for(target))
            return redirect(url_for("customer.order_confirmation", order_id=order.id))

    return render_template("customer/checkout.html", cart=summary, values=_checkout_values())


# ---- orders --------------------------------------------------------------------
def _own_order_or_404(order_id):
    return order_service.get_customer_order_or_none(current_user, order_id) or abort(404)


def _order_page(template, order, **extra):
    return render_template(
        template,
        order=order,
        subtotal=order_service.subtotal(order),
        delivery_fee=order_service.delivery_fee(order),
        steps=order_service.PROGRESS_STEPS,
        step_index=order_service.PROGRESS_INDEX.get(order.status),
        actions=order_service.available_actions(order, order_service.ACTOR_CUSTOMER),
        **extra,
    )


@customer_bp.route("/orders")
@role_required(ROLE_CUSTOMER)
def orders():
    return render_template(
        "customer/orders.html",
        orders=order_service.customer_orders(current_user),
        steps=order_service.PROGRESS_STEPS,
        progress_index=order_service.PROGRESS_INDEX,
    )


@customer_bp.route("/orders/<int:order_id>")
@role_required(ROLE_CUSTOMER)
def order_detail(order_id):
    return _order_page("customer/order_detail.html", _own_order_or_404(order_id))


@customer_bp.route("/orders/<int:order_id>/confirmation")
@role_required(ROLE_CUSTOMER)
def order_confirmation(order_id):
    return _order_page("customer/order_confirmation.html", _own_order_or_404(order_id))


@customer_bp.route("/orders/<int:order_id>/cancel", methods=["POST"])
@role_required(ROLE_CUSTOMER)
def order_cancel(order_id):
    order = _own_order_or_404(order_id)
    try:
        flash(order_service.apply_action(order, "cancel", order_service.ACTOR_CUSTOMER), "success")
    except ValueError as error:
        flash(str(error), "error")
    return redirect(url_for("customer.order_detail", order_id=order.id))


# ---- product reviews -----------------------------------------------------------
def _reviewable_product_or_404(product_id):
    return catalog_service.get_visible_product(product_id) or abort(404)


@customer_bp.route("/products/<int:product_id>/review", methods=["POST"])
@role_required(ROLE_CUSTOMER)
def review_save(product_id):
    """Write a review (or edit your own). Allowed only after a delivered order with this product."""
    product = _reviewable_product_or_404(product_id)
    try:
        _review, created = review_service.save_review(
            current_user, product, request.form.get("rating"), request.form.get("comment")
        )
        flash("Thanks for your review!" if created else "Your review was updated.", "success")
    except review_service.ReviewError as error:
        flash(str(error), "error")
    return redirect(url_for("shop.product_detail", product_id=product.id) + "#reviews")


@customer_bp.route("/products/<int:product_id>/review/delete", methods=["POST"])
@role_required(ROLE_CUSTOMER)
def review_delete(product_id):
    """Delete your own review (you can never touch anyone else's)."""
    product = _reviewable_product_or_404(product_id)
    if review_service.delete_review(current_user, product):
        flash("Your review was deleted.", "success")
    else:
        flash("You have not reviewed this product.", "error")
    return redirect(url_for("shop.product_detail", product_id=product.id) + "#reviews")
