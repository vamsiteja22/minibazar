"""Shared helpers for the Phase 9 feature tests."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.extensions import db
from app.models.order import Order, OrderItem
from app.models.user import User
from tests.test_orders import OrderTestCase


class FeatureTestCase(OrderTestCase):
    """Shops A and B with products, plus a customer (Cathy). Adds a quick way to make orders."""

    def make_order_directly(self, lines, shop=None, status="delivered", customer_email="cathy@example.com",
                            created_at=None, days_ago=0, delivery_fee="25.00"):
        """Create an order without going through checkout. lines = [(product, quantity), ...]."""
        shop = shop or self.shop_a
        customer = User.query.filter_by(email=customer_email).one()
        created_at = created_at or (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days_ago))
        order = Order(customer_id=customer.id, shop_id=shop.id, delivery_address="Home, Town",
                      status=status, created_at=created_at, total_amount=0)
        goods = Decimal("0")
        for product, quantity in lines:
            order.items.append(OrderItem(product_id=product.id, quantity=quantity,
                                         price_at_purchase=product.price))
            goods += product.price * quantity
        order.total_amount = goods + Decimal(delivery_fee)
        db.session.add(order)
        db.session.commit()
        return order
