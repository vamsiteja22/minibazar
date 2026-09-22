"""Feature 3: low-stock alerts for shopkeepers."""
import unittest

from app.extensions import db
from app.models.product import Product
from app.services import inventory_service
from tests.feature_base import FeatureTestCase


class LowStockTestCase(FeatureTestCase):
    def setUp(self):
        super().setUp()
        # Shop A (threshold 5): Apple 5 and Pear 10 already exist from the base fixture.
        self.sold_out = self.make_product(self.shop_a, "Sold Out Mango", stock=0)
        self.low = self.make_product(self.shop_a, "Nearly Gone Plum", stock=2)
        self.fine = self.make_product(self.shop_a, "Plenty Grapes", stock=6)
        self.hidden = self.make_product(self.shop_a, "Hidden Fig", stock=1, available=False)
        self.other_shop = self.make_product(self.shop_b, "Other Shop Low", stock=1)
        self.seller = self.seller_client(self.shop_a)

    def names(self, products):
        return [p.name for p in products]


class InventoryRuleTests(LowStockTestCase):
    def test_threshold_comes_from_config(self):
        self.assertEqual(inventory_service.threshold(), 5)

    def test_which_products_raise_an_alert(self):
        alerts = inventory_service.low_stock_products(self.shop_a)
        self.assertEqual(self.names(alerts["out"]), ["Sold Out Mango"])
        self.assertEqual(self.names(alerts["low"]), ["Nearly Gone Plum", "Apple"])   # fewest first
        self.assertEqual(alerts["count"], 3)

    def test_the_threshold_itself_counts_and_one_above_does_not(self):
        names = self.names(inventory_service.low_stock_products(self.shop_a)["low"])
        self.assertIn("Apple", names)               # stock 5 = threshold
        self.assertNotIn("Plenty Grapes", names)    # stock 6

    def test_hidden_products_and_other_shops_are_ignored(self):
        everything = inventory_service.low_stock_products(self.shop_a)
        listed = self.names(everything["out"] + everything["low"])
        self.assertNotIn("Hidden Fig", listed)
        self.assertNotIn("Other Shop Low", listed)
        self.assertEqual(inventory_service.low_stock_count(self.shop_b), 1)

    def test_changing_the_threshold_changes_the_alerts(self):
        self.app.config["LOW_STOCK_THRESHOLD"] = 1
        alerts = inventory_service.low_stock_products(self.shop_a)
        self.assertEqual(self.names(alerts["out"]), ["Sold Out Mango"])
        self.assertEqual(alerts["low"], [])
        self.app.config["LOW_STOCK_THRESHOLD"] = 10
        self.assertEqual(inventory_service.low_stock_count(self.shop_a), 5)   # Pear (10) joins in

    def test_no_alerts_when_everything_is_well_stocked(self):
        self.assertEqual(inventory_service.low_stock_products(self.shop_b)["out"], [])
        self.bread.stock_quantity = 50
        self.other_shop.stock_quantity = 50
        db.session.commit()
        self.assertEqual(inventory_service.low_stock_products(self.shop_b)["count"], 0)


class ShopkeeperAlertPagesTests(LowStockTestCase):
    def test_dashboard_shows_the_alert_panel(self):
        page = self.page(self.seller, "/dashboard/shopkeeper")
        for text in ("Low stock alert", "Sold Out Mango", "Sold out", "Nearly Gone Plum", "Only 2 left",
                     "Restock now", "5 or fewer"):
            self.assertIn(text, page)
        self.assertNotIn("Plenty Grapes", page.split("Low stock alert")[1].split("Recent orders")[0])
        self.assertNotIn("Hidden Fig", page)
        self.assertNotIn("Other Shop Low", page)

    def test_dashboard_has_no_panel_when_nothing_is_low(self):
        seller_b = self.seller_client(self.shop_b)
        self.other_shop.stock_quantity = 40
        self.bread.stock_quantity = 40
        db.session.commit()
        self.assertNotIn("Low stock alert", self.page(seller_b, "/dashboard/shopkeeper"))

    def test_products_tab_shows_a_badge_with_the_count(self):
        for path in ("/dashboard/shopkeeper", "/shopkeeper/products", "/shopkeeper/orders", "/shopkeeper/analytics"):
            page = self.page(self.seller, path)
            self.assertIn('cart-badge badge-alert" title="Products running low">3<', page, path)

    def test_no_badge_when_nothing_is_low(self):
        seller_b = self.seller_client(self.shop_b)
        self.other_shop.stock_quantity = 40
        self.bread.stock_quantity = 40
        db.session.commit()
        self.assertNotIn("badge-alert", self.page(seller_b, "/shopkeeper/products"))

    def test_low_stock_filter_on_the_products_page(self):
        everything = self.page(self.seller, "/shopkeeper/products")
        self.assertIn("Plenty Grapes", everything)
        self.assertIn("Low stock (3)", everything)

        low_only = self.page(self.seller, "/shopkeeper/products?stock=low")
        for name in ("Sold Out Mango", "Nearly Gone Plum", "Apple"):
            self.assertIn(name, low_only)
        for name in ("Plenty Grapes", "Pear", "Hidden Fig", "Other Shop Low"):
            self.assertNotIn(name, low_only)

    def test_rows_are_labelled(self):
        page = self.page(self.seller, "/shopkeeper/products")
        self.assertIn("Out of stock", page)
        self.assertIn(">Low stock<", page)

    def test_empty_state_for_the_filter(self):
        seller_b = self.seller_client(self.shop_b)
        self.other_shop.stock_quantity = 40
        self.bread.stock_quantity = 40
        db.session.commit()
        self.assertIn("Nothing is running low", self.page(seller_b, "/shopkeeper/products?stock=low"))

    def test_restocking_clears_the_alert(self):
        # follow the redirect so the "updated" confirmation message (which names the product) is used up
        self.seller.post(f"/shopkeeper/products/{self.low.id}/quick-update",
                         data={"price": "10", "stock_quantity": "30"}, follow_redirects=True)
        self.assertNotIn("Nearly Gone Plum", self.page(self.seller, "/shopkeeper/products?stock=low"))
        self.assertEqual(inventory_service.low_stock_count(self.shop_a), 2)

    def test_hiding_a_product_clears_its_alert(self):
        self.seller.post(f"/shopkeeper/products/{self.low.id}/toggle")
        self.assertEqual(inventory_service.low_stock_count(self.shop_a), 2)

    def test_a_sale_can_trigger_an_alert(self):
        self.pear.stock_quantity = 8
        db.session.commit()
        self.assertNotIn("Pear", self.page(self.seller, "/shopkeeper/products?stock=low"))
        self.add(self.customer, self.pear, 4)
        self.checkout()
        self.assertEqual(self.stock(self.pear), 4)
        self.assertIn("Pear", self.page(self.seller, "/shopkeeper/products?stock=low"))
        self.assertIn("Only 4 left", self.page(self.seller, "/dashboard/shopkeeper"))

    def test_a_rejected_order_returns_stock_and_clears_the_alert(self):
        self.pear.stock_quantity = 8
        db.session.commit()
        self.add(self.customer, self.pear, 4)
        self.checkout()
        order = self.all_orders()[-1]
        self.order_for(self.seller, order, "reject")
        self.assertEqual(self.stock(self.pear), 8)
        self.assertNotIn("Pear", self.page(self.seller, "/shopkeeper/products?stock=low"))


class AlertAccessTests(LowStockTestCase):
    def test_only_the_owner_sees_their_shops_alerts(self):
        seller_b = self.seller_client(self.shop_b)
        page = self.page(seller_b, "/shopkeeper/products?stock=low")
        self.assertIn("Other Shop Low", page)
        self.assertNotIn("Sold Out Mango", page)
        self.assertNotIn("Nearly Gone Plum", page)

    def test_other_roles_cannot_open_the_alert_views(self):
        for client in (self.customer, self.login_client("rider@example.com", "delivery_partner"),
                       self.login_client("boss@example.com", "admin")):
            self.assertEqual(client.get("/shopkeeper/products?stock=low").status_code, 403)
        self.assertEqual(self.app.test_client().get("/shopkeeper/products?stock=low").status_code, 302)

    def test_customers_do_not_see_alert_widgets(self):
        page = self.page(self.customer, "/products")
        self.assertNotIn("Low stock", page)
        self.assertNotIn("badge-alert", page)

    def test_alerts_do_not_change_what_customers_can_buy(self):
        self.assertIn("Nearly Gone Plum", self.page(self.customer, "/products"))   # still on sale, 2 left
        self.assertEqual(Product.query.filter_by(name="Nearly Gone Plum").one().stock_quantity, 2)


if __name__ == "__main__":
    unittest.main()
