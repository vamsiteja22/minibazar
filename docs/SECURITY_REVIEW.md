# Mini Bazaar - Security Review

Scope: the complete application as of Phase 10 (Flask backend, SQLite/PostgreSQL database, Jinja templates,
JavaScript). The review covered code inspection, targeted attack tests, and running the app in production mode.
Every finding below was either **fixed** or is listed under *Known limitations*.

## 1. Summary

| Area | Result |
|---|---|
| Password security | Good: salted `scrypt` hashes, length limits, timing-safe login, throttling |
| Unauthorized access | Good: role checks on every route plus ownership checks on every lookup |
| Input validation | Good: every form validated on the server; limits match database columns |
| SQL injection | Protected: all queries use the ORM; no SQL is built from user text |
| Cross-site scripting (XSS) | Protected: automatic escaping, no inline scripts, strict Content-Security-Policy |
| CSRF | Protected: every state-changing request needs a token |
| Secure configuration | Fixed: production mode with mandatory secret key, debug off, secure cookies |
| Debug mode | Fixed: cannot be enabled in production |

## 2. Findings that were fixed during this phase

| # | Finding | Severity | Fix |
|---|---|---|---|
| 1 | **Open redirect.** After login, `?next=/\evil.com` was accepted. Browsers read `\` as `/`, so a victim could be sent to another website. | High | `is_safe_redirect` now refuses backslashes, control characters and encoded tricks. Tests cover 13 attack strings. |
| 2 | **Weak secret key by default.** If `SECRET_KEY` was not set, a public default string was used silently. Anyone knowing it could forge session cookies. | High | Production refuses to start unless `SECRET_KEY` is set to 32+ random characters. |
| 3 | **Debug could reach production.** `run.py` always started with debug tools on, and `.env` contained `FLASK_DEBUG=1`. The Werkzeug debugger allows remote code execution. | High | Config is chosen by `APP_ENV`. `run.py` refuses to run in production. `.env.example` has no debug switch. |
| 4 | **Password guessing.** Unlimited login attempts. | Medium | Five wrong passwords lock that visitor and email for 5 minutes (per address + email, so victims are not locked out by attackers elsewhere). |
| 5 | **Account discovery through timing.** A missing email returned faster than a wrong password. | Medium | A dummy password hash is checked, so both take the same time. The message was already identical. |
| 6 | **No browser security headers.** | Medium | Added Content-Security-Policy, X-Frame-Options (no clickjacking), X-Content-Type-Options, Referrer-Policy, Permissions-Policy, and HSTS on HTTPS. |
| 7 | **Demo data command on a live site.** `seed-demo-orders` creates a customer with a publicly known password. | Medium | Disabled unless running in development/testing. |
| 8 | **Loose email validation and no length limits.** `"><x>@y.z` style values were stored, and over-long names or emails would crash PostgreSQL with a server error. | Low | Strict email pattern, name 2-100, email up to 120, password 8-128 characters. |
| 9 | **Raw technical error pages.** A missing form token or a crash showed default server pages. | Low | Friendly 400 and 500 pages; details go only to the server log. |
| 10 | **Foreign keys not enforced on SQLite.** The database itself allowed rows pointing at nothing. | Low | `PRAGMA foreign_keys=ON` on every SQLite connection. All 367 tests still pass. |

## 3. Detailed review by topic

### 3.1 Password security
* Passwords are hashed with Werkzeug's `generate_password_hash` (scrypt, random salt). Plain passwords are never stored or logged. Two users with the same password get different hashes (tested).
* Length 8-128 (the upper limit stops absurdly long inputs from slowing the server).
* Login errors never say whether the email or the password was wrong. A deactivation message is shown only after the correct password.
* No password-reset by email exists yet (listed under future work).

### 3.2 Unauthorized access
* **Layer 1 - role:** `@role_required(...)` (customer, shopkeeper, delivery partner, admin). Visitors go to Login; the wrong role gets 403.
* **Layer 2 - ownership:** every lookup is scoped to the logged-in user (`filter_by(id=..., shop_id=my_shop.id)`, `customer_id=current_user.id`, `delivery_partner_id=current_user.id`). Another user's id returns 404, so nothing leaks.
* Admin accounts can only be created from the terminal (`flask create-admin`); the website refuses `role=admin`.
* A deactivated user is logged out immediately (the session loader ignores inactive users).
* Tests: `test_auth`, `test_shopkeeper` (AuthorizationTests), `test_cart` (TwoCustomersTests), `test_orders` (OrderPrivacyTests), `test_delivery` (PartnerIsolationTests, PartnerAccessTests), `test_admin` (AdminAccessTests).

### 3.3 Input validation (server side)
Every form value is checked on the server (JavaScript checks are only a convenience):

| Input | Rule |
|---|---|
| Name / email / password | 2-100 / valid pattern up to 120 / 8-128 characters |
| Shop | name 2-120, address 5-255, phone 10-digit mobile, description up to 500, coordinates in range |
| Product | name 2-120, price above 0 up to 1,00,000 with at most 2 decimals, stock 0-100,000, real image type, up to 3 MB |
| Cart | quantity a whole number, at most the stock and 99 |
| Checkout | name 2-50, mobile number, address 10-110, note up to 50, cash on delivery only |
| Review | rating 1-5, comment up to 500, only after delivery |
| Category | 2-80 characters, unique ignoring capitals |
| URL parameters | unknown `category`, `sort`, `radius`, `days` fall back to safe defaults |

Uploaded files are identified by their **content** (file signature), not their name or declared type, saved under random names, and only PNG/JPG/WEBP/GIF are allowed (no SVG or HTML).

### 3.4 SQL injection
* All database access uses SQLAlchemy's ORM or constructs (`update()`, `filter`, `join`). Values are always passed as bound parameters.
* Search text is escaped for `%`, `_` and `\` so it is matched literally.
* The only string SQL in the project is fixed text written by the developers: `ALTER TABLE` in the upgrader (fixed table/column list), `SELECT 1` in the health check, and `PRAGMA foreign_keys=ON`.
* An automated test scans every source file and fails if any `execute()`/`text()` call receives a raw string outside that short list.
* Attack strings (`' OR '1'='1`, `'; DROP TABLE users; --`, `UNION SELECT ...`) were sent to search, login, register, URL parameters and shop forms: no errors, no leaks, tables intact.

### 3.5 Cross-site scripting (XSS)
* Jinja auto-escapes everything. There is no `|safe` or `Markup` anywhere in the project (checked by search).
* No inline `<script>` blocks or `onclick=` attributes exist, so the Content-Security-Policy `script-src 'self'` never breaks a page. A test loads 23 pages across all roles to prove it.

### 3.6 CSRF (cross-site request forgery)
* Flask-WTF `CSRFProtect` is enabled globally: every POST needs a token, including logout, cart, checkout, reviews and all admin/shop/delivery actions.
* Session cookies use `SameSite=Lax` and `HttpOnly` (and `Secure` in production) as a second layer.
* Actions that change data are POST-only; opening them by URL gives 405.
* A missing or expired token shows a friendly page. Tests confirm 400 for every major action without a token.

### 3.7 Secure configuration and secret key handling
* Settings come from environment variables; `.env` is git-ignored and `.env.example` documents the names only.
* `APP_ENV=production` enables: debug off, `Secure` cookies, HSTS, HTTPS URLs, and **mandatory** strong `SECRET_KEY`.
* Generate a key: `python -c "import secrets; print(secrets.token_hex(32))"`. Never commit it. Changing it logs everyone out.
* `DATABASE_URL` (with the old `postgres://` spelling fixed automatically) and `UPLOAD_FOLDER` are also environment-driven.
* `TRUSTED_PROXIES` makes the app trust the host's proxy for the real client address and HTTPS detection.

### 3.8 Debug mode
* Development: `DEBUG=True` only when `APP_ENV` is `development`.
* Production: `DEBUG=False`, the Werkzeug console (`/console`) is not exposed, errors show a friendly page, and details go to the log. `run.py` (the development server) refuses to start in production; a real server (`gunicorn`/`waitress` via `wsgi.py`) is used instead.
* The smoke test checks that `/console` is 404 and that no traceback text is ever shown.

## 4. Known limitations (honest list for the viva)

| Limitation | Why it is acceptable now | What a bigger system would do |
|---|---|---|
| Login throttle is kept in memory | Fine for one server process; resets on restart | Store counters in Redis or the database |
| No email verification or password reset | Needs an email service | Add verified emails and reset links |
| No two-factor authentication | Out of scope | Optional TOTP for admins |
| Registration reveals "email already exists" | Common trade-off for a clear message | Generic message plus email confirmation |
| Uploaded photos are served by the app's static route | Only validated images are stored | Object storage/CDN with virus scanning |
| Payment is cash on delivery only | No card data is handled at all | Use a hosted payment page (never store cards) |
| Requests are not rate-limited beyond login | Small audience | Add Flask-Limiter for all POST routes |
| PostgreSQL is supported but the automated tests run on SQLite | Queries use portable SQL | Add a PostgreSQL run to a CI pipeline |

## 5. How to repeat the review

```bash
python -m unittest tests.test_security                # 44 security tests
python -m unittest discover -s tests -t .             # everything
python scripts/local_production_check.py              # boots production mode + smoke test
python scripts/smoke_test.py https://your-site        # after deployment
```
