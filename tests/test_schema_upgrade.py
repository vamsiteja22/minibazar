"""The additive database upgrade that lets older databases keep working."""
import os
import shutil
import tempfile
import unittest

from sqlalchemy import create_engine, inspect, text

from app import create_app
from app.schema_upgrade import COLUMN_ADDITIONS, upgrade_schema
from config import DevelopmentConfig

# The tables exactly as they were before Phase 8 (no is_active, no rejection_reason).
OLD_SCHEMA = [
    """CREATE TABLE users (id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL, email VARCHAR(120) NOT NULL,
       password_hash VARCHAR(255) NOT NULL, role VARCHAR(20) NOT NULL, created_at DATETIME NOT NULL)""",
    """CREATE TABLE shops (id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL, name VARCHAR(120) NOT NULL,
       description TEXT, address VARCHAR(255) NOT NULL, phone VARCHAR(20), is_approved BOOLEAN NOT NULL,
       created_at DATETIME NOT NULL)""",
    "INSERT INTO users VALUES (1, 'Old User', 'old@example.com', 'hash', 'customer', '2026-01-01 00:00:00')",
    "INSERT INTO shops VALUES (1, 1, 'Old Shop', NULL, '1 Old Road', NULL, 1, '2026-01-01 00:00:00')",
]


class SchemaUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.path = os.path.join(self.folder, "old.db")
        self.engine = create_engine(f"sqlite:///{self.path}")
        with self.engine.begin() as connection:
            for statement in OLD_SCHEMA:
                connection.execute(text(statement))

    def tearDown(self):
        self.engine.dispose()
        shutil.rmtree(self.folder, ignore_errors=True)

    def columns(self, table):
        return {c["name"] for c in inspect(self.engine).get_columns(table)}

    def test_adds_missing_columns_and_keeps_the_data(self):
        added = upgrade_schema(self.engine)
        self.assertEqual(sorted(added), ["shops.latitude", "shops.longitude",
                                         "shops.rejection_reason", "users.is_active"])
        self.assertIn("is_active", self.columns("users"))
        self.assertIn("rejection_reason", self.columns("shops"))
        with self.engine.connect() as connection:
            user = connection.execute(text("SELECT name, is_active FROM users")).one()
            shop = connection.execute(
                text("SELECT name, is_approved, rejection_reason, latitude, longitude FROM shops")).one()
        self.assertEqual(tuple(user), ("Old User", 1))          # existing users stay active
        self.assertEqual(tuple(shop), ("Old Shop", 1, None, None, None))   # existing shops are untouched

    def test_running_twice_changes_nothing_more(self):
        upgrade_schema(self.engine)
        self.assertEqual(upgrade_schema(self.engine), [])

    def test_a_brand_new_empty_database_is_skipped(self):
        empty = create_engine("sqlite://")
        self.assertEqual(upgrade_schema(empty), [])
        empty.dispose()

    def test_every_listed_column_exists_on_its_model(self):
        from app.models.shop import Shop
        from app.models.user import User

        models = {"users": User, "shops": Shop}
        for table, column, _definition in COLUMN_ADDITIONS:
            self.assertTrue(hasattr(models[table], column), (table, column))

    def test_the_app_upgrades_an_old_database_when_it_starts(self):
        path = self.path

        class OldDbConfig(DevelopmentConfig):
            SQLALCHEMY_DATABASE_URI = f"sqlite:///{path}"

        app = create_app(OldDbConfig)
        self.assertIn("is_active", self.columns("users"))
        self.assertIn("rejection_reason", self.columns("shops"))
        with app.app_context():
            from app.extensions import db

            db.engine.dispose()

    def test_the_upgrade_command(self):
        path = self.path

        class OldDbConfig(DevelopmentConfig):
            SQLALCHEMY_DATABASE_URI = f"sqlite:///{path}"

        app = create_app(OldDbConfig)        # starting the app already upgrades it...
        result = app.test_cli_runner().invoke(args=["upgrade-db"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("already up to date", result.output)   # ...so the command has nothing left to do
        with app.app_context():
            from app.extensions import db

            db.engine.dispose()


if __name__ == "__main__":
    unittest.main()
