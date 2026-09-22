"""Security helpers: browser security headers, login throttling, friendly error pages.

Everything here is small and switched on in create_app(). Each part has one job:

* add_security_headers  - tells the browser to block clickjacking, content sniffing and
                          scripts from other websites (Content-Security-Policy).
* LoginThrottle         - slows down password guessing.
* register_error_pages  - friendly pages for a bad form token (400) and server errors (500),
                          so visitors never see technical details.
"""
import time

from flask import render_template, request
from flask_wtf.csrf import CSRFError
from werkzeug.security import generate_password_hash

from app.extensions import db

# Only our own files may run scripts. Styles allow inline attributes because pages colour
# their cards with style="..." (all values come from our own code, never from users).
CONTENT_SECURITY_POLICY = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "font-src 'self'",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])


def add_security_headers(app):
    @app.after_request
    def set_headers(response):
        response.headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        # The site may ask for the visitor's location (the "Use my location" button); nothing else.
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(self), camera=(), microphone=(), payment=()"
        )
        if app.config.get("HTTPS_ONLY") and request.is_secure:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response


class LoginThrottle:
    """Remembers wrong passwords and blocks a visitor after too many.

    The key is "visitor address + email", so one person guessing cannot lock out the real
    owner of the account from a different address. State is kept in memory: it is reset
    when the app restarts and is not shared between several server processes - enough to
    stop casual guessing; a large site would use a shared store such as Redis.
    """

    def __init__(self, max_failures=5, lockout_seconds=300, clock=time.time):
        self.max_failures = max_failures
        self.lockout_seconds = lockout_seconds
        self.clock = clock
        self._failures = {}   # key -> list of times of recent wrong passwords

    @staticmethod
    def key(address, email):
        return f"{address}|{(email or '').strip().lower()}"

    def _recent(self, key):
        cutoff = self.clock() - self.lockout_seconds
        recent = [t for t in self._failures.get(key, []) if t > cutoff]
        if recent:
            self._failures[key] = recent
        else:
            self._failures.pop(key, None)
        return recent

    def seconds_left(self, key):
        """0 if the visitor may try, otherwise how many seconds until they can."""
        recent = self._recent(key)
        if len(recent) < self.max_failures:
            return 0
        return max(1, int(recent[0] + self.lockout_seconds - self.clock()))

    def record_failure(self, key):
        self._recent(key)
        self._failures.setdefault(key, []).append(self.clock())

    def clear(self, key):
        self._failures.pop(key, None)


# A real password hash of a random string. Checking a password against it takes as long
# as checking against a real account, so "no such email" and "wrong password" look the same.
DUMMY_PASSWORD_HASH = generate_password_hash("not-a-real-password-just-for-timing")


def register_error_pages(app):
    @app.errorhandler(CSRFError)
    def bad_form_token(error):
        return render_template("errors/400.html"), 400

    @app.errorhandler(500)
    def server_error(error):
        db.session.rollback()   # leave the database in a clean state
        return render_template("errors/500.html"), 500
