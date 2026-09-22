"""Tiny, safe database upgrader.

`db.create_all()` creates missing TABLES but never adds new COLUMNS to tables that
already exist. When a later phase adds a column, this module adds it to an older
database so nobody has to delete their data.

It only ever ADDS columns, and it skips columns that already exist, so it is safe
to run any number of times. It runs automatically when the app starts, and can be
run by hand with:  flask --app run upgrade-db
"""
from sqlalchemy import inspect, text

# (table, column, SQL type and default). These are fixed strings written by us -
# never user input.
COLUMN_ADDITIONS = [
    ("users", "is_active", "BOOLEAN NOT NULL DEFAULT 1"),
    ("shops", "rejection_reason", "VARCHAR(255)"),
    ("shops", "latitude", "FLOAT"),
    ("shops", "longitude", "FLOAT"),
]


def upgrade_schema(engine):
    """Add any missing columns. Returns a list like ['users.is_active'] of what was added."""
    added = []
    inspector = inspect(engine)
    for table, column, definition in COLUMN_ADDITIONS:
        if not inspector.has_table(table):
            continue  # brand-new database: create_all() will build it with every column
        existing = {col["name"] for col in inspector.get_columns(table)}
        if column not in existing:
            with engine.begin() as connection:
                connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))
            added.append(f"{table}.{column}")
    return added
