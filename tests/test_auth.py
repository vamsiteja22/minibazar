import re
import unittest

from app import create_app
from app.extensions import db
from app.models.user import User
from config import DevelopmentConfig

PASSWORD = "secret123"

DASHBOARDS = {
    "customer": "/dashboard/customer",
    "shopkeeper": "/dashboard/shopkeeper",
    "delivery_partner": "/dashboard/delivery",
    "admin": "/dashboard/admin",
}


class TestConfig(DevelopmentConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False  # forms are tested without tokens (see CSRF test below)


class AuthTests(unittest.TestCase):
    config = TestConfig

    def setUp(self):
        self.app = create_app(self.config)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.ctx.pop()

    # helpers
    def register(self, role, email=None, **overrides):
        data = {
            "name": "Test User",
            "email": email or f"{role}@example.com",
            "password": PASSWORD,
            "confirm_password": PASSWORD,
            "role": role,
        }
        data.update(overrides)
        return self.client.post("/register", data=data, follow_redirects=False)

    def login(self, email, password=PASSWORD, **kwargs):
        return self.client.post(
            "/login", data={"email": email, "password": password}, **kwargs
        )

    def make_admin(self):
        admin = User(name="Admin", email="admin@example.com", role="admin")
        admin.set_password(PASSWORD)
        db.session.add(admin)
        db.session.commit()

    def logout(self):
        return self.client.post("/logout")


class RegistrationTests(AuthTests):
    def test_each_public_role_can_register(self):
        for role in ("customer", "shopkeeper", "delivery_partner"):
            response = self.register(role)
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.location.endswith("/login"))
            self.assertEqual(User.query.filter_by(email=f"{role}@example.com").one().role, role)

    def test_password_is_stored_hashed(self):
        self.register("customer")
        user = User.query.one()
        self.assertNotEqual(user.password_hash, PASSWORD)
        self.assertNotIn(PASSWORD, user.password_hash)

    def test_admin_role_cannot_be_registered_publicly(self):
        response = self.register("admin")
        self.assertEqual(response.status_code, 200)  # form shown again with error
        self.assertEqual(User.query.count(), 0)

    def test_invalid_input_rejected(self):
        self.register("customer", password="short", confirm_password="short")
        self.register("customer", confirm_password="different1")
        self.register("customer", email="not-an-email")
        self.register("customer", name="")
        self.assertEqual(User.query.count(), 0)

    def test_duplicate_email_rejected(self):
        self.register("customer", email="dup@example.com")
        response = self.register("shopkeeper", email="DUP@example.com")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.query.count(), 1)


class LoginAndAccessTests(AuthTests):
    def setUp(self):
        super().setUp()
        for role in ("customer", "shopkeeper", "delivery_partner"):
            self.register(role)
        self.make_admin()

    def test_each_role_is_redirected_to_its_own_dashboard(self):
        for role, path in DASHBOARDS.items():
            email = "admin@example.com" if role == "admin" else f"{role}@example.com"
            response = self.login(email)
            self.assertEqual(response.status_code, 302, role)
            self.assertTrue(response.location.endswith(path), (role, response.location))
            self.assertEqual(self.client.get(path).status_code, 200)
            self.logout()

    def test_wrong_password_and_unknown_email_fail_the_same_way(self):
        for email, password in (("customer@example.com", "wrongpass1"), ("nobody@example.com", PASSWORD)):
            response = self.login(email, password)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Invalid email or password.", response.data)
        self.assertEqual(self.client.get("/dashboard/customer").status_code, 302)

    def test_anonymous_user_is_sent_to_login(self):
        for path in DASHBOARDS.values():
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302, path)
            self.assertIn("/login", response.location)

    def test_users_cannot_open_other_roles_dashboards(self):
        emails = {
            "customer": "customer@example.com",
            "shopkeeper": "shopkeeper@example.com",
            "delivery_partner": "delivery_partner@example.com",
            "admin": "admin@example.com",
        }
        for role, email in emails.items():
            self.login(email)
            for other_role, path in DASHBOARDS.items():
                expected = 200 if other_role == role else 403
                self.assertEqual(self.client.get(path).status_code, expected, (role, path))
            self.logout()

    def test_dashboard_index_redirects_by_role(self):
        self.login("shopkeeper@example.com")
        response = self.client.get("/dashboard/")
        self.assertTrue(response.location.endswith("/dashboard/shopkeeper"))

    def test_logout_ends_session(self):
        self.login("customer@example.com")
        self.assertEqual(self.client.get("/dashboard/customer").status_code, 200)
        self.assertEqual(self.logout().status_code, 302)
        self.assertEqual(self.client.get("/dashboard/customer").status_code, 302)

    def test_logout_requires_post(self):
        self.login("customer@example.com")
        self.assertEqual(self.client.get("/logout").status_code, 405)
        self.assertEqual(self.client.get("/dashboard/customer").status_code, 200)

    def test_next_redirect_only_allows_local_paths(self):
        good = self.login("customer@example.com", query_string={"next": "/dashboard/"})
        self.assertTrue(good.location.endswith("/dashboard/"))
        self.logout()
        for evil in ("https://evil.com", "//evil.com"):
            response = self.login("customer@example.com", query_string={"next": evil})
            self.assertTrue(response.location.endswith("/dashboard/customer"), evil)
            self.logout()


class AdminCliTests(AuthTests):
    def test_create_admin_command(self):
        runner = self.app.test_cli_runner()
        result = runner.invoke(
            args=["create-admin"],
            input=f"Boss\nboss@example.com\n{PASSWORD}\n{PASSWORD}\n",
        )
        self.assertEqual(result.exit_code, 0, result.output)
        boss = User.query.filter_by(email="boss@example.com").one()
        self.assertEqual(boss.role, "admin")
        self.assertNotEqual(boss.password_hash, PASSWORD)
        response = self.login("boss@example.com")
        self.assertTrue(response.location.endswith("/dashboard/admin"))

    def test_create_admin_rejects_short_password(self):
        runner = self.app.test_cli_runner()
        result = runner.invoke(args=["create-admin"], input="Boss\nboss@example.com\nabc\nabc\n")
        self.assertNotEqual(result.exit_code, 0)
        self.assertEqual(User.query.count(), 0)


class CsrfEnabledConfig(TestConfig):
    WTF_CSRF_ENABLED = True


class CsrfTests(AuthTests):
    config = CsrfEnabledConfig

    def test_post_without_token_is_rejected_and_with_token_works(self):
        data = {"name": "A B", "email": "a@example.com", "password": PASSWORD,
                "confirm_password": PASSWORD, "role": "customer"}
        self.assertEqual(self.client.post("/register", data=data).status_code, 400)
        self.assertEqual(User.query.count(), 0)

        page = self.client.get("/register").get_data(as_text=True)
        token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
        response = self.client.post("/register", data={**data, "csrf_token": token})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(User.query.count(), 1)


if __name__ == "__main__":
    unittest.main()
