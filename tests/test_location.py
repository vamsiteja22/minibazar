"""Feature 1: nearby shop filtering (coordinates, distances, the shops page)."""
import unittest

from app.extensions import db
from app.models.shop import Shop
from app.services import location_service as loc
from tests.feature_base import FeatureTestCase

HYDERABAD = (17.3850, 78.4867)


class DistanceMathTests(unittest.TestCase):
    def test_known_distances(self):
        self.assertEqual(loc.haversine_km(*HYDERABAD, *HYDERABAD), 0)
        self.assertAlmostEqual(loc.haversine_km(0, 0, 1, 0), 111.19, delta=0.2)          # 1 degree of latitude
        self.assertAlmostEqual(loc.haversine_km(*HYDERABAD, 12.9716, 77.5946), 500, delta=10)   # Hyderabad-Bengaluru
        self.assertAlmostEqual(loc.haversine_km(0, 0, 0, 180), 20015, delta=20)          # half the Earth

    def test_symmetric_and_never_negative(self):
        a, b = loc.haversine_km(10, 20, -30, 40), loc.haversine_km(-30, 40, 10, 20)
        self.assertAlmostEqual(a, b)
        self.assertGreaterEqual(a, 0)

    def test_format_distance(self):
        self.assertEqual(loc.format_distance(0.35), "350 m")
        self.assertEqual(loc.format_distance(0.999), "1000 m")
        self.assertEqual(loc.format_distance(2.44), "2.4 km")
        self.assertEqual(loc.format_distance(12), "12.0 km")


class ParseCoordinateTests(unittest.TestCase):
    def test_valid_values(self):
        self.assertEqual(loc.parse_coordinates("17.385044", "78.486671"), (17.385044, 78.486671))
        self.assertEqual(loc.parse_coordinates(" 17.3850441234 ", " 78.4866719999 "), (17.385044, 78.486672))
        self.assertEqual(loc.parse_coordinates("90", "-180"), (90.0, -180.0))
        self.assertEqual(loc.parse_coordinates("-12", "0"), (-12.0, 0.0))

    def test_both_blank_means_no_location(self):
        self.assertEqual(loc.parse_coordinates("", ""), (None, None))
        self.assertEqual(loc.parse_coordinates(None, "  "), (None, None))

    def test_bad_values_are_rejected(self):
        bad = [("17", ""), ("", "78"), ("abc", "78"), ("17", "x"), ("nan", "10"), ("10", "inf"),
               ("91", "10"), ("-90.1", "10"), ("10", "180.5"), ("10", "-181"), ("1,5", "2")]
        for lat, lng in bad:
            with self.assertRaises(loc.LocationError, msg=(lat, lng)):
                loc.parse_coordinates(lat, lng)

    def test_radius_falls_back_to_the_default(self):
        self.assertEqual(loc.parse_radius("10"), 10)
        for bad in ("", "abc", "3", "-5", "999", "5.5", None):
            self.assertEqual(loc.parse_radius(bad), loc.DEFAULT_RADIUS, bad)


class ShopLocationFormTests(FeatureTestCase):
    def setUp(self):
        super().setUp()
        self.seller = self.seller_client(self.shop_a)

    def edit(self, **fields):
        data = {"name": "Shop A", "address": "12 Market Road, Town", "phone": "", "description": ""}
        data.update(fields)
        return self.seller.post("/shopkeeper/shop/edit", data=data, follow_redirects=True)

    def shop(self):
        db.session.expire_all()
        return db.session.get(Shop, self.shop_a.id)

    def test_shopkeeper_can_save_a_location(self):
        self.edit(latitude="17.385044", longitude="78.486671")
        shop = self.shop()
        self.assertEqual((shop.latitude, shop.longitude), (17.385044, 78.486671))
        self.assertTrue(shop.has_location)
        page = self.page(self.seller, "/shopkeeper/shop")
        self.assertIn("17.385044, 78.486671", page)
        self.assertIn("openstreetmap.org/?mlat=17.385044", page)

    def test_edit_form_is_prefilled_and_offers_the_location_button(self):
        self.edit(latitude="17.385044", longitude="78.486671")
        page = self.page(self.seller, "/shopkeeper/shop/edit")
        self.assertIn('value="17.385044"', page)
        self.assertIn('value="78.486671"', page)
        self.assertIn("data-geolocate", page)

    def test_leaving_both_empty_removes_the_location(self):
        self.edit(latitude="17.385044", longitude="78.486671")
        self.edit(latitude="", longitude="")
        self.assertFalse(self.shop().has_location)
        self.assertIn("Not set", self.page(self.seller, "/shopkeeper/shop"))

    def test_invalid_locations_are_rejected_and_nothing_changes(self):
        self.edit(latitude="17.385044", longitude="78.486671")
        for lat, lng, message in (("17", "", "both latitude and longitude"), ("abc", "78", "must be numbers"),
                                  ("95", "78", "between -90 and 90"), ("17", "200", "between -180 and 180")):
            page = self.edit(name="Changed Name", latitude=lat, longitude=lng).get_data(as_text=True)
            self.assertIn(message, page, (lat, lng))
        shop = self.shop()
        self.assertEqual((shop.name, shop.latitude, shop.longitude), ("Shop A", 17.385044, 78.486671))

    def test_a_new_shop_can_be_created_with_a_location(self):
        client = self.login_client("newseller@example.com", "shopkeeper")
        client.post("/shopkeeper/shop/create", data={
            "name": "Brand New", "address": "1 New Road, Town", "latitude": "12.9716", "longitude": "77.5946"})
        shop = Shop.query.filter_by(name="Brand New").one()
        self.assertEqual((shop.latitude, shop.longitude), (12.9716, 77.5946))

    def test_map_link_on_the_public_shop_page_only_when_a_location_exists(self):
        self.assertNotIn("View on map", self.page(self.app.test_client(), f"/shops/{self.shop_a.id}"))
        self.edit(latitude="17.385044", longitude="78.486671")
        page = self.page(self.app.test_client(), f"/shops/{self.shop_a.id}")
        self.assertIn("View on map", page)
        self.assertIn('rel="noopener"', page)


class NearbyShopsTests(FeatureTestCase):
    """Customer at (17.385, 78.4867). Shop A is 110 m away, B about 3 km, C about 12 km."""

    def setUp(self):
        super().setUp()
        self.set_location(self.shop_a, 17.3860, 78.4867)
        self.set_location(self.shop_b, 17.4120, 78.4867)
        self.shop_c = self.make_shop("Far Away Shop", owner_email="far@example.com")
        self.set_location(self.shop_c, 17.4930, 78.4867)
        self.shop_d = self.make_shop("No Location Shop", owner_email="noloc@example.com")
        self.shop_e = self.make_shop("Unapproved Near Shop", approved=False, owner_email="unap@example.com")
        self.set_location(self.shop_e, 17.3855, 78.4867)
        self.visitor = self.app.test_client()

    def set_location(self, shop, lat, lng):
        shop.latitude, shop.longitude = lat, lng
        db.session.commit()

    def near(self, radius=5, lat=HYDERABAD[0], lng=HYDERABAD[1], **extra):
        query = "&".join(f"{k}={v}" for k, v in dict(lat=lat, lng=lng, radius=radius, **extra).items())
        return self.page(self.visitor, f"/shops?{query}")

    def test_only_shops_within_the_radius_are_listed_nearest_first(self):
        page = self.near(5)
        self.assertIn("Shop A", page)
        self.assertIn("Shop B", page)
        self.assertNotIn("Far Away Shop", page)
        self.assertLess(page.index("Shop A"), page.index("Shop B"))     # nearest first
        self.assertIn("Shops within 5 km of you", page)

    def test_radius_changes_the_result(self):
        self.assertNotIn("Shop B", self.near(1))
        self.assertIn("Shop A", self.near(1))
        self.assertNotIn("Far Away Shop", self.near(10))
        self.assertIn("Far Away Shop", self.near(25))

    def test_distance_is_shown_on_each_card(self):
        page = self.near(5)
        self.assertIn("110 m away", page)
        self.assertRegex(page, r"3\.0 km away")

    def test_shops_without_a_location_are_left_out_but_mentioned(self):
        page = self.near(25)
        self.assertNotIn("No Location Shop", page)
        self.assertIn("1 other shop has not shared a location yet", page)

    def test_unapproved_shops_never_appear(self):
        self.assertNotIn("Unapproved Near Shop", self.near(25))

    def test_without_a_position_every_approved_shop_is_shown_as_before(self):
        page = self.page(self.visitor, "/shops")
        for name in ("Shop A", "Shop B", "Far Away Shop", "No Location Shop"):
            self.assertIn(name, page)
        self.assertNotIn("Unapproved Near Shop", page)
        self.assertNotIn(" away<", page)

    def test_nothing_nearby_shows_a_helpful_empty_state(self):
        page = self.near(5, lat=28.6139, lng=77.2090)      # Delhi
        self.assertIn("No shops within 5 km", page)
        self.assertIn("Show all shops", page)

    def test_bad_positions_show_a_message_instead_of_crashing(self):
        for lat, lng, message in (("abc", "78", "must be numbers"), ("17.3", "", "both latitude and longitude"),
                                  ("120", "78", "between -90 and 90"), ("17", "500", "between -180 and 180"),
                                  ("nan", "1", "real numbers")):
            response = self.visitor.get(f"/shops?lat={lat}&lng={lng}")
            self.assertEqual(response.status_code, 200, (lat, lng))
            page = response.get_data(as_text=True)
            self.assertIn(message, page, (lat, lng))
            self.assertIn("Shop A", page)                    # falls back to the normal list

    def test_bad_radius_uses_the_default(self):
        page = self.near("banana")
        self.assertIn("Shops within 5 km", page)
        self.assertIn("Shops within 5 km", self.near(999))

    def test_category_filter_and_nearby_work_together(self):
        self.make_product(self.shop_a, "Roti", category=self.bakery)     # only Shop A sells a bakery item
        page = self.near(25, category=self.bakery.id)
        self.assertIn("Shop A", page)
        self.assertNotIn("Shop B", page)                                  # near, but sells no bakery items
        self.assertNotIn("Far Away Shop", page)

    def test_typed_values_are_escaped(self):
        page = self.visitor.get("/shops?lat=%22%3E%3Cscript%3Ealert(1)%3C/script%3E&lng=1").get_data(as_text=True)
        self.assertNotIn("<script>alert(1)</script>", page)

    def test_the_page_offers_the_location_button_and_manual_entry(self):
        page = self.page(self.visitor, "/shops")
        self.assertIn("Use my location", page)
        self.assertIn("data-geolocate", page)
        self.assertIn('name="lat"', page)
        self.assertIn('name="lng"', page)
        self.assertIn("not saved", page)


if __name__ == "__main__":
    unittest.main()
