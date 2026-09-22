"""Turning a cart into an order.

place_order() is ALL-OR-NOTHING: either the order is created, the stock is reduced
and the cart is emptied, or nothing changes at all.

The browser only sends delivery details. Prices, quantities, the shop, the status
and the total all come from the database on the server.
"""
import re
from decimal import Decimal

from sqlalchemy import update

from app.extensions import db
from app.models.order import PAYMENT_PENDING, Order, OrderItem
from app.models.product import Product
from app.services import cart_service

PHONE_PATTERN = re.compile(r"^(\+91)?[6-9]\d{9}$")

# The whole delivery text is saved in one 255-character column, so each part is limited.
MAX_NAME = 50
MAX_ADDRESS = 110
MAX_NOTE = 50
MIN_ADDRESS = 10


class CheckoutError(Exception):
    """Something to tell the customer. `go_to_cart` says where to send them."""

    def __init__(self, message, go_to_cart=True):
        super().__init__(message)
        self.go_to_cart = go_to_cart


# ---- the form ------------------------------------------------------------------
def validate_checkout_form(form):
    """Return (cleaned, errors). `cleaned` holds the delivery text ready to save."""
    name = " ".join(form.get("full_name", "").split())
    phone = re.sub(r"[\s-]", "", form.get("phone", ""))
    address = " ".join(form.get("address", "").split())
    note = " ".join(form.get("notes", "").split())

    errors = []
    if not 2 <= len(name) <= MAX_NAME:
        errors.append(f"Please enter your name (2 to {MAX_NAME} characters).")
    if not PHONE_PATTERN.match(phone):
        errors.append("Enter a valid 10-digit mobile number.")
    if not MIN_ADDRESS <= len(address) <= MAX_ADDRESS:
        errors.append(f"Please enter your full delivery address ({MIN_ADDRESS} to {MAX_ADDRESS} characters).")
    if len(note) > MAX_NOTE:
        errors.append(f"Delivery instructions can be at most {MAX_NOTE} characters.")
    if form.get("payment", "cod") != "cod":
        errors.append("Only cash on delivery is available right now.")

    phone = phone[-10:]
    delivery_text = f"{name} · {phone}\n{address}"
    if note:
        delivery_text += f"\nNote: {note}"
    return {"delivery_address": delivery_text}, errors


# ---- placing the order ------------------------------------------------------------
def reserve_stock(product_id, quantity):
    """Take `quantity` from a product's stock, but only if enough is left.

    One conditional UPDATE, so two customers buying the last item at the same
    moment cannot both succeed. Returns True if the stock was reserved.
    """
    result = db.session.execute(
        update(Product)
        .where(
            Product.id == product_id,
            Product.is_available.is_(True),
            Product.stock_quantity >= quantity,
        )
        .values(stock_quantity=Product.stock_quantity - quantity)
    )
    return result.rowcount == 1


def place_order(customer, cleaned, expected_total=None):
    """Create the order for the customer's cart. Returns the new Order.

    Raises CheckoutError (and changes nothing) if anything is wrong.
    """
    summary = cart_service.summary(customer)
    if summary["is_empty"]:
        raise CheckoutError("Your cart is empty. Add something before checking out.")
    if summary["has_problems"]:
        raise CheckoutError("Some items in your cart changed. Please review them first.")

    shop = summary["shop"]
    if any(line["product"].shop_id != shop.id for line in summary["lines"]):
        raise CheckoutError("An order can only contain items from one shop.")

    # "The total I saw" only detects price changes - it is NEVER used as the amount.
    if expected_total is not None:
        try:
            saw = Decimal(expected_total)
        except Exception:
            saw = None
        if saw != summary["total"]:
            raise CheckoutError(
                "Prices in your cart changed. Please check the new total and confirm again.",
                go_to_cart=False,
            )

    try:
        for line in summary["lines"]:
            if not reserve_stock(line["product"].id, line["quantity"]):
                raise CheckoutError(
                    f"Sorry, “{line['product'].name}” just ran out of stock. "
                    "Please update your cart."
                )

        order = Order(
            customer_id=customer.id,
            shop_id=shop.id,
            delivery_address=cleaned["delivery_address"],
            total_amount=summary["total"],
            payment_status=PAYMENT_PENDING,
        )
        for line in summary["lines"]:
            order.items.append(OrderItem(
                product_id=line["product"].id,
                quantity=line["quantity"],
                price_at_purchase=line["product"].price,  # price frozen from the database
            ))
        db.session.add(order)

        for line in summary["lines"]:
            db.session.delete(line["item"])  # empty the cart
        db.session.commit()
    except Exception:
        db.session.rollback()  # undoes stock reservations too
        raise
    return order
