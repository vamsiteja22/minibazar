"""Application settings.

Which settings are used is chosen by the APP_ENV environment variable:
    APP_ENV=development   (default) debug tools on, relaxed cookies - for your own computer
    APP_ENV=production    debug OFF, strict cookies, and a real SECRET_KEY is REQUIRED

Values that differ between computers (secret key, database address, ...) are read from
environment variables. On your own computer they can live in a `.env` file (never share
or commit it - see .env.example for the list of settings).
"""
import os

from dotenv import load_dotenv

# Read values from the .env file (if it exists) into environment variables.
load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

DEV_SECRET_KEY = "dev-secret-key-change-me"   # only ever acceptable on your own computer
MIN_SECRET_KEY_LENGTH = 32


def _database_url():
    """DATABASE_URL, or a local SQLite file. Fixes the old 'postgres://' spelling some hosts give."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        return "sqlite:///" + os.path.join(BASE_DIR, "minibazar.db")
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


class Config:
    """Settings shared by every environment."""

    SECRET_KEY = os.environ.get("SECRET_KEY", DEV_SECRET_KEY)
    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # A shopkeeper is warned about any available product with this much stock or less.
    LOW_STOCK_THRESHOLD = 5

    # Times are stored in UTC and shown shifted by this many minutes (330 = India, UTC+5:30).
    DISPLAY_TZ_OFFSET_MINUTES = int(os.environ.get("DISPLAY_TZ_OFFSET_MINUTES", "330"))

    # Product image uploads: saved here, and requests bigger than 3 MB are refused.
    # On a host with a temporary disk, point UPLOAD_FOLDER at a persistent disk.
    UPLOAD_FOLDER = os.environ.get(
        "UPLOAD_FOLDER", os.path.join(BASE_DIR, "app", "static", "uploads", "products")
    )
    MAX_CONTENT_LENGTH = 3 * 1024 * 1024

    # Session cookie safety: JavaScript cannot read it, and it is not sent
    # along with requests coming from other websites.
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # Login protection: after this many wrong passwords, wait before trying again.
    MAX_FAILED_LOGINS = 5
    LOGIN_LOCKOUT_SECONDS = 300

    # How many reverse proxies (the host's web server) sit in front of the app.
    # Needed so the app sees the real visitor address and knows the site is on HTTPS.
    TRUSTED_PROXIES = int(os.environ.get("TRUSTED_PROXIES", "0"))

    # Set to True by ProductionConfig: adds the HSTS header and requires HTTPS cookies.
    HTTPS_ONLY = False


class DevelopmentConfig(Config):
    """Settings used while developing on your own computer."""

    DEBUG = True


class ProductionConfig(Config):
    """Settings for the live website."""

    DEBUG = False
    TESTING = False
    HTTPS_ONLY = True
    SESSION_COOKIE_SECURE = True          # cookies are only sent over HTTPS
    REMEMBER_COOKIE_SECURE = True
    REMEMBER_COOKIE_HTTPONLY = True
    PREFERRED_URL_SCHEME = "https"
    TRUSTED_PROXIES = int(os.environ.get("TRUSTED_PROXIES", "1"))   # hosts like Render / PythonAnywhere

    @classmethod
    def validate(cls):
        """Refuse to start with unsafe settings. Called by create_app()."""
        secret = os.environ.get("SECRET_KEY", "")
        if not secret or secret == DEV_SECRET_KEY or len(secret) < MIN_SECRET_KEY_LENGTH:
            raise RuntimeError(
                "SECRET_KEY is missing or too weak for production. Set the SECRET_KEY environment "
                f"variable to a random value of at least {MIN_SECRET_KEY_LENGTH} characters. "
                "Create one with:  python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        cls.SECRET_KEY = secret


CONFIGS = {"development": DevelopmentConfig, "production": ProductionConfig}


def get_config(name=None):
    """The settings class for APP_ENV (or the given name). Unknown names are an error."""
    name = (name or os.environ.get("APP_ENV", "development")).strip().lower()
    if name not in CONFIGS:
        raise RuntimeError(f"Unknown APP_ENV '{name}'. Use one of: {', '.join(CONFIGS)}.")
    return CONFIGS[name]
