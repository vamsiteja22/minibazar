"""Shared helpers for the catalogue and cart tests (real database data)."""
import shutil
import tempfile
from decimal import Decimal

from flask import g

from app.extensions import db
from app.models.category import Category
from app.models.product import Product
from app.models.shop import Shop
from app.models.user import User
from app.services import product_service
from tests.test_auth import PASSWORD, AuthTests, TestConfig


class ShopTestCase(AuthTests):
    base_config = TestConfig

    def setUp(self):
        self.upload_dir = tempfile.mkdtemp()
        upload_dir = self.upload_dir

        class Config(self.base_config):
            UPLOAD_FOLDER = upload_dir

        self.config = Config
        super().setUp()

        @self.app.before_request
        def forget_cached_user():
            # Tests keep one app context open; real requests each get a fresh one.
            g.pop("_login_user", None)

        product_service.ensure_default_categories()
        self.veg = Category.query.filter_by(name="Fruits & Vegetables").one()
        self.bakery = Category.query.filter_by(name="Bakery").one()

    def tearDown(self):
        super().tearDown()
        shutil.rmtree(self.upload_dir, ignore_errors=True)

    # data helpers ----------------------------------------------------------
    def make_user(self, email, role="customer", name=None):
        user = User(name=name or role.title(), email=email, role=role)
        user.set_password(PASSWORD)
        db.session.add(user)
        db.session.commit()
        return user

    def make_shop(self, name="Fresh Mart", approved=True, owner_email=None, description=None):
        owner = self.make_user(owner_email or f"owner-{name.lower().replace(' ', '')}@example.com",
                               "shopkeeper")
        shop = Shop(owner=owner, name=name, address="12 Market Road, Town",
                    description=description, is_approved=approved)
        db.session.add(shop)
        db.session.commit()
        return shop

    def make_product(self, shop, name="Apple", price="10.00", stock=10, category=None,
                     available=True, **extra):
        product = Product(shop_id=shop.id, category_id=(category or self.veg).id, name=name,
                          price=Decimal(price), stock_quantity=stock, is_available=available, **extra)
        db.session.add(product)
        db.session.commit()
        return product

    def login_client(self, email, role="customer", name=None):
        """Create a user (if needed) and return a test client logged in as them."""
        if not User.query.filter_by(email=email).first():
            self.make_user(email, role, name)
        client = self.app.test_client()
        client.post("/login", data={"email": email, "password": PASSWORD})
        return client

    def page(self, client, path):
        return client.get(path).get_data(as_text=True)
