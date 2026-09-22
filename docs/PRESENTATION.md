# Mini Bazaar - Presentation Guide

A ready-to-use plan for the project presentation, live demonstration and viva/interview questions.
Suggested length: **12-15 minutes** (10 slides + 5-minute live demo). Pictures for the slides are in
`docs/screenshots/` and `docs/diagrams/`.

---

## Part 1 - Slide outline

### Slide 1 - Title
**Mini Bazaar: A Hyperlocal E-Commerce Platform**
*Connecting customers with nearby local shopkeepers.*
Your name, roll number, guide, college.
> Say: "Mini Bazaar helps neighbourhood shops sell online and helps people buy from shops close to them."

### Slide 2 - Project introduction
* Everyday shopping (vegetables, milk, bread, stationery) still happens at local shops.
* Those shops have no easy way to go online.
* Mini Bazaar = one platform for many local shops, with delivery and administration built in.
* Four users: Customer, Shopkeeper, Delivery partner, Admin.
*Picture:* `screenshots/01_home.png`

### Slide 3 - The problem
* Customers cannot see which nearby shop has what, or whether it is in stock.
* Shopkeepers cannot manage stock and orders online.
* Delivery is arranged by phone calls; nothing is tracked.
* Multi-user systems risk wrong access, overselling stock and wrong prices.

### Slide 4 - Existing system
| Today | Problem |
|---|---|
| Phone / WhatsApp orders | No catalogue, no stock view, no history |
| Big e-commerce apps | Not local, fees, shopkeeper loses the customer |
| Own website per shop | Expensive, hard to find |
| Paper stock records | Slow, error-prone |

### Slide 5 - Proposed system
* One marketplace for many local shops, **one shop per order** (simple logistics).
* Nearby-shop search, verified reviews, low-stock alerts, sales analytics.
* Clear order lifecycle everyone can see.
* Secure by design: roles, ownership checks, validation, CSRF, headers.

### Slide 6 - Architecture
*Picture:* `diagrams/01_system_architecture.png`
* Modular monolith: **Routes → Services → Models → Database**.
* Routes are thin; business rules live in services (easy to test and explain).
* Flask + SQLAlchemy + Jinja + plain HTML/CSS/JS. SQLite now, PostgreSQL ready.

### Slide 7 - Database
*Picture:* `diagrams/03_er_diagram.png`
* 10 tables; an order belongs to one customer and one shop; a delivery belongs to one order.
* `price_at_purchase` keeps history correct when prices change.

### Slide 8 - Features by role
| Customer | Shopkeeper | Delivery partner | Admin |
|---|---|---|---|
| Browse, search, nearby shops | Shop and product management | Assigned deliveries | Approve shops |
| Cart, checkout, order tracking | Orders: accept, prepare, ready | Accept, pick up, deliver | Users and categories |
| Reviews and ratings | Low-stock alerts | Delivery history | All orders, statistics |
| | Sales analytics | | Assign delivery partners |

### Slide 9 - Order and delivery lifecycle
*Picture:* `diagrams/07_order_states.png`
Customer places → Shopkeeper accepts → Preparing → Ready → **Admin assigns partner** → Partner accepts → Picked up → Out for delivery → Delivered.
* Only valid transitions, and only by the right role.
* Stock is reserved at order time and returned if rejected or cancelled.

### Slide 10 - Testing and security
* **367 automated tests**, all passing; 131 documented manual test cases.
* Security review: 10 issues found and fixed (open-redirect bypass, secret key, debug mode, login throttling, headers...).
* Production run verified with a smoke test (23 of 23 checks).

### Slide 11 - Future scope
Online payments · live delivery tracking on a map · SMS/e-mail notifications · coupons · mobile app (PWA) · automatic delivery allocation · password reset and verified e-mail.

### Slide 12 - Thank you / Questions
Repository link, live link (if deployed), your contact.

---

## Part 2 - Live demonstration script (about 5 minutes)

**Before you start:** run `python run.py`; have five browser windows/profiles ready (customer, shopkeeper, partner, admin, and a visitor).
Create the accounts in advance (see `docs/TEST_PLAN.md` section 3) or use the demo world from `scripts/capture_screenshots.py` as a guide.

| Step | Who | What to show | What to say |
|---|---|---|---|
| 1 | Visitor | Home page, search "bread", open Shops, use *nearby* with a typed location | "Anyone can browse. Only approved shops are visible, and nearby search uses the haversine distance." |
| 2 | Shopkeeper | Dashboard: low-stock alert, Products list, add a product | "Shopkeepers manage stock. Low products raise an alert." |
| 3 | Admin | Admin > Shops: approve the new shop | "Shops are hidden until an admin approves them." |
| 4 | Customer | Add two items to the cart; try adding from another shop | "One shop per order: the system explains and offers to start a new cart." |
| 5 | Customer | Checkout with an invalid phone, then a valid one; confirmation page | "Everything is validated on the server; the total is calculated on the server, never trusted from the browser." |
| 6 | Shopkeeper | Orders: Accept → Preparing → Ready | "Status changes follow a fixed workflow." |
| 7 | Admin | Orders > *Needs a delivery partner* > assign | "Delivery assignment is controlled by the admin." |
| 8 | Partner | Accept → Picked up → Out for delivery → Delivered | "The order status and delivery stay in sync; cash on delivery is marked paid." |
| 9 | Customer | Order shows Delivered; write a review | "Reviews are unlocked only after delivery." |
| 10 | Shopkeeper | Analytics page | "Sales figures count delivered goods only." |

**Security moment (30 seconds):** as a customer type `/shopkeeper/products` → 403. Log in as a second shopkeeper and open the first shop's order URL → 404.

---

## Part 3 - Questions you may be asked (with short answers)

**General**
1. *Why Flask and not Django?* Flask is small and explicit, so each part (routes, services, models) is visible and easy to explain. Django would give more built in but hide detail.
2. *Why a monolith?* One deployable unit is simpler to build, test and deploy; it is still modular (routes/services/models).
3. *Why no React?* The pages are server-rendered with Jinja; plain JavaScript is used only for small conveniences. Fewer moving parts.

**Database**
4. *How do you avoid wrong prices in old orders?* `order_items.price_at_purchase` stores the price at purchase time.
5. *Why Decimal for money?* Floats give rounding errors (0.1 + 0.2). Decimal is exact.
6. *Can two customers buy the last item?* No. Stock is reserved with one conditional `UPDATE ... WHERE stock >= qty`; only one succeeds, and failures roll back everything.
7. *SQLite or PostgreSQL?* SQLite for development and tests; PostgreSQL supported through `DATABASE_URL` for production.

**Security**
8. *How are passwords stored?* Salted scrypt hashes (Werkzeug). Never plain text.
9. *How do you stop a customer opening shopkeeper pages?* Two layers: a role check on the route and an ownership filter in every query. Wrong role → 403; someone else's data → 404.
10. *What is CSRF and how do you prevent it?* A malicious site making your browser send a request. Every form carries a secret token that the server checks (Flask-WTF), and cookies are `SameSite=Lax`.
11. *How do you prevent SQL injection?* Only the ORM with bound parameters; an automated test fails if raw SQL strings appear.
12. *What did the security review find?* An open redirect using a backslash, a default secret key, debug mode risk, no login throttling, no security headers... all fixed and tested.
13. *What if someone guesses passwords?* After 5 wrong attempts that visitor+email waits 5 minutes.

**Business logic**
14. *Why one shop per order?* Simplifies delivery and payment; each order has one pickup point.
15. *Who can cancel an order?* The customer, only while it is Pending. After the shopkeeper accepts, it is committed.
16. *What happens to stock when an order is rejected?* It is returned automatically, once.
17. *Why can only delivered customers review?* To keep reviews genuine (verified purchase).
18. *How does nearby search work?* Shops store latitude/longitude; the browser gives the customer's position; the server computes the great-circle distance with the haversine formula and filters by radius. No paid map service.

**Testing and deployment**
19. *How did you test?* 367 automated tests (unit, integration, security), 131 documented manual cases, and a smoke test for the running site.
20. *How would you deploy?* Set `APP_ENV=production` and a strong `SECRET_KEY`, use gunicorn/waitress via `wsgi.py`, PostgreSQL or SQLite on a persistent disk, HTTPS, then run `scripts/smoke_test.py`. Full steps in `docs/DEPLOYMENT.md`.
21. *What are the limitations?* Login throttle is in memory; no email verification/password reset; no online payment; automated tests run on SQLite. All listed in the security review.

**Improvement / thinking**
22. *What would you add next?* Payments through a hosted gateway, notifications, live tracking, and automatic partner allocation.
23. *What was the hardest part?* Keeping stock, orders and deliveries consistent: solved with atomic updates, transactions and a single table of valid status changes.
24. *What did you learn?* Layered design, secure defaults, writing tests first for risky rules, and documenting decisions.

---

## Part 4 - Presentation checklist

| ☐ | Item |
|---|---|
| ☐ | Slides created from Part 1 with pictures from `docs/screenshots/` and `docs/diagrams/` |
| ☐ | Demo accounts created and password written down (not shown on screen) |
| ☐ | `python -m unittest discover -s tests -t .` run once before the demo (shows `OK`) |
| ☐ | Live URL (if deployed) tested with `python scripts/smoke_test.py <url>` |
| ☐ | Backup: screenshots and a short screen recording in case the internet or laptop fails |
| ☐ | Printed or PDF copy of `docs/PROJECT_REPORT.md` and `docs/TEST_PLAN.md` |
