"""Shopping cart rules.

Database picture:
    User --1:1-- Cart --1:many-- CartItem --many:1-- Product --many:1-- Shop

* A customer has at most one Cart (Cart.customer_id is unique).
* A Cart has one CartItem per product (unique cart + product); quantity changes instead of duplicating.
* Version 1 rule: a cart holds products from ONE shop only. The cart has no shop column;
  its shop is simply the shop of the products inside it.
* Every function takes the logged-in customer, so a customer can only ever reach their own cart.
"""
from decimal import Decimal

from app.extensions import db
from app.models.cart import Cart, CartItem

DELIVERY_FEE = Decimal("25")
FREE_DELIVERY_ABOVE = Decimal("199")
MAX_PER_ITEM = 99


class CartError(Exception):
    """A problem to show to the customer (its text is a friendly message)."""


class ShopConflict(CartError):
    """The customer tried to add a product from a different shop than the cart's shop."""

    def __init__(self, current_shop, product):
        self.current_shop = current_shop
        self.product = product
        super().__init__(
            f"Your cart already has items from {current_shop.name}. "
            "You can order from one shop at a time."
        )


# ---- helpers -----------------------------------------------------------------
def parse_quantity(text):
    """Turn form text into a whole number of at least 1."""
    text = (text or "").strip()
    if not text.isdigit() or int(text) < 1:
        raise CartError("Please enter a quantity of 1 or more.")
    return int(text)


def max_quantity(product):
    return min(product.stock_quantity, MAX_PER_ITEM)


def check_orderable(product):
    """Raise CartError if this product cannot be bought right now."""
    if not product.is_available or not product.shop.is_approved:
        raise CartError(f"“{product.name}” is not available right now.")
    if product.stock_quantity <= 0:
        raise CartError(f"“{product.name}” is out of stock.")


def get_cart(customer, create=False):
    cart = customer.cart
    if cart is None and create:
        cart = Cart(customer=customer)
        db.session.add(cart)
        db.session.commit()
    return cart


def cart_shop(cart):
    """The shop this cart belongs to (None while the cart is empty)."""
    if cart is None or not cart.items:
        return None
    return cart.items[0].product.shop


def _find_item(cart, product_id):
    return next((item for item in cart.items if item.product_id == product_id), None)


def get_item_or_none(customer, item_id):
    """Load a cart item ONLY if it is in this customer's own cart."""
    return (
        CartItem.query.join(Cart, CartItem.cart_id == Cart.id)
        .filter(CartItem.id == item_id, Cart.customer_id == customer.id)
        .first()
    )


# ---- changing the cart ------------------------------------------------------
def add_item(customer, product, quantity):
    """Add `quantity` of a product. Returns the CartItem."""
    check_orderable(product)
    cart = get_cart(customer, create=True)

    current_shop = cart_shop(cart)
    if current_shop is not None and current_shop.id != product.shop_id:
        raise ShopConflict(current_shop, product)

    item = _find_item(cart, product.id)
    already = item.quantity if item else 0
    limit = max_quantity(product)
    if already + quantity > limit:
        message = f"Only {product.stock_quantity} of “{product.name}” in stock"
        if already:
            message += f" - you already have {already} in your cart"
        raise CartError(message + ".")

    if item:
        item.quantity += quantity
    else:
        item = CartItem(cart_id=cart.id, product_id=product.id, quantity=quantity)
        db.session.add(item)
    db.session.commit()
    return item


def set_quantity(customer, item_id, quantity):
    item = get_item_or_none(customer, item_id)
    if item is None:
        raise LookupError("Cart item not found.")
    check_orderable(item.product)
    if quantity > max_quantity(item.product):
        raise CartError(
            f"Only {item.product.stock_quantity} of “{item.product.name}” in stock."
        )
    item.quantity = quantity
    db.session.commit()
    return item


def remove_item(customer, item_id):
    item = get_item_or_none(customer, item_id)
    if item is None:
        raise LookupError("Cart item not found.")
    name = item.product.name
    db.session.delete(item)
    db.session.commit()
    return name


def clear_cart(customer):
    cart = get_cart(customer)
    if cart is not None:
        for item in list(cart.items):
            db.session.delete(item)
        db.session.commit()


def replace_cart_with(customer, product, quantity):
    """Empty the cart, then add the product (used after a shop-conflict confirmation)."""
    check_orderable(product)
    if quantity > max_quantity(product):
        raise CartError(f"Only {product.stock_quantity} of “{product.name}” in stock.")
    clear_cart(customer)
    return add_item(customer, product, quantity)


# ---- reading the cart -------------------------------------------------------
def item_count(customer):
    cart = customer.cart
    return sum(item.quantity for item in cart.items) if cart else 0


def _line_problem(product, quantity):
    """Why this line cannot be ordered right now (or None if it is fine)."""
    if not product.is_available or not product.shop.is_approved:
        return "No longer available - please remove it."
    if product.stock_quantity <= 0:
        return "Out of stock - please remove it."
    if quantity > product.stock_quantity:
        return f"Only {product.stock_quantity} left - please lower the quantity."
    return None


def summary(customer):
    """Everything the cart and checkout pages need, with totals worked out."""
    cart = customer.cart
    items = sorted(cart.items, key=lambda i: i.id) if cart else []

    lines = []
    for item in items:
        lines.append({
            "item": item,
            "product": item.product,
            "quantity": item.quantity,
            "line_total": item.product.price * item.quantity,
            "problem": _line_problem(item.product, item.quantity),
        })

    subtotal = sum((line["line_total"] for line in lines), Decimal("0"))
    delivery_fee = Decimal("0") if (not lines or subtotal >= FREE_DELIVERY_ABOVE) else DELIVERY_FEE
    return {
        "shop": cart_shop(cart),
        "lines": lines,
        "is_empty": not lines,
        "item_count": sum(line["quantity"] for line in lines),
        "subtotal": subtotal,
        "delivery_fee": delivery_fee,
        "total": subtotal + delivery_fee,
        "free_delivery_above": FREE_DELIVERY_ABOVE,
        "amount_for_free_delivery": max(FREE_DELIVERY_ABOVE - subtotal, Decimal("0")),
        "has_problems": any(line["problem"] for line in lines),
    }
