import re
from urllib.parse import unquote, urlparse

from werkzeug.security import check_password_hash

from app.extensions import db
from app.models.user import (
    ROLE_ADMIN,
    ROLE_CUSTOMER,
    ROLE_DELIVERY,
    ROLE_SHOPKEEPER,
    User,
)

# Roles a visitor may pick on the public registration form. Admin is NOT here.
PUBLIC_ROLES = {
    ROLE_CUSTOMER: "Customer",
    ROLE_SHOPKEEPER: "Shopkeeper",
    ROLE_DELIVERY: "Delivery Partner",
}

# Lengths match the database columns (a database such as PostgreSQL rejects longer values).
MAX_NAME_LENGTH = 100
MAX_EMAIL_LENGTH = 120
EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$")

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128   # stops absurdly long passwords being used to slow the server down

# Which dashboard each role lands on after login.
DASHBOARD_ENDPOINTS = {
    ROLE_CUSTOMER: "dashboard.customer",
    ROLE_SHOPKEEPER: "dashboard.shopkeeper",
    ROLE_DELIVERY: "dashboard.delivery",
    ROLE_ADMIN: "dashboard.admin",
}


def dashboard_endpoint(user):
    return DASHBOARD_ENDPOINTS[user.role]


def validate_registration(name, email, password, confirm_password, role):
    """Return a list of error messages (empty list means the data is valid)."""
    errors = []
    if not name or not (2 <= len(name.strip()) <= MAX_NAME_LENGTH):
        errors.append(f"Please enter your name (2 to {MAX_NAME_LENGTH} characters).")
    if not email or len(email) > MAX_EMAIL_LENGTH or not EMAIL_PATTERN.match(email.strip()):
        errors.append("Please enter a valid email address (for example name@example.com).")
    if len(password or "") < MIN_PASSWORD_LENGTH:
        errors.append(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    elif len(password) > MAX_PASSWORD_LENGTH:
        errors.append(f"Password can be at most {MAX_PASSWORD_LENGTH} characters.")
    if password != confirm_password:
        errors.append("Passwords do not match.")
    if role not in PUBLIC_ROLES:
        errors.append("Please choose a valid account type.")
    if email and User.query.filter_by(email=email.strip().lower()).first():
        errors.append("An account with this email already exists.")
    return errors


def create_user(name, email, password, role):
    """Create and save a user. The password is stored only as a hash."""
    user = User(name=name.strip(), email=email, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def authenticate(email, password):
    """Return the user if email and password match, otherwise None.

    A password check always takes about the same time, even when the email does not exist
    (a dummy hash is checked), so response speed cannot be used to find out which emails
    have accounts.
    """
    from app.security import DUMMY_PASSWORD_HASH

    password = password or ""
    user = User.query.filter_by(email=(email or "").strip().lower()).first()
    if user is None or len(password) > MAX_PASSWORD_LENGTH:
        check_password_hash(DUMMY_PASSWORD_HASH, password[:MAX_PASSWORD_LENGTH])
        return None
    return user if user.check_password(password) else None


def is_safe_redirect(target):
    """Allow only paths on THIS site (blocks open-redirect attacks).

    Browsers treat a backslash like a slash, so a target such as slash + backslash + evil.com
    would really go to another website. Anything with a backslash or control character - written directly or
    percent-encoded - is refused, as is anything starting with "//" or naming a host.
    """
    if not target or not target.startswith("/"):
        return False
    for text in (target, unquote(target)):
        if text.startswith("//") or "\\" in text or any(ord(char) < 32 for char in text):
            return False
    parsed = urlparse(target)
    return not parsed.scheme and not parsed.netloc
