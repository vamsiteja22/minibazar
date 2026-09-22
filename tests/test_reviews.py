"""Feature 2: product reviews and shop ratings."""
import unittest

from app.extensions import db
from app.models.review import Review
from app.services import review_service
from tests.feature_base import FeatureTestCase
from tests.test_auth import CsrfEnabledConfig


class ReviewTestCase(FeatureTestCase):
    def setUp(self):
        super().setUp()
        self.visitor = self.app.test_client()

    def review(self, client, product, rating="5", comment="", **extra):
        data = {"rating": rating, "comment": comment}
        data.update(extra)
        return client.post(f"/products/{product.id}/review", data=data, follow_redirects=True)

    def rows(self):
        db.session.expire_all()
        return Review.query.order_by(Review.id).all()

    def buyer(self, email, product=None, status="delivered", name=None):
        """A customer who ordered `product` (default Apple); returns their logged-in client."""
        client = self.login_client(email, "customer", name)
        self.make_order_directly([(product or self.apple, 1)], status=status, customer_email=email)
        return client


class EligibilityTests(ReviewTestCase):
    def test_only_a_delivered_order_counts(self):
        cathy = self.user()
        self.assertFalse(review_service.has_delivered_purchase(cathy, self.apple))
        for status in ("pending", "confirmed", "preparing", "ready_for_pickup", "out_for_delivery",
                       "rejected", "cancelled"):
            self.make_order_directly([(self.apple, 1)], status=status)
            self.assertFalse(review_service.has_delivered_purchase(cathy, self.apple), status)
        self.make_order_directly([(self.apple, 1)], status="delivered")
        self.assertTrue(review_service.has_delivered_purchase(cathy, self.apple))

    def test_it_must_be_that_product_and_that_customer(self):
        self.make_order_directly([(self.apple, 1)], status="delivered")
        cathy = self.user()
        self.assertFalse(review_service.has_delivered_purchase(cathy, self.pear))     # other product
        other = self.login_client("olive@example.com")
        self.assertFalse(review_service.has_delivered_purchase(self.user("olive@example.com"), self.apple))
        self.assertEqual(len(self.rows()), 0)
        del other

    def test_what_the_product_page_offers_each_visitor(self):
        url = f"/products/{self.apple.id}"
        visitor_page = self.page(self.visitor, url)
        self.assertNotIn("Write a review", visitor_page)
        self.assertNotIn("once an order containing it has been delivered", visitor_page)

        self.assertIn("once an order containing it has been delivered", self.page(self.customer, url))
        self.assertNotIn("Write a review", self.page(self.customer, url))

        self.make_order_directly([(self.apple, 1)])
        page = self.page(self.customer, url)
        self.assertIn("Write a review", page)
        self.assertIn('name="rating"', page)
        self.assertIn("Post review", page)

        seller = self.seller_client(self.shop_a)
        page = self.page(seller, url)
        self.assertNotIn("Write a review", page)
        self.assertNotIn("once an order containing it has been delivered", page)


class WritingReviewsTests(ReviewTestCase):
    def setUp(self):
        super().setUp()
        self.make_order_directly([(self.apple, 1)])       # Cathy received an Apple

    def test_post_a_review(self):
        page = self.review(self.customer, self.apple, "4", "  Sweet   and crisp ").get_data(as_text=True)
        self.assertIn("Thanks for your review", page)
        review, = self.rows()
        self.assertEqual((review.rating, review.comment), (4, "Sweet and crisp"))
        self.assertEqual((review.customer_id, review.product_id), (self.user().id, self.apple.id))
        self.assertIn("Sweet and crisp", page)
        self.assertIn("Your review", page)

    def test_posting_again_edits_the_same_review(self):
        self.review(self.customer, self.apple, "2", "Meh")
        page = self.review(self.customer, self.apple, "5", "Changed my mind").get_data(as_text=True)
        self.assertIn("Your review was updated", page)
        review, = self.rows()                              # still exactly one row
        self.assertEqual((review.rating, review.comment), (5, "Changed my mind"))
        self.assertIn("Edit your review", page)
        self.assertIn("Update review", page)

    def test_the_comment_is_optional(self):
        self.review(self.customer, self.apple, "3", "   ")
        self.assertIsNone(self.rows()[0].comment)

    def test_invalid_ratings_are_rejected(self):
        for bad in ("", "0", "6", "-1", "abc", "3.5", "10", " "):
            page = self.review(self.customer, self.apple, bad).get_data(as_text=True)
            self.assertIn("rating from 1 to 5", page, repr(bad))
        self.assertEqual(self.rows(), [])

    def test_too_long_comments_are_rejected(self):
        page = self.review(self.customer, self.apple, "5", "x" * 501).get_data(as_text=True)
        self.assertIn("at most 500 characters", page)
        self.assertEqual(self.rows(), [])
        self.review(self.customer, self.apple, "5", "x" * 500)       # exactly the limit is fine
        self.assertEqual(len(self.rows()), 1)

    def test_cannot_review_a_product_you_did_not_receive(self):
        page = self.review(self.customer, self.pear, "5", "Never bought it").get_data(as_text=True)
        self.assertIn("after an order containing it has been delivered", page)
        self.assertEqual(self.rows(), [])

    def test_an_undelivered_order_does_not_unlock_reviews(self):
        other = self.login_client("olive@example.com")
        self.make_order_directly([(self.apple, 1)], status="out_for_delivery", customer_email="olive@example.com")
        self.review(other, self.apple, "5")
        self.assertEqual(self.rows(), [])

    def test_comments_are_escaped(self):
        page = self.review(self.customer, self.apple, "5", "<script>alert(1)</script>").get_data(as_text=True)
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("&lt;script&gt;", page)

    def test_hidden_and_unknown_products_are_404(self):
        self.apple.is_available = False
        db.session.commit()
        self.assertEqual(self.customer.post(f"/products/{self.apple.id}/review", data={"rating": "5"}).status_code, 404)
        self.assertEqual(self.customer.post("/products/9999/review", data={"rating": "5"}).status_code, 404)
        self.assertEqual(self.rows(), [])


class DeletingReviewsTests(ReviewTestCase):
    def setUp(self):
        super().setUp()
        self.make_order_directly([(self.apple, 1)])
        self.olive = self.buyer("olive@example.com")
        self.review(self.customer, self.apple, "5", "Cathy's review")
        self.review(self.olive, self.apple, "1", "Olive's review")

    def test_delete_your_own_review(self):
        page = self.customer.post(f"/products/{self.apple.id}/review/delete", follow_redirects=True).get_data(as_text=True)
        self.assertIn("Your review was deleted", page)
        remaining = self.rows()
        self.assertEqual([r.comment for r in remaining], ["Olive's review"])

    def test_you_can_only_ever_delete_your_own(self):
        self.customer.post(f"/products/{self.apple.id}/review/delete")
        self.customer.post(f"/products/{self.apple.id}/review/delete")     # nothing left of hers
        self.assertEqual([r.comment for r in self.rows()], ["Olive's review"])
        page = self.customer.post(f"/products/{self.apple.id}/review/delete", follow_redirects=True).get_data(as_text=True)
        self.assertIn("You have not reviewed this product", page)

    def test_the_delete_button_is_only_on_your_own_review(self):
        cathy_page = self.page(self.customer, f"/products/{self.apple.id}")
        self.assertEqual(cathy_page.count("Delete my review"), 1)
        self.assertIn("Olive&#39;s review", cathy_page)
        self.assertNotIn("Delete my review", self.page(self.visitor, f"/products/{self.apple.id}"))


class ReviewAccessTests(ReviewTestCase):
    def setUp(self):
        super().setUp()
        self.make_order_directly([(self.apple, 1)])
        self.paths = [f"/products/{self.apple.id}/review", f"/products/{self.apple.id}/review/delete"]

    def test_visitors_are_sent_to_login(self):
        for path in self.paths:
            response = self.visitor.post(path, data={"rating": "5"})
            self.assertEqual(response.status_code, 302, path)
            self.assertIn("/login", response.location)
        self.assertEqual(self.rows(), [])

    def test_other_roles_are_refused(self):
        for role in ("shopkeeper", "delivery_partner", "admin"):
            client = self.login_client(f"{role}@example.com", role)
            for path in self.paths:
                self.assertEqual(client.post(path, data={"rating": "5"}).status_code, 403, (role, path))
        self.assertEqual(self.rows(), [])

    def test_actions_need_post(self):
        for path in self.paths:
            self.assertEqual(self.customer.get(path).status_code, 405, path)


class RatingDisplayTests(ReviewTestCase):
    def setUp(self):
        super().setUp()
        self.olive = self.buyer("olive@example.com")
        self.make_order_directly([(self.apple, 1), (self.pear, 1)])         # Cathy got both
        self.review(self.customer, self.apple, "5", "Great")
        self.review(self.olive, self.apple, "4", "Good")
        self.review(self.customer, self.pear, "3", "OK")

    def test_product_average_and_count(self):
        self.assertEqual((self.apple.average_rating, self.apple.review_count), (4.5, 2))
        page = self.page(self.visitor, f"/products/{self.apple.id}")
        self.assertIn("4.5", page)
        self.assertIn("(2)", page)
        self.assertIn("Great", page)
        self.assertIn("Good", page)

    def test_shop_rating_is_the_average_of_all_its_products_reviews(self):
        rating = review_service.shop_rating(self.shop_a)
        self.assertAlmostEqual(rating[0], 4.0)               # (5 + 4 + 3) / 3
        self.assertEqual(rating[1], 3)
        self.assertIsNone(review_service.shop_rating(self.shop_b))

    def test_shop_rating_is_shown_on_cards_and_the_shop_page(self):
        shops_page = self.page(self.visitor, "/shops")
        self.assertIn("4.0", shops_page)
        self.assertIn("(3)", shops_page)
        self.assertIn("4.0", self.page(self.visitor, f"/shops/{self.shop_a.id}"))
        self.assertIn("4.0", self.page(self.visitor, "/"))
        self.assertIn("(3)", self.page(self.visitor, "/search?q=shop"))

    def test_a_shop_without_reviews_shows_no_rating(self):
        page = self.page(self.visitor, f"/shops/{self.shop_b.id}")
        self.assertNotIn("★", page.split("Products (")[0].split("shop-hero-info")[1])

    def test_editing_or_deleting_changes_the_averages(self):
        self.review(self.olive, self.apple, "1")
        self.assertEqual(self.apple.average_rating, 3.0)
        self.olive.post(f"/products/{self.apple.id}/review/delete")
        db.session.expire_all()
        self.assertEqual(self.apple.average_rating, 5.0)

    def test_newest_reviews_come_first(self):
        first = review_service.reviews_for(self.apple)
        self.assertEqual([r.comment for r in first], ["Good", "Great"])


class ReviewCsrfTests(ReviewTestCase):
    base_config = CsrfEnabledConfig

    def test_review_posts_need_a_token(self):
        self.make_order_directly([(self.apple, 1)])
        with self.customer.session_transaction() as session:
            session["_user_id"] = str(self.user().id)
            session["_fresh"] = True
        response = self.customer.post(f"/products/{self.apple.id}/review", data={"rating": "5"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.rows(), [])


if __name__ == "__main__":
    unittest.main()
