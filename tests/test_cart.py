"""Cart rules: adding, quantities, stock limits, one shop per cart, and who may touch what."""
import unittest
from decimal import Decimal

from app.extensions import db
from app.models.cart import Cart, CartItem
from app.models.user import User
from app.services import cart_service
from tests.shop_base import ShopTestCase
from tests.test_auth import CsrfEnabledConfig


class CartTestCase(ShopTestCase):
    def setUp(self):
        super().setUp()
        self.shop_a = self.make_shop("Shop A")
        self.shop_b = self.make_shop("Shop B")
        self.apple = self.make_product(self.shop_a, "Apple", "10.00", stock=5)
        self.pear = self.make_product(self.shop_a, "Pear", "20.50", stock=10)
        self.bread = self.make_product(self.shop_b, "Bread", "40.00", stock=10)
        self.customer = self.login_client("cathy@example.com")

    # helpers
    def add(self, client, product, quantity="1", **extra):
        data = {"product_id": str(product.id), "quantity": str(quantity)}
        data.update(extra)
        return client.post("/cart/add", data=data, follow_redirects=True)

    def user(self, email="cathy@example.com"):
        db.session.expire_all()
        return User.query.filter_by(email=email).one()

    def items(self, email="cathy@example.com"):
        db.session.expire_all()
        cart = self.user(email).cart
        return {i.product.name: i.quantity for i in cart.items} if cart else {}


class AccessTests(CartTestCase):
    ACTIONS = [("post", "/cart/add"), ("post", "/cart/replace"), ("post", "/cart/clear"),
               ("post", "/cart/items/1/update"), ("post", "/cart/items/1/remove"),
               ("get", "/cart"), ("get", "/checkout")]

    def test_visitors_are_sent_to_login(self):
        visitor = self.app.test_client()
        for method, path in self.ACTIONS:
            response = getattr(visitor, method)(path)
            self.assertEqual(response.status_code, 302, path)
            self.assertIn("/login", response.location)
        self.assertEqual(Cart.query.count(), 0)

    def test_other_roles_are_refused(self):
        for role in ("shopkeeper", "delivery_partner", "admin"):
            client = self.login_client(f"{role}@example.com", role)
            for method, path in self.ACTIONS:
                data = {"product_id": str(self.apple.id), "quantity": "1"}
                response = getattr(client, method)(path, data=data if method == "post" else None)
                self.assertEqual(response.status_code, 403, (role, path))
        self.assertEqual(Cart.query.count(), 0)

    def test_get_is_not_allowed_on_actions(self):
        for path in ("/cart/add", "/cart/clear", "/cart/items/1/update"):
            self.assertEqual(self.customer.get(path).status_code, 405, path)


class AddToCartTests(CartTestCase):
    def test_add_creates_cart_and_item(self):
        page = self.add(self.customer, self.apple, 2).get_data(as_text=True)
        self.assertIn("Added 2 × Apple to your cart.", page)
        self.assertEqual(self.items(), {"Apple": 2})
        self.assertEqual(Cart.query.count(), 1)

    def test_adding_same_product_again_adds_to_quantity(self):
        self.add(self.customer, self.apple, 2)
        self.add(self.customer, self.apple, 1)
        self.assertEqual(self.items(), {"Apple": 3})
        self.assertEqual(CartItem.query.count(), 1)  # still one row per product

    def test_several_products_from_one_shop(self):
        self.add(self.customer, self.apple)
        self.add(self.customer, self.pear, 2)
        self.assertEqual(self.items(), {"Apple": 1, "Pear": 2})

    def test_bad_quantities_are_rejected(self):
        for bad in ("0", "-1", "abc", "", "1.5", " "):
            page = self.add(self.customer, self.apple, bad).get_data(as_text=True)
            self.assertIn("quantity of 1 or more", page, repr(bad))
        self.assertEqual(self.items(), {})

    def test_missing_or_invalid_product(self):
        for pid in ("999", "abc", ""):
            page = self.customer.post("/cart/add", data={"product_id": pid, "quantity": "1"},
                                      follow_redirects=True).get_data(as_text=True)
            self.assertIn("not available", page, pid)
        self.assertEqual(self.items(), {})

    def test_hidden_unapproved_and_out_of_stock_products_cannot_be_added(self):
        hidden = self.make_product(self.shop_a, "Hidden", available=False)
        sold_out = self.make_product(self.shop_a, "Sold Out", stock=0)
        pending_shop = self.make_shop("Pending Shop", approved=False)
        secret = self.make_product(pending_shop, "Secret")
        for product in (hidden, secret):
            self.assertIn("not available", self.add(self.customer, product).get_data(as_text=True))
        page = self.add(self.customer, sold_out).get_data(as_text=True)
        self.assertIn("out of stock", page)
        self.assertEqual(self.items(), {})

    def test_cannot_add_more_than_stock(self):
        page = self.add(self.customer, self.apple, 6).get_data(as_text=True)
        self.assertIn("Only 5 of “Apple” in stock", page)
        self.assertEqual(self.items(), {})
        self.add(self.customer, self.apple, 5)  # exactly the stock is fine
        self.assertEqual(self.items(), {"Apple": 5})

    def test_stock_limit_counts_what_is_already_in_the_cart(self):
        self.add(self.customer, self.apple, 3)
        page = self.add(self.customer, self.apple, 3).get_data(as_text=True)
        self.assertIn("you already have 3 in your cart", page)
        self.assertEqual(self.items(), {"Apple": 3})

    def test_redirects_back_only_to_local_pages(self):
        good = self.customer.post("/cart/add", data={"product_id": self.apple.id, "quantity": 1,
                                                     "next": "/products?sort=price_low"})
        self.assertTrue(good.location.endswith("/products?sort=price_low"))
        for evil in ("https://evil.com", "//evil.com"):
            response = self.customer.post("/cart/add", data={"product_id": self.apple.id, "quantity": 1,
                                                             "next": evil})
            self.assertTrue(response.location.endswith("/cart"), evil)

    def test_add_buttons_work_from_listing_pages(self):
        page = self.page(self.customer, "/products")
        self.assertIn('action="/cart/add"', page)
        self.assertIn('name="product_id"', page)


class OneShopPerCartTests(CartTestCase):
    def setUp(self):
        super().setUp()
        self.add(self.customer, self.apple, 2)

    def test_other_shop_is_refused_with_a_clear_message(self):
        response = self.customer.post("/cart/add", data={"product_id": self.bread.id, "quantity": 1})
        self.assertEqual(response.status_code, 409)
        page = response.get_data(as_text=True)
        self.assertIn("already has items from", page)
        self.assertIn("Shop A", page)
        self.assertIn("Clear my cart and add", page)
        self.assertIn("Keep my cart", page)
        self.assertEqual(self.items(), {"Apple": 2})  # nothing was mixed in

    def test_replace_clears_cart_and_starts_over(self):
        response = self.customer.post("/cart/replace", data={"product_id": self.bread.id, "quantity": 3},
                                      follow_redirects=True)
        self.assertIn("Started a new cart", response.get_data(as_text=True))
        self.assertEqual(self.items(), {"Bread": 3})

    def test_failed_replace_keeps_the_old_cart(self):
        sold_out = self.make_product(self.shop_b, "Sold Out", stock=0)
        too_many = self.customer.post("/cart/replace", data={"product_id": self.bread.id, "quantity": 99},
                                      follow_redirects=True).get_data(as_text=True)
        self.assertIn("in stock", too_many)
        self.customer.post("/cart/replace", data={"product_id": sold_out.id, "quantity": 1})
        self.assertEqual(self.items(), {"Apple": 2})

    def test_emptying_the_cart_frees_you_to_pick_another_shop(self):
        self.customer.post("/cart/clear")
        self.add(self.customer, self.bread)
        self.assertEqual(self.items(), {"Bread": 1})

    def test_removing_last_item_also_resets_the_shop(self):
        item = self.user().cart.items[0]
        self.customer.post(f"/cart/items/{item.id}/remove")
        self.add(self.customer, self.bread)
        self.assertEqual(self.items(), {"Bread": 1})


class UpdateRemoveTests(CartTestCase):
    def setUp(self):
        super().setUp()
        self.add(self.customer, self.apple, 2)
        self.add(self.customer, self.pear, 1)
        db.session.expire_all()
        self.apple_item = next(i for i in self.user().cart.items if i.product.name == "Apple")

    def update(self, item, quantity):
        return self.customer.post(f"/cart/items/{item.id}/update", data={"quantity": quantity},
                                  follow_redirects=True).get_data(as_text=True)

    def test_update_quantity(self):
        self.assertIn("Quantity updated", self.update(self.apple_item, 4))
        self.assertEqual(self.items()["Apple"], 4)

    def test_update_cannot_exceed_stock_or_be_invalid(self):
        self.assertIn("Only 5 of “Apple” in stock", self.update(self.apple_item, 6))
        for bad in ("0", "-2", "x", ""):
            self.assertIn("quantity of 1 or more", self.update(self.apple_item, bad))
        self.assertEqual(self.items()["Apple"], 2)

    def test_remove_one_item(self):
        page = self.customer.post(f"/cart/items/{self.apple_item.id}/remove",
                                  follow_redirects=True).get_data(as_text=True)
        self.assertIn("Removed Apple", page)
        self.assertEqual(self.items(), {"Pear": 1})

    def test_clear_cart(self):
        page = self.customer.post("/cart/clear", follow_redirects=True).get_data(as_text=True)
        self.assertIn("Your cart is empty", page)
        self.assertEqual(self.items(), {})

    def test_unknown_item_ids_are_404(self):
        self.assertEqual(self.customer.post("/cart/items/9999/update", data={"quantity": 1}).status_code, 404)
        self.assertEqual(self.customer.post("/cart/items/9999/remove").status_code, 404)


class TotalsTests(CartTestCase):
    def test_summary_numbers(self):
        self.add(self.customer, self.apple, 2)   # 20.00
        self.add(self.customer, self.pear, 1)    # 20.50
        summary = cart_service.summary(self.user())
        self.assertEqual(summary["item_count"], 3)
        self.assertEqual(summary["subtotal"], Decimal("40.50"))
        self.assertEqual(summary["delivery_fee"], Decimal("25"))   # under the free-delivery limit
        self.assertEqual(summary["total"], Decimal("65.50"))
        self.assertEqual(summary["amount_for_free_delivery"], Decimal("158.50"))
        self.assertEqual(summary["shop"].name, "Shop A")
        self.assertFalse(summary["has_problems"])

    def test_free_delivery_from_the_limit(self):
        big = self.make_product(self.shop_a, "Big Item", "199.00")
        self.add(self.customer, big, 1)
        summary = cart_service.summary(self.user())
        self.assertEqual(summary["delivery_fee"], Decimal("0"))
        self.assertEqual(summary["total"], Decimal("199.00"))

    def test_empty_cart_has_no_delivery_fee(self):
        summary = cart_service.summary(self.user())
        self.assertTrue(summary["is_empty"])
        self.assertEqual(summary["total"], Decimal("0"))

    def test_cart_page_shows_totals_and_navbar_badge(self):
        self.add(self.customer, self.apple, 2)
        self.add(self.customer, self.pear, 1)
        page = self.page(self.customer, "/cart")
        for text in ("₹40.50", "₹65.50", "₹25", "Subtotal (3 items)", "Apple", "Pear", "Shop A",
                     "more for free delivery"):
            self.assertIn(text, page)
        self.assertIn('cart-badge">3<', page)

    def test_empty_cart_page(self):
        page = self.page(self.customer, "/cart")
        self.assertIn("Your cart is empty", page)
        self.assertIn('cart-badge">0<', page)

    def test_price_changes_show_up_in_the_cart(self):
        self.add(self.customer, self.apple, 2)
        self.apple.price = Decimal("15.00")
        db.session.commit()
        self.assertIn("₹30", self.page(self.customer, "/cart"))


class ProblemLineTests(CartTestCase):
    """Things can change after an item was added: stock drops, product hidden."""

    def setUp(self):
        super().setUp()
        self.add(self.customer, self.apple, 4)

    def test_stock_dropped_below_quantity(self):
        self.apple.stock_quantity = 2
        db.session.commit()
        page = self.page(self.customer, "/cart")
        self.assertIn("Only 2 left - please lower the quantity", page)
        self.assertTrue(cart_service.summary(self.user())["has_problems"])
        checkout = self.customer.get("/checkout")
        self.assertEqual(checkout.status_code, 302)
        self.assertTrue(checkout.location.endswith("/cart"))

    def test_product_hidden_or_sold_out_after_adding(self):
        self.apple.is_available = False
        db.session.commit()
        self.assertIn("No longer available", self.page(self.customer, "/cart"))
        self.apple.is_available = True
        self.apple.stock_quantity = 0
        db.session.commit()
        self.assertIn("Out of stock", self.page(self.customer, "/cart"))

    def test_problem_lines_can_still_be_removed(self):
        self.apple.stock_quantity = 0
        db.session.commit()
        item = self.user().cart.items[0]
        self.customer.post(f"/cart/items/{item.id}/remove")
        self.assertEqual(self.items(), {})


class CheckoutPageTests(CartTestCase):
    def test_empty_cart_redirects_to_cart(self):
        response = self.customer.get("/checkout", follow_redirects=True)
        self.assertIn("Your cart is empty", response.get_data(as_text=True))

    def test_checkout_shows_real_totals(self):
        self.add(self.customer, self.apple, 2)
        page = self.page(self.customer, "/checkout")
        for text in ("2 × Apple", "₹20", "₹45", "Shop A", "Place order"):
            self.assertIn(text, page)

    def test_checkout_form_posts_to_the_server(self):
        self.add(self.customer, self.apple)
        page = self.page(self.customer, "/checkout")
        self.assertIn('method="post" action="/checkout"', page)
        self.assertIn('name="expected_total"', page)


class TwoCustomersTests(CartTestCase):
    """Customers must never see or change each other's carts."""

    def setUp(self):
        super().setUp()
        self.add(self.customer, self.apple, 2)
        self.other = self.login_client("olive@example.com")
        self.add(self.other, self.bread, 1)

    def test_carts_are_separate(self):
        self.assertEqual(self.items("cathy@example.com"), {"Apple": 2})
        self.assertEqual(self.items("olive@example.com"), {"Bread": 1})
        self.assertIn("Apple", self.page(self.customer, "/cart"))
        self.assertNotIn("Bread", self.page(self.customer, "/cart"))
        self.assertNotIn("Apple", self.page(self.other, "/cart"))

    def test_customer_cannot_change_anothers_cart_items(self):
        cathy_item = self.user("cathy@example.com").cart.items[0]
        attempts = [("update", {"quantity": 1}), ("remove", {})]
        for action, data in attempts:
            response = self.other.post(f"/cart/items/{cathy_item.id}/{action}", data=data)
            self.assertEqual(response.status_code, 404, action)
        self.assertEqual(self.items("cathy@example.com"), {"Apple": 2})
        self.assertEqual(self.items("olive@example.com"), {"Bread": 1})

    def test_clear_only_clears_own_cart(self):
        self.other.post("/cart/clear")
        self.assertEqual(self.items("olive@example.com"), {})
        self.assertEqual(self.items("cathy@example.com"), {"Apple": 2})

    def test_each_customer_can_shop_at_a_different_shop(self):
        self.assertEqual(Cart.query.count(), 2)


class CsrfTests(CartTestCase):
    base_config = CsrfEnabledConfig

    def test_cart_posts_need_a_token(self):
        # login itself needs a token in this config, so log in through the session directly
        with self.customer.session_transaction() as session:
            session["_user_id"] = str(self.user().id)
            session["_fresh"] = True
        for path in ("/cart/add", "/cart/clear", "/cart/replace", "/cart/items/1/remove"):
            self.assertEqual(self.customer.post(path, data={"product_id": self.apple.id,
                                                            "quantity": 1}).status_code, 400, path)
        self.assertEqual(Cart.query.count(), 0)


if __name__ == "__main__":
    unittest.main()
