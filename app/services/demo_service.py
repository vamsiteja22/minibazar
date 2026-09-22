"""Sample orders so a shopkeeper has something to manage without first placing
real ones as a customer. For local testing only - used by `flask seed-demo-orders`."""
from decimal import Decimal

from app.extensions import db
from app.models.order import (
    ORDER_CONFIRMED,
    ORDER_DELIVERED,
    ORDER_PENDING,
    ORDER_PREPARING,
    Order,
    OrderItem,
)
from app.models.product import Product
from app.models.user import ROLE_CUSTOMER, User
from app.services.order_service import STOCK_RETURNING_STATUSES

DEMO_CUSTOMER_EMAIL = "demo.customer@example.com"
DEMO_CUSTOMER_PASSWORD = "demo-pass-123"

# (status, [(product position, quantity), ...])
DEMO_ORDERS = [
    (ORDER_PENDING, [(0, 2), (1, 1)]),
    (ORDER_PENDING, [(1, 3)]),
    (ORDER_CONFIRMED, [(0, 1)]),
    (ORDER_PREPARING, [(1, 2), (0, 1)]),
    (ORDER_DELIVERED, [(0, 4)]),
    (ORDER_DELIVERED, [(1, 2)]),
]


def get_or_create_demo_customer():
    customer = User.query.filter_by(email=DEMO_CUSTOMER_EMAIL).first()
    if customer is None:
        customer = User(name="Demo Customer", email=DEMO_CUSTOMER_EMAIL, role=ROLE_CUSTOMER)
        customer.set_password(DEMO_CUSTOMER_PASSWORD)
        db.session.add(customer)
        db.session.commit()
    return customer


def create_demo_orders(shop):
    """Create sample orders from the shop's first two products. Returns how many."""
    products = Product.query.filter_by(shop_id=shop.id).order_by(Product.id).limit(2).all()
    if not products:
        raise ValueError("Add at least one product to the shop first.")

    customer = get_or_create_demo_customer()
    for status, lines in DEMO_ORDERS:
        order = Order(
            customer_id=customer.id,
            shop_id=shop.id,
            delivery_address="12, Demo Street, Gandhi Nagar",
            status=status,
        )
        total = Decimal("0")
        for position, quantity in lines:
            product = products[position % len(products)]
            order.items.append(
                OrderItem(product_id=product.id, quantity=quantity, price_at_purchase=product.price)
            )
            total += product.price * quantity
            if status not in STOCK_RETURNING_STATUSES:
                # Like a real order, reserve the stock (never below zero).
                product.stock_quantity = max(0, product.stock_quantity - quantity)
        order.total_amount = total
        db.session.add(order)
    db.session.commit()
    return len(DEMO_ORDERS)
