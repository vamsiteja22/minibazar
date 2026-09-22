"""Feature 4: sales analytics for shopkeepers."""
import unittest
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

from app.extensions import db
from app.services import analytics_service
from tests.feature_base import FeatureTestCase

OFFSET = timedelta(minutes=330)   # DISPLAY_TZ_OFFSET_MINUTES


def local_today():
    return (datetime.now(timezone.utc).replace(tzinfo=None) + OFFSET).date()


class AnalyticsTestCase(FeatureTestCase):
    def setUp(self):
        super().setUp()
        self.seller = self.seller_client(self.shop_a)

    def report(self, days=30):
        db.session.expire_all()
        return analytics_service.sales_report(self.shop_a, days)


class PeriodTests(unittest.TestCase):
    def test_parse_period(self):
        for good in (7, 30, 90):
            self.assertEqual(analytics_service.parse_period(str(good)), good)
        for bad in ("", "abc", "1", "365", "-7", "7.5", None):
            self.assertEqual(analytics_service.parse_period(bad), analytics_service.DEFAULT_PERIOD, bad)


class NumbersTests(AnalyticsTestCase):
    def setUp(self):
        super().setUp()
        self.milk = self.make_product(self.shop_a, "Milk", "30.00", category=self.bakery)
        # Apple 10.00, Pear 20.50 (base fixture), Milk 30.00
        self.make_order_directly([(self.apple, 3), (self.pear, 1)])      # goods 50.50
        self.make_order_directly([(self.milk, 2)], days_ago=3)          # goods 60.00
        self.make_order_directly([(self.apple, 1)], status="pending")
        self.make_order_directly([(self.apple, 5)], status="rejected")
        self.make_order_directly([(self.apple, 1)], status="cancelled")

    def test_only_delivered_orders_count_as_sales_and_only_the_goods(self):
        report = self.report()
        self.assertEqual(report["revenue"], Decimal("110.50"))          # delivery fees (25 each) excluded
        self.assertEqual(report["orders"], 2)
        self.assertEqual(report["units"], 6)                              # 3 + 1 + 2
        self.assertEqual(report["average_order"], Decimal("110.50") / 2)

    def test_order_results_and_cancellation_rate(self):
        report = self.report()
        self.assertEqual(report["orders_placed"], 5)
        self.assertEqual(report["closed_orders"], 2)                      # rejected + cancelled
        self.assertEqual(report["closed_percent"], 40)

    def test_best_selling_products_are_ranked_by_sales(self):
        top = self.report()["top_products"]
        self.assertEqual([(p["name"], p["units"], p["revenue"]) for p in top],
                         [("Milk", 2, Decimal("60.00")), ("Apple", 3, Decimal("30.00")),
                          ("Pear", 1, Decimal("20.50"))])

    def test_sales_by_category(self):
        cats = self.report()["top_categories"]
        self.assertEqual([(c["name"], c["revenue"]) for c in cats],
                         [("Bakery", Decimal("60.00")), ("Fruits & Vegetables", Decimal("50.50"))])

    def test_daily_series_covers_every_day_and_scales_to_the_best_day(self):
        report = self.report(7)
        self.assertEqual(len(report["series"]), 7)
        self.assertEqual(report["series"][-1]["day"], local_today())
        self.assertEqual(report["series"][0]["day"], local_today() - timedelta(days=6))
        by_day = {p["day"]: p for p in report["series"]}
        today, three_ago = local_today(), local_today() - timedelta(days=3)
        self.assertEqual((by_day[today]["revenue"], by_day[today]["orders"]), (Decimal("50.50"), 1))
        self.assertEqual(by_day[three_ago]["revenue"], Decimal("60.00"))
        self.assertEqual(by_day[three_ago]["percent"], 100)               # the best day fills the chart
        self.assertEqual(by_day[today]["percent"], 84)                    # 50.5 / 60
        self.assertEqual(report["best_day"]["day"], three_ago)
        quiet = [p for p in report["series"] if not p["revenue"]]
        self.assertTrue(all(p["percent"] == 0 for p in quiet))


class PeriodBoundaryTests(AnalyticsTestCase):
    def test_orders_outside_the_period_are_left_out(self):
        self.make_order_directly([(self.apple, 1)], days_ago=2)
        self.make_order_directly([(self.apple, 1)], days_ago=20)
        self.make_order_directly([(self.apple, 1)], days_ago=60)
        self.assertEqual(self.report(7)["orders"], 1)
        self.assertEqual(self.report(30)["orders"], 2)
        self.assertEqual(self.report(90)["orders"], 3)

    def test_days_are_local_days_not_utc_days(self):
        # 00:30 local time today is still "yesterday" in UTC, but must count for TODAY.
        just_after_local_midnight = datetime.combine(local_today(), time(0, 30)) - OFFSET
        self.make_order_directly([(self.apple, 2)], created_at=just_after_local_midnight)
        report = self.report(7)
        today = report["series"][-1]
        self.assertEqual((today["day"], today["revenue"]), (local_today(), Decimal("20.00")))
        self.assertEqual(report["orders"], 1)

    def test_the_first_day_of_the_period_is_included(self):
        first_day_start = datetime.combine(local_today() - timedelta(days=6), time(0, 5)) - OFFSET
        self.make_order_directly([(self.apple, 1)], created_at=first_day_start)
        self.assertEqual(self.report(7)["orders"], 1)
        the_day_before = datetime.combine(local_today() - timedelta(days=7), time(23, 55)) - OFFSET
        self.make_order_directly([(self.apple, 1)], created_at=the_day_before)
        self.assertEqual(self.report(7)["orders"], 1)                     # one day too old


class IsolationAndEmptyTests(AnalyticsTestCase):
    def test_other_shops_orders_are_never_included(self):
        self.make_order_directly([(self.bread, 4)], shop=self.shop_b)
        self.make_order_directly([(self.apple, 1)])
        report = self.report()
        self.assertEqual((report["revenue"], report["orders"]), (Decimal("10.00"), 1))
        self.assertEqual([p["name"] for p in report["top_products"]], ["Apple"])

    def test_a_shop_with_no_orders_gets_zeroes(self):
        report = self.report()
        self.assertEqual((report["revenue"], report["orders"], report["units"], report["average_order"]),
                         (0, 0, 0, 0))
        self.assertEqual((report["orders_placed"], report["closed_percent"]), (0, 0))
        self.assertIsNone(report["best_day"])
        self.assertEqual(report["top_products"], [])
        self.assertTrue(all(p["percent"] == 0 for p in report["series"]))

    def test_a_product_without_a_category_is_grouped_sensibly(self):
        loose = self.make_product(self.shop_a, "Loose Item", "5.00")
        loose.category_id = None
        db.session.commit()
        self.make_order_directly([(loose, 2)])
        self.assertEqual(self.report()["top_categories"][0]["name"], "No category")


class AnalyticsPageTests(AnalyticsTestCase):
    def setUp(self):
        super().setUp()
        self.make_order_directly([(self.apple, 3), (self.pear, 1)])
        self.make_order_directly([(self.apple, 1)], days_ago=4)
        self.make_order_directly([(self.apple, 1)], status="rejected")

    def test_the_page_shows_the_numbers(self):
        page = self.page(self.seller, "/shopkeeper/analytics")
        for text in ("Sales analytics", "₹60.50", "Delivered orders", "Average order", "Items sold",
                     "Sales per day", "Best-selling products", "Sales by category", "Order results",
                     "Apple", "Pear", "Last 30 days", "Last 7 days", "Last 90 days", "(33%)"):
            self.assertIn(text, page)

    def test_the_chart_is_accessible_and_has_a_tooltip_per_day(self):
        page = self.page(self.seller, "/shopkeeper/analytics?days=7")
        self.assertIn('role="img"', page)
        self.assertIn("Bar chart of daily sales for the last 7 days", page)
        self.assertEqual(page.count('class="bar-col"'), 7)
        self.assertIn("from 1 order", page)

    def test_every_period_renders_with_the_right_number_of_bars(self):
        for days in (7, 30, 90):
            page = self.page(self.seller, f"/shopkeeper/analytics?days={days}")
            self.assertEqual(page.count('class="bar-col"'), days, days)

    def test_bad_period_values_fall_back_to_30_days(self):
        for bad in ("abc", "5", "9999", "-1", ""):
            page = self.page(self.seller, f"/shopkeeper/analytics?days={bad}")
            self.assertEqual(page.count('class="bar-col"'), 30, bad)

    def test_empty_shop_sees_a_friendly_message(self):
        seller_b = self.seller_client(self.shop_b)
        page = self.page(seller_b, "/shopkeeper/analytics")
        self.assertIn("No orders in this period", page)
        self.assertEqual(seller_b.get("/shopkeeper/analytics").status_code, 200)

    def test_the_sales_figure_matches_the_dashboard(self):
        dashboard = self.page(self.seller, "/dashboard/shopkeeper")
        self.assertIn("₹60.50", dashboard)

    def test_the_analytics_tab_is_in_the_menu(self):
        self.assertIn("📈 Analytics", self.page(self.seller, "/dashboard/shopkeeper"))


class AnalyticsAccessTests(AnalyticsTestCase):
    def test_visitors_are_sent_to_login(self):
        response = self.app.test_client().get("/shopkeeper/analytics")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.location)

    def test_other_roles_are_refused(self):
        for client in (self.customer, self.login_client("rider@example.com", "delivery_partner"),
                       self.login_client("boss@example.com", "admin")):
            self.assertEqual(client.get("/shopkeeper/analytics").status_code, 403)

    def test_a_shopkeeper_without_a_shop_is_sent_to_create_one(self):
        client = self.login_client("noshop@example.com", "shopkeeper")
        response = client.get("/shopkeeper/analytics")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith("/shopkeeper/shop/create"))

    def test_each_shopkeeper_sees_only_their_own_figures(self):
        self.make_order_directly([(self.apple, 2)])
        self.make_order_directly([(self.bread, 3)], shop=self.shop_b)
        page_a = self.page(self.seller, "/shopkeeper/analytics")
        page_b = self.page(self.seller_client(self.shop_b), "/shopkeeper/analytics")
        self.assertIn("₹20", page_a)
        self.assertNotIn("Bread", page_a)
        self.assertIn("₹120", page_b)
        self.assertNotIn("Apple", page_b)


if __name__ == "__main__":
    unittest.main()
