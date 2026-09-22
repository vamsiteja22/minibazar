import unittest
from decimal import Decimal

from sqlalchemy.exc import IntegrityError

from app import create_app
from app.extensions import db
from app.models import (
    Cart, CartItem, Category, Delivery, Order, OrderItem, Product, Review, Shop, User,
)
from config import DevelopmentConfig


class TestConfig(DevelopmentConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def make_user(self, email, role="customer"):
        user = User(name="Test", email=email, role=role)
        user.set_password("secret123")
        db.session.add(user)
        db.session.commit()
        return user

    def test_full_relationship_chain(self):
        customer = self.make_user("cust@example.com")
        owner = self.make_user("shop@example.com", "shopkeeper")
        rider = self.make_user("rider@example.com", "delivery_partner")

        shop = Shop(owner=owner, name="Fresh Mart", address="Main St")
        category = Category(name="Fruits")
        apple = Product(shop=shop, category=category, name="Apple",
                        price=Decimal("2.50"), stock_quantity=10)
        db.session.add_all([shop, category, apple])

        cart = Cart(customer=customer)
        cart.items.append(CartItem(product=apple, quantity=2))

        order = Order(customer=customer, shop=shop, delivery_address="Home",
                      total_amount=Decimal("5.00"))
        order.items.append(OrderItem(product=apple, quantity=2,
                                     price_at_purchase=apple.price))
        order.delivery = Delivery(delivery_partner=rider)
        review = Review(customer=customer, product=apple, rating=5)
        db.session.add_all([cart, order, review])
        db.session.commit()

        self.assertEqual(owner.shop.products[0].name, "Apple")
        self.assertEqual(customer.orders[0].items[0].price_at_purchase, Decimal("2.50"))
        self.assertEqual(rider.deliveries[0].order.shop.name, "Fresh Mart")
        self.assertEqual(order.status, "pending")
        self.assertEqual(order.payment_status, "pending")
        self.assertFalse(shop.is_approved)
        self.assertIsNotNone(customer.created_at)

    def test_password_is_hashed(self):
        user = self.make_user("a@example.com")
        self.assertNotEqual(user.password_hash, "secret123")
        self.assertTrue(user.check_password("secret123"))
        self.assertFalse(user.check_password("wrong"))

    def test_validation_rules(self):
        with self.assertRaises(ValueError):
            User(name="x", email="not-an-email")
        with self.assertRaises(ValueError):
            User(name="x", email="a@b.com", role="hacker")
        with self.assertRaises(ValueError):
            Product(name="x", price=Decimal("-1"))
        with self.assertRaises(ValueError):
            Review(rating=6)
        with self.assertRaises(ValueError):
            CartItem(quantity=0)

    def test_duplicate_email_rejected(self):
        self.make_user("dup@example.com")
        db.session.add(User(name="B", email="DUP@example.com", password_hash="x"))
        with self.assertRaises(IntegrityError):
            db.session.commit()


if __name__ == "__main__":
    unittest.main()
