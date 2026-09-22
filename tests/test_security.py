"""Phase 10 security review: configuration, headers, login protection, injection, error pages."""
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

import config as config_module
from app import create_app, security
from app.extensions import db
from app.models.product import Product
from app.models.user import User
from app.services import auth_service
from config import ProductionConfig, get_config
from tests.staff_base import StaffTestCase
from tests.test_auth import PASSWORD, CsrfEnabledConfig, TestConfig

ROOT = pathlib.Path(__file__).resolve().parent.parent
STRONG_SECRET = "a" * 40


class ProdTestConfig(ProductionConfig):
    """Production rules, but with a throw-away in-memory database."""

    SQLALCHEMY_DATABASE_URI = "sqlite://"
    TESTING = True


# ---- configuration ------------------------------------------------------------------
class ConfigurationTests(unittest.TestCase):
    def test_development_is_the_default(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("APP_ENV", None)
            self.assertEqual(get_config().__name__, "DevelopmentConfig")

    def test_unknown_environment_names_are_an_error(self):
        with self.assertRaises(RuntimeError):
            get_config("stagingg")

    def test_production_turns_debug_off_and_cookies_strict(self):
        self.assertFalse(ProductionConfig.DEBUG)
        self.assertTrue(ProductionConfig.SESSION_COOKIE_SECURE)
        self.assertTrue(ProductionConfig.SESSION_COOKIE_HTTPONLY)
        self.assertEqual(ProductionConfig.SESSION_COOKIE_SAMESITE, "Lax")
        self.assertTrue(ProductionConfig.HTTPS_ONLY)

    def test_production_refuses_a_missing_or_weak_secret_key(self):
        for bad in (None, "", config_module.DEV_SECRET_KEY, "too-short", "x" * 31):
            env = {} if bad is None else {"SECRET_KEY": bad}
            with mock.patch.dict(os.environ, env, clear=False):
                if bad is None:
                    os.environ.pop("SECRET_KEY", None)
                with self.assertRaises(RuntimeError, msg=repr(bad)) as caught:
                    create_app(ProdTestConfig)
                self.assertIn("SECRET_KEY", str(caught.exception))

    def test_production_starts_with_a_strong_secret_key(self):
        with mock.patch.dict(os.environ, {"SECRET_KEY": STRONG_SECRET}):
            app = create_app(ProdTestConfig)
        self.assertEqual(app.config["SECRET_KEY"], STRONG_SECRET)
        self.assertFalse(app.debug)

    def test_old_postgres_urls_are_fixed(self):
        with mock.patch.dict(os.environ, {"DATABASE_URL": "postgres://u:p@host:5432/db"}):
            self.assertEqual(config_module._database_url(), "postgresql://u:p@host:5432/db")
        with mock.patch.dict(os.environ, {"DATABASE_URL": "postgresql://u:p@host/db"}):
            self.assertEqual(config_module._database_url(), "postgresql://u:p@host/db")
        with mock.patch.dict(os.environ, {}):
            os.environ.pop("DATABASE_URL", None)
            self.assertTrue(config_module._database_url().startswith("sqlite:///"))

    def test_the_development_server_refuses_to_run_in_production(self):
        env = dict(os.environ, APP_ENV="production", SECRET_KEY=STRONG_SECRET,
                   DATABASE_URL="sqlite:///" + os.path.join(tempfile.gettempdir(), "prod_refuse_test.db"))
        result = subprocess.run([sys.executable, "run.py"], cwd=ROOT, env=env, capture_output=True,
                                text=True, timeout=120)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Refusing to start the development server", result.stdout + result.stderr)

    def test_production_without_a_secret_key_cannot_start_at_all(self):
        env = {k: v for k, v in os.environ.items() if k != "SECRET_KEY"}
        env.update(APP_ENV="production", DATABASE_URL="sqlite://")
        result = subprocess.run([sys.executable, "-c", "import wsgi"], cwd=ROOT, env=env,
                                capture_output=True, text=True, timeout=120)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SECRET_KEY is missing or too weak", result.stderr)


class DeploymentFilesTests(unittest.TestCase):
    def read(self, name):
        return (ROOT / name).read_text(encoding="utf-8")

    def test_secrets_are_never_committed(self):
        ignored = [line.strip() for line in self.read(".gitignore").splitlines()]
        for pattern in (".env", "venv/", "instance/", "*.db"):
            self.assertIn(pattern, ignored)

    def test_the_example_env_file_contains_no_real_secrets_or_debug_switch(self):
        example = self.read(".env.example")
        self.assertNotIn("FLASK_DEBUG", example)
        self.assertIn("APP_ENV=development", example)
        self.assertRegex(example, r"SECRET_KEY=change-me")

    def test_production_requirements_include_a_real_server(self):
        requirements = self.read("requirements-prod.txt")
        self.assertIn("-r requirements.txt", requirements)
        self.assertIn("gunicorn", requirements)
        self.assertIn("waitress", requirements)

    def test_entry_points(self):
        self.assertIn("gunicorn wsgi:app", self.read("Procfile"))
        self.assertIn("app = create_app()", self.read("wsgi.py"))


# ---- headers ---------------------------------------------------------------------------
class SecurityHeaderTests(StaffTestCase):
    def test_every_kind_of_response_carries_the_headers(self):
        anonymous = self.app.test_client()
        for path in ("/", "/login", "/shops", "/no-such-page", "/static/css/style.css", "/healthz"):
            headers = anonymous.get(path).headers
            self.assertIn("script-src 'self'", headers["Content-Security-Policy"], path)
            self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"], path)
            self.assertEqual(headers["X-Content-Type-Options"], "nosniff", path)
            self.assertEqual(headers["X-Frame-Options"], "DENY", path)
            self.assertIn("strict-origin", headers["Referrer-Policy"], path)
            self.assertIn("geolocation=(self)", headers["Permissions-Policy"], path)

    def test_hsts_is_only_sent_by_the_production_site_over_https(self):
        self.assertNotIn("Strict-Transport-Security", self.app.test_client().get("/").headers)
        with mock.patch.dict(os.environ, {"SECRET_KEY": STRONG_SECRET}):
            live = create_app(ProdTestConfig)
        with live.app_context():
            db.create_all()
        secure = live.test_client().get("/", base_url="https://shop.example.com")
        self.assertIn("max-age=31536000", secure.headers["Strict-Transport-Security"])
        plain = live.test_client().get("/", base_url="http://shop.example.com")
        self.assertNotIn("Strict-Transport-Security", plain.headers)

    def test_no_page_needs_inline_scripts_so_the_strict_policy_never_breaks_anything(self):
        seller = self.seller_client(self.shop_a)
        self.add(self.customer, self.apple)
        pages = [(self.app.test_client(), p) for p in ("/", "/login", "/register", "/shops", "/products",
                                                       f"/products/{self.apple.id}", "/search?q=a")]
        pages += [(self.customer, p) for p in ("/cart", "/checkout", "/orders", "/dashboard/customer")]
        pages += [(seller, p) for p in ("/dashboard/shopkeeper", "/shopkeeper/products", "/shopkeeper/analytics",
                                        "/shopkeeper/orders", "/shopkeeper/shop/edit", "/shopkeeper/products/new")]
        pages += [(self.admin, p) for p in ("/dashboard/admin", "/admin/users", "/admin/shops", "/admin/orders",
                                            "/admin/categories")]
        pages += [(self.rider, "/dashboard/delivery")]
        for client, path in pages:
            html = client.get(path).get_data(as_text=True)
            self.assertNotRegex(html, r"<script(?![^>]*\bsrc=)", path)            # only external scripts
            self.assertNotRegex(html, r"\son(click|submit|load|change|error)\s*=", path)  # no inline handlers
            self.assertNotIn("javascript:", html, path)

    def test_session_cookie_flags(self):
        response = self.app.test_client().post("/login", data={"email": "cathy@example.com", "password": PASSWORD})
        cookie = response.headers.get("Set-Cookie", "")
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)


# ---- login protection --------------------------------------------------------------------
class ThrottleUnitTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000.0
        self.throttle = security.LoginThrottle(max_failures=3, lockout_seconds=60, clock=lambda: self.now)
        self.key = self.throttle.key("1.2.3.4", "Cathy@Example.com ")

    def test_locks_after_the_limit_and_unlocks_later(self):
        for _ in range(2):
            self.throttle.record_failure(self.key)
        self.assertEqual(self.throttle.seconds_left(self.key), 0)
        self.throttle.record_failure(self.key)
        self.assertGreater(self.throttle.seconds_left(self.key), 0)
        self.now += 61
        self.assertEqual(self.throttle.seconds_left(self.key), 0)

    def test_the_key_ignores_email_case_and_spaces_but_not_the_address(self):
        self.assertEqual(self.key, self.throttle.key("1.2.3.4", "cathy@example.com"))
        self.assertNotEqual(self.key, self.throttle.key("9.9.9.9", "cathy@example.com"))

    def test_success_clears_the_count(self):
        for _ in range(3):
            self.throttle.record_failure(self.key)
        self.throttle.clear(self.key)
        self.assertEqual(self.throttle.seconds_left(self.key), 0)


class LoginProtectionTests(StaffTestCase):
    def attempt(self, client, email="cathy@example.com", password="wrong-password-1", **extra):
        return client.post("/login", data={"email": email, "password": password}, **extra)

    def test_too_many_wrong_passwords_lock_the_visitor_out_even_with_the_right_one(self):
        guesser = self.app.test_client()
        for _ in range(self.app.config["MAX_FAILED_LOGINS"]):
            self.assertEqual(self.attempt(guesser).status_code, 200)
        blocked = self.attempt(guesser, password=PASSWORD)          # the CORRECT password
        self.assertEqual(blocked.status_code, 429)
        self.assertIn("Too many failed attempts", blocked.get_data(as_text=True))
        self.assertEqual(guesser.get("/cart").status_code, 302)     # and they are not logged in

    def test_other_accounts_and_other_visitors_are_not_affected(self):
        guesser = self.app.test_client()
        for _ in range(self.app.config["MAX_FAILED_LOGINS"]):
            self.attempt(guesser)
        self.assertEqual(self.attempt(guesser, "rider@example.com", PASSWORD).status_code, 302)   # other email
        elsewhere = self.attempt(self.app.test_client(), password=PASSWORD,
                                 environ_overrides={"REMOTE_ADDR": "203.0.113.9"})                # other address
        self.assertEqual(elsewhere.status_code, 302)

    def test_the_lock_expires(self):
        guesser = self.app.test_client()
        throttle = self.app.extensions["login_throttle"]
        clock = {"now": 5000.0}
        throttle.clock = lambda: clock["now"]
        for _ in range(self.app.config["MAX_FAILED_LOGINS"]):
            self.attempt(guesser)
        self.assertEqual(self.attempt(guesser, password=PASSWORD).status_code, 429)
        clock["now"] += self.app.config["LOGIN_LOCKOUT_SECONDS"] + 1
        self.assertEqual(self.attempt(guesser, password=PASSWORD).status_code, 302)

    def test_a_successful_login_resets_the_counter(self):
        client = self.app.test_client()
        for _ in range(self.app.config["MAX_FAILED_LOGINS"] - 1):
            self.attempt(client)
        self.assertEqual(self.attempt(client, password=PASSWORD).status_code, 302)
        client.post("/logout")
        for _ in range(self.app.config["MAX_FAILED_LOGINS"] - 1):
            self.assertEqual(self.attempt(client).status_code, 200)     # fresh allowance

    def test_unknown_emails_are_throttled_too(self):
        client = self.app.test_client()
        for _ in range(self.app.config["MAX_FAILED_LOGINS"]):
            self.attempt(client, "nobody@example.com")
        self.assertEqual(self.attempt(client, "nobody@example.com").status_code, 429)


class PasswordSecurityTests(StaffTestCase):
    def test_passwords_are_salted_hashes_never_plain_text(self):
        hashes = [u.password_hash for u in User.query.all()]
        self.assertTrue(hashes)
        for stored in hashes:
            self.assertNotIn(PASSWORD, stored)
            self.assertRegex(stored, r"^(scrypt|pbkdf2):")
        self.assertEqual(len(hashes), len(set(hashes)))     # same password, different salts

    def test_missing_emails_cost_the_same_as_wrong_passwords(self):
        with mock.patch("app.services.auth_service.check_password_hash") as checked:
            self.assertIsNone(auth_service.authenticate("nobody@example.com", "whatever123"))
        checked.assert_called_once()
        self.assertEqual(checked.call_args.args[0], security.DUMMY_PASSWORD_HASH)

    def test_overlong_passwords_are_rejected_without_hashing_them(self):
        huge = "x" * 5000
        self.assertIsNone(auth_service.authenticate("cathy@example.com", huge))
        errors = auth_service.validate_registration("New Person", "new@example.com", huge, huge, "customer")
        self.assertTrue(any("at most 128" in e for e in errors))
        response = self.app.test_client().post("/register", data={
            "name": "New Person", "email": "new@example.com", "password": huge,
            "confirm_password": huge, "role": "customer"})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(User.query.filter_by(email="new@example.com").first())

    def test_password_boundary_lengths(self):
        for password, ok in (("x" * 7, False), ("x" * 8, True), ("x" * 128, True), ("x" * 129, False)):
            errors = auth_service.validate_registration("Name", "edge@example.com", password, password, "customer")
            self.assertEqual(not any("Password" in e and "characters" in e for e in errors), ok, len(password))


class RedirectSafetyTests(StaffTestCase):
    BAD = ["//evil.com", "https://evil.com", "http://evil.com", "/\\evil.com", "/\\/evil.com", "/%5Cevil.com",
           "/%5cevil.com", "/%2F/evil.com", "/\t/evil.com", "\\evil.com", "javascript:alert(1)", "evil.com", ""]

    def test_unsafe_targets_are_refused(self):
        for target in self.BAD:
            self.assertFalse(auth_service.is_safe_redirect(target), repr(target))

    def test_local_targets_are_accepted(self):
        for target in ("/", "/dashboard/", "/products?sort=price_low", "/shops/3#reviews"):
            self.assertTrue(auth_service.is_safe_redirect(target), target)

    def test_login_never_redirects_off_site(self):
        for target in self.BAD:
            client = self.app.test_client()
            response = client.post("/login", data={"email": "cathy@example.com", "password": PASSWORD},
                                   query_string={"next": target})
            self.assertEqual(response.status_code, 302, target)
            self.assertTrue(response.location.endswith("/dashboard/customer"), (target, response.location))


# ---- injection ---------------------------------------------------------------------------
class InjectionTests(StaffTestCase):
    PAYLOADS = ["' OR '1'='1", "'; DROP TABLE users; --", "\" OR 1=1 --", "%' OR 1=1 --", "1; DELETE FROM products",
                "' UNION SELECT email, password_hash FROM users --", "\\", "%", "_"]

    def counts(self):
        db.session.expire_all()
        return User.query.count(), Product.query.count()

    def test_search_treats_attack_text_as_plain_text(self):
        before = self.counts()
        visitor = self.app.test_client()
        for payload in self.PAYLOADS:
            response = visitor.get("/search", query_string={"q": payload})
            self.assertEqual(response.status_code, 200, payload)
            page = response.get_data(as_text=True)
            self.assertNotIn("scrypt:", page)                  # no password hashes leak
            self.assertNotIn("pbkdf2:", page)
            self.assertNotIn("cathy@example.com", page)        # no other user data either
            if payload not in ("%", "_", "\\"):
                self.assertIn("Nothing found", page, payload)          # matched nothing, as plain text
        self.assertEqual(self.counts(), before)

    def test_login_and_register_forms_are_not_injectable(self):
        users_before = {u.email for u in User.query.all()}
        products_before = Product.query.count()
        client = self.app.test_client()
        for payload in self.PAYLOADS:
            login = client.post("/login", data={"email": payload, "password": payload})
            self.assertEqual(login.status_code, 200, payload)
            self.assertIn("Invalid email or password", login.get_data(as_text=True))
            client.post("/register", data={"name": payload, "email": f"{payload}@x.com", "password": payload * 3,
                                           "confirm_password": payload * 3, "role": "customer"})
        db.session.expire_all()
        users_after = {u.email for u in User.query.all()}
        self.assertTrue(users_before <= users_after)                     # nobody was deleted
        self.assertEqual(Product.query.count(), products_before)
        for email in users_after - users_before:                          # and no odd address got in
            self.assertRegex(email, auth_service.EMAIL_PATTERN)

    def test_url_parameters_are_not_injectable(self):
        visitor = self.app.test_client()
        for path in ("/products?category=1%20OR%201=1", "/products?sort=price_low;DROP%20TABLE%20users",
                     "/shops?category=1;--", "/shops?lat=1%20OR%201=1&lng=2", "/products/1%20OR%201=1",
                     "/shops/1;DROP%20TABLE%20shops"):
            self.assertIn(visitor.get(path).status_code, (200, 404), path)
        self.assertEqual(db.session.execute(text("SELECT COUNT(*) FROM users")).scalar(), self.counts()[0])

    def test_writing_attack_text_into_forms_stores_it_harmlessly(self):
        seller = self.seller_client(self.shop_a)
        seller.post("/shopkeeper/shop/edit", data={"name": "Bob'); DROP TABLE shops;--",
                                                   "address": "1 Robert'); DROP TABLE users;-- Road"})
        db.session.expire_all()
        self.assertEqual(db.session.execute(text("SELECT COUNT(*) FROM shops")).scalar(), 2)
        self.assertIn("Bob&#39;); DROP TABLE shops;--", self.page(seller, "/shopkeeper/shop"))

    def test_no_source_file_builds_sql_from_strings(self):
        """Every database call must go through the ORM or a SQLAlchemy construct."""
        offenders = []
        for path in (ROOT / "app").rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            for match in re.finditer(r"\.execute\(\s*f?([\"'])(.*?)", source):
                if match.group(2) != "PRAGMA foreign_keys=ON":       # a fixed switch, no user input
                    offenders.append(f"{path.name}: execute() called with a raw string")
            for match in re.finditer(r"\btext\(\s*f?[\"']", source):
                if path.name not in ("schema_upgrade.py", "main.py"):
                    offenders.append(f"{path.name}: text() with a raw string")
        self.assertEqual(offenders, [])
        # the two allowed uses are fixed strings written by us (the upgrader, and SELECT 1)
        upgrader = (ROOT / "app" / "schema_upgrade.py").read_text(encoding="utf-8")
        self.assertIn("fixed strings written by us", upgrader)


class DatabaseIntegrityTests(StaffTestCase):
    def test_foreign_keys_are_enforced(self):
        self.assertEqual(db.session.execute(text("PRAGMA foreign_keys")).scalar(), 1)
        db.session.add(Product(shop_id=99999, name="Orphan", price=1, stock_quantity=1))
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()


# ---- error pages, health check, demo data --------------------------------------------------
class FriendlyErrorTests(unittest.TestCase):
    def test_a_missing_form_token_gives_a_friendly_400_page(self):
        class Config(CsrfEnabledConfig):
            pass

        app = create_app(Config)
        with app.app_context():
            db.create_all()
        response = app.test_client().post("/login", data={"email": "a@b.com", "password": "x"})
        self.assertEqual(response.status_code, 400)
        page = response.get_data(as_text=True)
        self.assertIn("That page expired", page)
        self.assertNotIn("CSRF", page)

    def test_a_crash_shows_a_friendly_500_page_without_technical_details(self):
        app = create_app(TestConfig)
        app.config["PROPAGATE_EXCEPTIONS"] = False

        @app.route("/boom")
        def boom():
            return 1 / 0

        response = app.test_client().get("/boom")
        self.assertEqual(response.status_code, 500)
        page = response.get_data(as_text=True)
        self.assertIn("Something went wrong on our side", page)
        for leak in ("Traceback", "ZeroDivisionError", "division by zero", "/app/", "File \""):
            self.assertNotIn(leak, page)

    def test_the_development_debugger_is_not_available_in_production(self):
        with mock.patch.dict(os.environ, {"SECRET_KEY": STRONG_SECRET}):
            app = create_app(ProdTestConfig)
        self.assertFalse(app.debug)
        self.assertNotIn("Werkzeug", app.test_client().get("/nothing-here").get_data(as_text=True))


class HealthCheckTests(StaffTestCase):
    def test_health_check_reports_ok(self):
        response = self.app.test_client().get("/healthz")
        self.assertEqual((response.status_code, response.get_json()), (200, {"status": "ok"}))

    def test_health_check_reports_a_database_problem(self):
        with mock.patch.object(db.session, "execute", side_effect=RuntimeError("db down")):
            response = self.app.test_client().get("/healthz")
        self.assertEqual((response.status_code, response.get_json()), (503, {"status": "error"}))


class DemoDataSafetyTests(StaffTestCase):
    def test_demo_orders_cannot_be_created_on_a_live_site(self):
        self.app.config["TESTING"] = False
        self.app.config["DEBUG"] = False
        result = self.app.test_cli_runner().invoke(args=["seed-demo-orders", "--email", self.shop_a.owner.email])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("local development only", result.output)
        self.assertIsNone(User.query.filter_by(email="demo.customer@example.com").first())

    def test_admin_accounts_can_only_come_from_the_terminal_and_never_from_the_form(self):
        response = self.app.test_client().post("/register", data={
            "name": "Sneaky", "email": "sneaky@example.com", "password": PASSWORD,
            "confirm_password": PASSWORD, "role": "admin"})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(User.query.filter_by(email="sneaky@example.com").first())


if __name__ == "__main__":
    unittest.main()
