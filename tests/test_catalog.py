"""Browsing, filtering, searching and product details (real database data)."""
import unittest

from app.extensions import db
from app.models.category import Category
from app.models.order import Order, OrderItem
from app.models.review import Review
from app.services import catalog_service
from tests.shop_base import ShopTestCase


class EmptySiteTests(ShopTestCase):
    def test_pages_render_with_friendly_empty_states(self):
        for path, text in (("/", "Shops are getting ready"), ("/shops", "No shops yet"),
                           ("/products", "No products yet"), ("/search?q=milk", "Nothing found"),
                           ("/search", "Type something to search")):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertIn(text, response.get_data(as_text=True), path)

    def test_unknown_ids_give_404(self):
        for path in ("/shops/999", "/products/999", "/no-such-page"):
            self.assertEqual(self.client.get(path).status_code, 404, path)


class VisibilityTests(ShopTestCase):
    """Customers see only approved shops and products the shopkeeper has not hidden."""

    def setUp(self):
        super().setUp()
        self.good_shop = self.make_shop("Good Shop")
        self.pending_shop = self.make_shop("Pending Shop", approved=False)
        self.shown = self.make_product(self.good_shop, "Shown Apple")
        self.hidden = self.make_product(self.good_shop, "Hidden Pear", available=False)
        self.sold_out = self.make_product(self.good_shop, "Sold Out Mango", stock=0)
        self.unapproved_product = self.make_product(self.pending_shop, "Secret Banana")

    def test_lists_show_only_visible_things(self):
        for path in ("/", "/products", "/shops", f"/shops/{self.good_shop.id}"):
            page = self.page(self.client, path)
            self.assertNotIn("Hidden Pear", page, path)
            self.assertNotIn("Secret Banana", page, path)
            self.assertNotIn("Pending Shop", page, path)
        self.assertIn("Shown Apple", self.page(self.client, "/products"))
        self.assertIn("Good Shop", self.page(self.client, "/shops"))

    def test_hidden_and_unapproved_pages_are_404(self):
        self.assertEqual(self.client.get(f"/products/{self.hidden.id}").status_code, 404)
        self.assertEqual(self.client.get(f"/products/{self.unapproved_product.id}").status_code, 404)
        self.assertEqual(self.client.get(f"/shops/{self.pending_shop.id}").status_code, 404)
        self.assertEqual(self.client.get(f"/products/{self.shown.id}").status_code, 200)

    def test_out_of_stock_stays_visible_but_marked(self):
        page = self.page(self.client, "/products")
        self.assertIn("Sold Out Mango", page)
        self.assertIn("Out of stock", page)
        detail = self.page(self.client, f"/products/{self.sold_out.id}")
        self.assertIn("Currently out of stock", detail)

    def test_search_respects_visibility(self):
        for word in ("Hidden", "Secret", "Pending"):
            page = self.page(self.client, f"/search?q={word}")
            self.assertIn("Nothing found", page, word)

    def test_approving_a_shop_makes_it_visible(self):
        self.pending_shop.is_approved = True
        db.session.commit()
        self.assertIn("Secret Banana", self.page(self.client, "/products"))
        self.assertEqual(self.client.get(f"/shops/{self.pending_shop.id}").status_code, 200)


class ApproveShopCommandTests(ShopTestCase):
    def test_approve_and_revoke_from_the_command_line(self):
        shop = self.make_shop("New Shop", approved=False, owner_email="new@example.com")
        self.make_product(shop, "Milk")
        runner = self.app.test_cli_runner()
        self.assertIn("waiting for approval", runner.invoke(args=["list-shops"]).output)
        self.assertEqual(self.client.get(f"/shops/{shop.id}").status_code, 404)

        result = runner.invoke(args=["approve-shop", "--email", "new@example.com"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("approved", result.output)
        self.assertEqual(self.client.get(f"/shops/{shop.id}").status_code, 200)

        runner.invoke(args=["approve-shop", "--email", "new@example.com", "--revoke"])
        self.assertEqual(self.client.get(f"/shops/{shop.id}").status_code, 404)

    def test_unknown_email_is_an_error(self):
        result = self.app.test_cli_runner().invoke(args=["approve-shop", "--email", "nobody@example.com"])
        self.assertNotEqual(result.exit_code, 0)


class FilterAndSortTests(ShopTestCase):
    def setUp(self):
        super().setUp()
        self.shop = self.make_shop("Fresh Mart")
        self.other = self.make_shop("Bread Co")
        self.make_product(self.shop, "Cheap Apple", "5", category=self.veg)
        self.make_product(self.shop, "Pricey Melon", "90", category=self.veg)
        self.make_product(self.other, "Wheat Bread", "40", category=self.bakery)

    def test_filter_by_category(self):
        page = self.page(self.client, f"/products?category={self.bakery.id}")
        self.assertIn("Wheat Bread", page)
        self.assertNotIn("Cheap Apple", page)

    def test_unknown_or_bad_category_is_ignored(self):
        for value in ("999", "abc", ""):
            page = self.page(self.client, f"/products?category={value}")
            self.assertIn("Cheap Apple", page, value)  # behaves like "All"
            self.assertEqual(self.client.get(f"/shops?category={value}").status_code, 200)

    def test_real_category_with_no_products_shows_empty_state(self):
        empty = Category(name="Empty Aisle")
        db.session.add(empty)
        db.session.commit()
        self.assertIn("Nothing here yet", self.page(self.client, f"/products?category={empty.id}"))
        self.assertIn("No shops sell this yet", self.page(self.client, f"/shops?category={empty.id}"))

    def test_sorting(self):
        low = [p.name for p in catalog_service.list_products(sort="price_low")]
        high = [p.name for p in catalog_service.list_products(sort="price_high")]
        self.assertEqual(low, ["Cheap Apple", "Wheat Bread", "Pricey Melon"])
        self.assertEqual(high, ["Pricey Melon", "Wheat Bread", "Cheap Apple"])
        self.assertEqual(self.client.get("/products?sort=weird").status_code, 200)

    def test_shop_page_filters_its_own_products(self):
        page = self.page(self.client, f"/shops/{self.shop.id}?category={self.veg.id}")
        self.assertIn("Cheap Apple", page)
        self.assertNotIn("Wheat Bread", page)  # belongs to another shop

    def test_shops_filtered_by_category(self):
        page = self.page(self.client, f"/shops?category={self.bakery.id}")
        self.assertIn("Bread Co", page)
        self.assertNotIn("Fresh Mart", page)


class SearchTests(ShopTestCase):
    def setUp(self):
        super().setUp()
        self.shop = self.make_shop("Green Grocer", description="Organic farm produce")
        self.make_product(self.shop, "Tomato", description="Juicy red fruit")
        self.make_product(self.shop, "100% Juice", category=self.bakery)
        self.make_product(self.shop, "Rock_Salt")

    def found(self, q):
        return self.page(self.client, f"/search?q={q}")

    def test_matches_name_description_category_and_shop_case_insensitively(self):
        self.assertIn("Tomato", self.found("tomato"))
        self.assertIn("Tomato", self.found("JUICY"))          # description
        self.assertIn("100% Juice", self.found("bakery"))      # category name
        self.assertIn("Tomato", self.found("green"))           # shop name
        self.assertIn("Green Grocer", self.found("organic"))   # shop description

    def test_percent_and_underscore_are_plain_characters(self):
        self.assertIn("100% Juice", self.found("100%25"))
        self.assertNotIn("Tomato", self.found("%25"))
        self.assertIn("Rock_Salt", self.found("k_S"))
        self.assertNotIn("Rock_Salt", self.found("k.S"))

    def test_no_results_and_blank(self):
        self.assertIn("Nothing found", self.found("zzzz"))
        self.assertIn("Type something", self.found("%20%20"))

    def test_query_is_escaped(self):
        page = self.found("<script>alert(1)</script>")
        self.assertNotIn("<script>alert(1)</script>", page)


class ProductDetailTests(ShopTestCase):
    def setUp(self):
        super().setUp()
        self.shop = self.make_shop("Fresh Mart")
        self.product = self.make_product(self.shop, "Apple", "12.50", stock=3,
                                         description="Crisp & sweet")

    def test_price_stock_and_description(self):
        page = self.page(self.client, f"/products/{self.product.id}")
        for text in ("Apple", "₹12.50", "Only 3 left", "Crisp &amp; sweet", "Fresh Mart", "No reviews yet"):
            self.assertIn(text, page)

    def test_reviews_and_average_rating(self):
        one = self.make_user("r1@example.com", name="Rita")
        two = self.make_user("r2@example.com", name="Sam")
        db.session.add_all([Review(customer=one, product=self.product, rating=5, comment="Great"),
                            Review(customer=two, product=self.product, rating=4)])
        db.session.commit()
        page = self.page(self.client, f"/products/{self.product.id}")
        self.assertIn("4.5", page)
        self.assertIn("Great", page)
        self.assertIn("Rita", page)

    def test_product_name_is_escaped(self):
        product = self.make_product(self.shop, "<b>Bold</b>")
        self.assertNotIn("<b>Bold</b>", self.page(self.client, f"/products/{product.id}"))

    def test_add_control_depends_on_who_is_looking(self):
        url = f"/products/{self.product.id}"
        self.assertIn("Log in to add to cart", self.page(self.client, url))
        customer = self.login_client("c@example.com")
        page = self.page(customer, url)
        self.assertIn('action="/cart/add"', page)
        self.assertIn('name="quantity"', page)
        seller = self.login_client("s@example.com", role="shopkeeper")
        page = self.page(seller, url)
        self.assertNotIn('action="/cart/add"', page)
        self.assertIn("Only customer accounts can place orders", page)

    def test_related_products_are_same_category_and_visible(self):
        self.make_product(self.shop, "Pear")
        self.make_product(self.shop, "Loaf", category=self.bakery)
        self.make_product(self.shop, "Ghost Plum", available=False)
        page = self.page(self.client, f"/products/{self.product.id}")
        self.assertIn("Pear", page)
        self.assertNotIn("Loaf", page)
        self.assertNotIn("Ghost Plum", page)


class PopularityTests(ShopTestCase):
    def test_best_sellers_come_first_on_home(self):
        shop = self.make_shop("Fresh Mart")
        self.make_product(shop, "Brand New")
        best = self.make_product(shop, "Best Seller")
        customer = self.make_user("c@example.com")
        order = Order(customer_id=customer.id, shop_id=shop.id, delivery_address="Home, Town",
                      total_amount=50, status="delivered")
        order.items.append(OrderItem(product_id=best.id, quantity=5, price_at_purchase=best.price))
        db.session.add(order)
        db.session.commit()
        names = [p.name for p in catalog_service.popular_products()]
        self.assertEqual(names[0], "Best Seller")
        self.assertIn("Brand New", names)


if __name__ == "__main__":
    unittest.main()
