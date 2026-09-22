"""Registration input limits (found during the Phase 10 review)."""
import unittest

from app.models.user import User
from app.services import auth_service
from tests.shop_base import ShopTestCase


class EmailValidationTests(ShopTestCase):
    def errors(self, email, name="Valid Name"):
        return auth_service.validate_registration(name, email, "password123", "password123", "customer")

    def has_email_error(self, email):
        return any("valid email" in e for e in self.errors(email))

    def test_normal_addresses_are_accepted(self):
        for good in ("a@b.co", "first.last@example.com", "user+tag@sub.example.org", "USER_1@Example.COM",
                     "a-b@my-site.in"):
            self.assertFalse(self.has_email_error(good), good)

    def test_bad_addresses_are_rejected(self):
        for bad in ("", "plain", "no-at.com", "@example.com", "a@", "a@b", "a@b.", "a@.com", "a b@example.com",
                    "a@exa mple.com", "a@@example.com", "a@example..com", "a@example.c", "<script>@x.com",
                    "a'b@example.com", "a;b@example.com", "a\"b@example.com", "a\\b@example.com",
                    "' OR '1'='1@x.com", "user@exam_ple.com"):
            self.assertTrue(self.has_email_error(bad), repr(bad))

    def test_length_matches_the_database_column(self):
        longest_ok = "a" * (auth_service.MAX_EMAIL_LENGTH - len("@example.com")) + "@example.com"
        self.assertEqual(len(longest_ok), auth_service.MAX_EMAIL_LENGTH)
        self.assertFalse(self.has_email_error(longest_ok))
        self.assertTrue(self.has_email_error("a" + longest_ok))


class NameValidationTests(ShopTestCase):
    def name_error(self, name):
        errors = auth_service.validate_registration(name, "ok@example.com", "password123", "password123", "customer")
        return any("your name" in e for e in errors)

    def test_length_limits(self):
        for name, bad in (("", True), ("A", True), (" A ", True), ("Al", False), ("x" * 100, False),
                          ("x" * 101, True)):
            self.assertEqual(self.name_error(name), bad, repr(name))


class RegistrationPageTests(ShopTestCase):
    def register(self, **fields):
        data = {"name": "Test Person", "email": "test@example.com", "password": "password123",
                "confirm_password": "password123", "role": "customer"}
        data.update(fields)
        return self.app.test_client().post("/register", data=data)

    def test_over_long_values_are_refused_politely_not_with_a_server_error(self):
        for fields in ({"name": "x" * 101}, {"email": "a" * 200 + "@example.com"}):
            response = self.register(**fields)
            self.assertEqual(response.status_code, 200, fields)
        self.assertIsNone(User.query.filter_by(email="test@example.com").first())

    def test_a_valid_registration_still_works(self):
        self.assertEqual(self.register().status_code, 302)
        self.assertIsNotNone(User.query.filter_by(email="test@example.com").first())

    def test_email_is_stored_in_lower_case(self):
        self.register(email="Mixed.Case@Example.com")
        self.assertIsNotNone(User.query.filter_by(email="mixed.case@example.com").first())


if __name__ == "__main__":
    unittest.main()
