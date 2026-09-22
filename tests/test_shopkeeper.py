import io
import os
import shutil
import tempfile
import unittest
from decimal import Decimal

from flask import g

from app.extensions import db
from app.models.cart import Cart, CartItem
from app.models.category import Category
from app.models.order import Order, OrderItem
from app.models.product import Product
from app.models.shop import Shop
from app.models.user import User
from app.services import demo_service, product_service
from tests.test_auth import PASSWORD, AuthTests, CsrfEnabledConfig, TestConfig

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 32

SHOP_FORM = {"name": "Fresh Mart", "address": "12 Market Road, Gandhi Nagar",
             "phone": "9876543210", "description": "Local greens"}


class ShopkeeperTestCase(AuthTests):
    base_config = TestConfig

    def setUp(self):
        self.upload_dir = tempfile.mkdtemp()
        upload_dir = self.upload_dir

        class Config(self.base_config):
            UPLOAD_FOLDER = upload_dir
            MAX_CONTENT_LENGTH = 200 * 1024

        self.config = Config
        super().setUp()
        # The tests keep one app context open, which would let Flask-Login's cached
        # user leak between requests/clients. Real requests each get a fresh context,
        # so clear the cache before every request to behave the same way.
        @self.app.before_request
        def forget_cached_user():
            g.pop("_login_user", None)  # returns nothing, so the request continues
        product_service.ensure_default_categories()
        self.category = Category.query.first()

    def tearDown(self):
        super().tearDown()
        shutil.rmtree(self.upload_dir, ignore_errors=True)

    # helpers ---------------------------------------------------------------
    def make_seller(self, email, shop_name=None, client=None):
        """Register + log in a shopkeeper; optionally create their shop directly."""
        client = client or self.client
        client.post("/register", data={
            "name": "Test Seller", "email": email, "password": PASSWORD,
            "confirm_password": PASSWORD, "role": "shopkeeper",
        })
        client.post("/login", data={"email": email, "password": PASSWORD})
        if shop_name:
            owner = User.query.filter_by(email=email).one()
            db.session.add(Shop(owner=owner, name=shop_name, address="1 Test Road, Town"))
            db.session.commit()
        return User.query.filter_by(email=email).one()

    def make_product(self, shop, name="Apple", price="10.00", stock=5, **extra):
        product = Product(shop_id=shop.id, category_id=self.category.id, name=name,
                          price=Decimal(price), stock_quantity=stock, **extra)
        db.session.add(product)
        db.session.commit()
        return product

    def make_customer(self):
        customer = User(name="Cathy Customer", email="cathy@example.com", role="customer")
        customer.set_password(PASSWORD)
        db.session.add(customer)
        db.session.commit()
        return customer

    def make_order(self, shop, product, status="pending", quantity=2):
        customer = User.query.filter_by(email="cathy@example.com").first() or self.make_customer()
        order = Order(customer_id=customer.id, shop_id=shop.id, delivery_address="Home, Town",
                      total_amount=product.price * quantity, status=status)
        order.items.append(OrderItem(product_id=product.id, quantity=quantity,
                                     price_at_purchase=product.price))
        db.session.add(order)
        db.session.commit()
        return order

    def product_form(self, **overrides):
        data = {"name": "Tomato", "category_id": str(self.category.id), "price": "25.50",
                "stock_quantity": "10", "description": "Fresh", "is_available": "on"}
        data.update(overrides)
        return data


class ShopProfileTests(ShopkeeperTestCase):
    def test_shopkeeper_without_shop_sees_setup_prompt_and_is_redirected(self):
        self.make_seller("s@example.com")
        page = self.client.get("/dashboard/shopkeeper")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Create my shop", page.data)
        for path in ("/shopkeeper/products", "/shopkeeper/orders", "/shopkeeper/shop",
                     "/shopkeeper/products/new"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302, path)
            self.assertTrue(response.location.endswith("/shopkeeper/shop/create"), path)

    def test_create_shop(self):
        seller = self.make_seller("s@example.com")
        response = self.client.post("/shopkeeper/shop/create", data=SHOP_FORM)
        self.assertEqual(response.status_code, 302)
        shop = Shop.query.one()
        self.assertEqual(shop.owner_id, seller.id)
        self.assertEqual(shop.name, "Fresh Mart")
        self.assertFalse(shop.is_approved)  # waits for an admin
        self.assertIn(b"Fresh Mart", self.client.get("/shopkeeper/shop").data)

    def test_shop_validation(self):
        self.make_seller("s@example.com")
        for bad in ({"name": "A"}, {"address": "x"}, {"phone": "12345"},
                    {"description": "x" * 501}):
            self.client.post("/shopkeeper/shop/create", data={**SHOP_FORM, **bad})
        self.assertEqual(Shop.query.count(), 0)

    def test_second_shop_is_not_created(self):
        self.make_seller("s@example.com", "First Shop")
        response = self.client.get("/shopkeeper/shop/create")
        self.assertTrue(response.location.endswith("/shopkeeper/shop"))

    def test_edit_shop(self):
        self.make_seller("s@example.com", "Old Name")
        self.client.post("/shopkeeper/shop/edit", data={**SHOP_FORM, "name": "New Name"})
        shop = Shop.query.one()
        self.assertEqual((shop.name, shop.phone), ("New Name", "9876543210"))
        self.client.post("/shopkeeper/shop/edit", data={**SHOP_FORM, "name": ""})
        self.assertEqual(Shop.query.one().name, "New Name")


class ProductTests(ShopkeeperTestCase):
    def setUp(self):
        super().setUp()
        self.seller = self.make_seller("s@example.com", "Fresh Mart")
        self.shop = self.seller.shop

    def test_add_product(self):
        response = self.client.post("/shopkeeper/products/new", data=self.product_form())
        self.assertEqual(response.status_code, 302)
        product = Product.query.one()
        self.assertEqual(product.shop_id, self.shop.id)
        self.assertEqual(product.price, Decimal("25.50"))
        self.assertEqual(product.stock_quantity, 10)
        self.assertTrue(product.is_available)

    def test_product_page_shows_decimal_price(self):
        self.client.post("/shopkeeper/products/new", data=self.product_form())
        self.assertIn(b'value="25.50"', self.client.get("/shopkeeper/products").data)

    def test_price_and_stock_validation(self):
        bad_forms = [
            {"price": "0"}, {"price": "-5"}, {"price": "abc"}, {"price": ""},
            {"price": "1.234"}, {"price": "100001"}, {"price": "nan"},
            {"stock_quantity": "-1"}, {"stock_quantity": "1.5"}, {"stock_quantity": ""},
            {"stock_quantity": "100001"}, {"name": "x"}, {"category_id": ""}, {"category_id": "999"},
        ]
        for bad in bad_forms:
            response = self.client.post("/shopkeeper/products/new", data=self.product_form(**bad))
            self.assertEqual(response.status_code, 200, bad)  # form shown again
        self.assertEqual(Product.query.count(), 0)

    def test_failed_form_keeps_what_was_typed(self):
        page = self.client.post("/shopkeeper/products/new",
                                data=self.product_form(name="Kept Name", price="oops"))
        self.assertIn(b"Kept Name", page.data)

    def test_edit_updates_price_stock_category_and_availability(self):
        product = self.make_product(self.shop)
        other = Category(name="Extra")
        db.session.add(other)
        db.session.commit()
        response = self.client.post(
            f"/shopkeeper/products/{product.id}/edit",
            data={"name": "Apple Gala", "category_id": str(other.id), "price": "12.75",
                  "stock_quantity": "42", "description": "x"},  # no is_available => hidden
        )
        self.assertEqual(response.status_code, 302)
        db.session.refresh(product)
        self.assertEqual((product.name, product.price, product.stock_quantity, product.category_id),
                         ("Apple Gala", Decimal("12.75"), 42, other.id))
        self.assertFalse(product.is_available)

    def test_toggle_availability(self):
        product = self.make_product(self.shop)
        self.client.post(f"/shopkeeper/products/{product.id}/toggle")
        db.session.refresh(product)
        self.assertFalse(product.is_available)
        self.client.post(f"/shopkeeper/products/{product.id}/toggle")
        db.session.refresh(product)
        self.assertTrue(product.is_available)

    def test_quick_update_price_and_stock(self):
        product = self.make_product(self.shop)
        self.client.post(f"/shopkeeper/products/{product.id}/quick-update",
                         data={"price": "99.90", "stock_quantity": "7"})
        db.session.refresh(product)
        self.assertEqual((product.price, product.stock_quantity), (Decimal("99.90"), 7))
        for bad in ({"price": "0", "stock_quantity": "1"}, {"price": "5", "stock_quantity": "-2"}):
            self.client.post(f"/shopkeeper/products/{product.id}/quick-update", data=bad)
        db.session.refresh(product)
        self.assertEqual((product.price, product.stock_quantity), (Decimal("99.90"), 7))

    def test_delete_product_without_orders_removes_it_and_related_rows(self):
        product = self.make_product(self.shop)
        customer = self.make_customer()
        cart = Cart(customer=customer)
        cart.items.append(CartItem(product=product, quantity=1))
        db.session.add(cart)
        db.session.commit()
        self.client.post(f"/shopkeeper/products/{product.id}/delete")
        self.assertEqual(Product.query.count(), 0)
        self.assertEqual(CartItem.query.count(), 0)

    def test_delete_product_in_past_orders_only_hides_it(self):
        product = self.make_product(self.shop)
        self.make_order(self.shop, product, status="delivered")
        page = self.client.post(f"/shopkeeper/products/{product.id}/delete", follow_redirects=True)
        self.assertIn(b"instead of being deleted", page.data)
        db.session.refresh(product)
        self.assertFalse(product.is_available)
        self.assertEqual(OrderItem.query.count(), 1)  # order history intact

    def test_upload_valid_image_and_replace_and_remove(self):
        data = self.product_form(image=(io.BytesIO(PNG_BYTES), "photo.png"))
        self.client.post("/shopkeeper/products/new", data=data, content_type="multipart/form-data")
        product = Product.query.one()
        self.assertTrue(product.image.endswith(".png"))
        first = os.path.join(self.upload_dir, product.image)
        self.assertTrue(os.path.isfile(first))

        data = self.product_form(image=(io.BytesIO(PNG_BYTES), "new.png"))
        self.client.post(f"/shopkeeper/products/{product.id}/edit", data=data,
                         content_type="multipart/form-data")
        db.session.refresh(product)
        self.assertFalse(os.path.isfile(first))  # old file cleaned up
        second = os.path.join(self.upload_dir, product.image)
        self.assertTrue(os.path.isfile(second))

        self.client.post(f"/shopkeeper/products/{product.id}/edit",
                         data=self.product_form(remove_image="on"))
        db.session.refresh(product)
        self.assertIsNone(product.image)
        self.assertFalse(os.path.isfile(second))

    def test_deleting_product_removes_its_image(self):
        data = self.product_form(image=(io.BytesIO(PNG_BYTES), "photo.png"))
        self.client.post("/shopkeeper/products/new", data=data, content_type="multipart/form-data")
        path = os.path.join(self.upload_dir, Product.query.one().image)
        self.client.post(f"/shopkeeper/products/{Product.query.one().id}/delete")
        self.assertFalse(os.path.isfile(path))

    def test_fake_image_is_rejected_by_content_not_by_name(self):
        data = self.product_form(image=(io.BytesIO(b"<script>alert(1)</script>"), "evil.png"))
        self.client.post("/shopkeeper/products/new", data=data, content_type="multipart/form-data")
        self.assertEqual(Product.query.count(), 0)
        self.assertEqual(os.listdir(self.upload_dir), [])

    def test_too_large_upload_gets_friendly_413(self):
        big = PNG_BYTES + b"0" * (300 * 1024)
        data = self.product_form(image=(io.BytesIO(big), "big.png"))
        response = self.client.post("/shopkeeper/products/new", data=data,
                                    content_type="multipart/form-data")
        self.assertEqual(response.status_code, 413)
        self.assertIn(b"too large", response.data)
        self.assertEqual(Product.query.count(), 0)

    def test_categories_are_added_automatically_when_missing(self):
        Category.query.delete()
        db.session.commit()
        page = self.client.get("/shopkeeper/products/new").get_data(as_text=True)
        self.assertIn("Bakery", page)


class AuthorizationTests(ShopkeeperTestCase):
    """The most important tests: who may touch what."""

    def setUp(self):
        super().setUp()
        self.seller_a = self.make_seller("a@example.com", "Shop A")
        self.product_a = self.make_product(self.seller_a.shop, "A's Apple")
        self.order_a = self.make_order(self.seller_a.shop, self.product_a)

        self.client_b = self.app.test_client()
        self.seller_b = self.make_seller("b@example.com", "Shop B", client=self.client_b)

    def test_shopkeeper_cannot_touch_another_shops_product(self):
        pid = self.product_a.id
        attempts = [
            ("get", f"/shopkeeper/products/{pid}/edit", None),
            ("post", f"/shopkeeper/products/{pid}/edit", self.product_form(name="HACKED", price="1")),
            ("post", f"/shopkeeper/products/{pid}/toggle", None),
            ("post", f"/shopkeeper/products/{pid}/quick-update", {"price": "1", "stock_quantity": "0"}),
            ("post", f"/shopkeeper/products/{pid}/delete", None),
        ]
        for method, path, data in attempts:
            response = getattr(self.client_b, method)(path, data=data)
            self.assertEqual(response.status_code, 404, (method, path))
        db.session.refresh(self.product_a)
        self.assertEqual((self.product_a.name, self.product_a.price, self.product_a.stock_quantity,
                          self.product_a.is_available),
                         ("A's Apple", Decimal("10.00"), 5, True))

    def test_shopkeeper_cannot_see_or_change_another_shops_orders(self):
        oid = self.order_a.id
        self.assertEqual(self.client_b.get(f"/shopkeeper/orders/{oid}").status_code, 404)
        for action in ("accept", "reject", "preparing", "ready"):
            self.assertEqual(self.client_b.post(f"/shopkeeper/orders/{oid}/{action}").status_code, 404)
        db.session.refresh(self.order_a)
        self.assertEqual(self.order_a.status, "pending")

    def test_product_and_order_lists_only_show_own_shop(self):
        self.assertNotIn(b"A&#39;s Apple", self.client_b.get("/shopkeeper/products").data)
        self.assertNotIn(b"Cathy Customer", self.client_b.get("/shopkeeper/orders").data)
        self.assertIn(b"Cathy Customer", self.client.get("/shopkeeper/orders").data)

    def test_new_product_always_goes_to_own_shop(self):
        self.client_b.post("/shopkeeper/products/new",
                           data=self.product_form(name="B Product", shop_id=str(self.seller_a.shop.id)))
        self.assertEqual(Product.query.filter_by(name="B Product").one().shop_id, self.seller_b.shop.id)

    def test_other_roles_and_visitors_are_blocked_from_every_shopkeeper_page(self):
        paths = [("get", "/shopkeeper/shop"), ("get", "/shopkeeper/shop/create"),
                 ("get", "/shopkeeper/products"), ("get", "/shopkeeper/products/new"),
                 ("get", "/shopkeeper/orders"), ("get", f"/shopkeeper/orders/{self.order_a.id}"),
                 ("get", f"/shopkeeper/products/{self.product_a.id}/edit"),
                 ("post", f"/shopkeeper/products/{self.product_a.id}/delete"),
                 ("post", f"/shopkeeper/orders/{self.order_a.id}/accept")]

        visitor = self.app.test_client()
        for method, path in paths:
            response = getattr(visitor, method)(path)
            self.assertEqual(response.status_code, 302, path)
            self.assertIn("/login", response.location)

        for role in ("customer", "delivery_partner", "admin"):
            user = User(name=role.title(), email=f"{role}@example.com", role=role)
            user.set_password(PASSWORD)
            db.session.add(user)
        db.session.commit()
        for email in ("customer@example.com", "delivery_partner@example.com", "admin@example.com"):
            other = self.app.test_client()
            other.post("/login", data={"email": email, "password": PASSWORD})
            for method, path in paths:
                self.assertEqual(getattr(other, method)(path).status_code, 403, (email, path))

        db.session.refresh(self.product_a)
        db.session.refresh(self.order_a)
        self.assertEqual(self.order_a.status, "pending")
        self.assertEqual(Product.query.count(), 1)


class OrderManagementTests(ShopkeeperTestCase):
    def setUp(self):
        super().setUp()
        self.seller = self.make_seller("s@example.com", "Fresh Mart")
        self.shop = self.seller.shop
        self.product = self.make_product(self.shop)

    def act(self, order, action):
        return self.client.post(f"/shopkeeper/orders/{order.id}/{action}", follow_redirects=True)

    def test_full_happy_path(self):
        order = self.make_order(self.shop, self.product)
        for action, expected in (("accept", "confirmed"), ("preparing", "preparing"),
                                 ("ready", "ready_for_pickup")):
            self.act(order, action)
            db.session.refresh(order)
            self.assertEqual(order.status, expected)

    def test_reject(self):
        order = self.make_order(self.shop, self.product)
        page = self.act(order, "reject")
        db.session.refresh(order)
        self.assertEqual(order.status, "rejected")
        self.assertIn(b"Order rejected", page.data)
        self.assertNotIn(b"Accept order", page.data)  # no buttons left

    def test_invalid_status_jumps_are_refused(self):
        order = self.make_order(self.shop, self.product)
        for action in ("preparing", "ready"):  # can't skip steps
            page = self.act(order, action)
            self.assertIn(b"not available", page.data)
        db.session.refresh(order)
        self.assertEqual(order.status, "pending")

        self.act(order, "accept")
        page = self.act(order, "accept")  # double click
        self.assertIn(b"not available", page.data)
        self.act(order, "reject")  # can only reject a NEW order
        db.session.refresh(order)
        self.assertEqual(order.status, "confirmed")

    def test_finished_orders_cannot_be_changed(self):
        for status in ("delivered", "rejected", "cancelled", "out_for_delivery"):
            order = self.make_order(self.shop, self.product, status=status)
            for action in ("accept", "reject", "preparing", "ready"):
                self.act(order, action)
            db.session.refresh(order)
            self.assertEqual(order.status, status)

    def test_unknown_action(self):
        order = self.make_order(self.shop, self.product)
        page = self.act(order, "explode")
        self.assertIn(b"Unknown action", page.data)

    def test_status_filters(self):
        self.make_order(self.shop, self.product, "pending")
        self.make_order(self.shop, self.product, "preparing")
        self.make_order(self.shop, self.product, "delivered")
        self.make_order(self.shop, self.product, "rejected")
        expected = {"all": 4, "pending": 1, "active": 1, "completed": 1, "closed": 1}
        for key, count in expected.items():
            page = self.client.get(f"/shopkeeper/orders?status={key}").get_data(as_text=True)
            self.assertEqual(page.count("Order #"), count, key)
        self.assertEqual(self.client.get("/shopkeeper/orders?status=bogus").status_code, 200)

    def test_order_detail_page(self):
        order = self.make_order(self.shop, self.product, quantity=3)
        page = self.client.get(f"/shopkeeper/orders/{order.id}").get_data(as_text=True)
        for text in ("Cathy Customer", "Home, Town", "Apple", "× 3", "₹30", "Accept order", "Reject order"):
            self.assertIn(text, page)

    def test_order_action_needs_post(self):
        order = self.make_order(self.shop, self.product)
        self.assertEqual(self.client.get(f"/shopkeeper/orders/{order.id}/accept").status_code, 405)


class DashboardTests(ShopkeeperTestCase):
    def test_summary_cards_and_sales(self):
        seller = self.make_seller("s@example.com", "Fresh Mart")
        shop = seller.shop
        apple = self.make_product(shop, "Apple", "10.00")
        pear = self.make_product(shop, "Pear", "20.00", is_available=False)
        self.make_order(shop, apple, "pending")
        self.make_order(shop, apple, "pending")
        self.make_order(shop, apple, "delivered", quantity=3)   # 30
        self.make_order(shop, pear, "delivered", quantity=1)    # 20
        self.make_order(shop, apple, "rejected")                # not counted as sales

        from app.services import shop_service
        stats = shop_service.dashboard_stats(shop)
        self.assertEqual(stats["total_products"], 2)
        self.assertEqual(stats["available_products"], 1)
        self.assertEqual(stats["pending_orders"], 2)
        self.assertEqual(stats["completed_orders"], 2)
        self.assertEqual(stats["total_sales"], Decimal("50.00"))
        self.assertEqual(stats["top_products"][0][0], "Apple")

        page = self.client.get("/dashboard/shopkeeper").get_data(as_text=True)
        for text in ("Total products", "Available products", "Pending orders",
                     "Completed orders", "Sales summary", "₹50"):
            self.assertIn(text, page)

    def test_stats_ignore_other_shops(self):
        a = self.make_seller("a@example.com", "Shop A").shop
        b_client = self.app.test_client()
        b = self.make_seller("b@example.com", "Shop B", client=b_client).shop
        self.make_order(a, self.make_product(a), "delivered")
        from app.services import shop_service
        self.assertEqual(shop_service.dashboard_stats(b)["completed_orders"], 0)
        self.assertEqual(shop_service.dashboard_stats(b)["total_sales"], 0)

    def test_pending_badge_in_tabs(self):
        seller = self.make_seller("s@example.com", "Fresh Mart")
        self.make_order(seller.shop, self.make_product(seller.shop))
        self.assertIn(b'cart-badge">1<', self.client.get("/shopkeeper/orders").data)


class DemoOrdersTests(ShopkeeperTestCase):
    def test_seed_demo_orders_command(self):
        seller = self.make_seller("s@example.com", "Fresh Mart")
        runner = self.app.test_cli_runner()

        result = runner.invoke(args=["seed-demo-orders", "--email", "s@example.com"])
        self.assertNotEqual(result.exit_code, 0)  # no products yet
        self.assertIn("at least one product", result.output)

        self.make_product(seller.shop)
        result = runner.invoke(args=["seed-demo-orders", "--email", "s@example.com"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(Order.query.filter_by(shop_id=seller.shop.id).count(), len(demo_service.DEMO_ORDERS))

        result = runner.invoke(args=["seed-demo-orders", "--email", "nobody@example.com"])
        self.assertNotEqual(result.exit_code, 0)


class CsrfOnShopkeeperForms(ShopkeeperTestCase):
    base_config = CsrfEnabledConfig

    def test_post_without_token_is_rejected(self):
        # Data is created directly because forms need a CSRF token in this config.
        owner = User(name="Sam Seller", email="sam@example.com", role="shopkeeper")
        owner.set_password(PASSWORD)
        shop = Shop(owner=owner, name="Fresh Mart", address="1 Test Road, Town")
        db.session.add_all([owner, shop])
        db.session.commit()
        product = self.make_product(shop)

        self.assertEqual(self.client.post(f"/shopkeeper/products/{product.id}/delete").status_code, 400)
        self.assertEqual(self.client.post("/shopkeeper/products/new", data=self.product_form()).status_code, 400)
        self.assertEqual(Product.query.count(), 1)


if __name__ == "__main__":
    unittest.main()
