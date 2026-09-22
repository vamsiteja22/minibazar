# MINI BAZAAR

### A Hyperlocal E-Commerce Platform Connecting Customers with Nearby Local Shopkeepers

**Project Report**

| | |
|---|---|
| Project title | Mini Bazaar - Hyperlocal E-Commerce Platform |
| Submitted by | *(Student name / Roll number)* |
| Guide | *(Guide name)* |
| Department / College | *(Department, College name)* |
| Academic year | *(Year)* |
| Technology | Python, Flask, SQLAlchemy, SQLite / PostgreSQL, HTML, CSS, JavaScript |

> **Viewing the diagrams:** the diagrams are written in *Mermaid* text. They display automatically on GitHub and in VS Code
> (Markdown Preview Mermaid Support extension). To use them in a Word/PDF report, paste each block into
> <https://mermaid.live> and export a PNG or SVG.

---

## Table of contents

1. Abstract
2. Introduction
3. Problem statement
4. Existing system
5. Proposed system
6. Objectives
7. Scope
8. User roles
9. Features
10. Technology stack
11. System architecture
12. Database design
13. Use-case diagram
14. Data flow diagrams
15. Order and delivery lifecycle
16. Modules
17. Screenshots
18. Testing
19. Security
20. Deployment
21. Challenges and design decisions
22. Future enhancements
23. Conclusion
24. Appendix (project statistics, folder structure, commands)

---

## 1. Abstract

Small neighbourhood shops - grocers, bakers, dairies and stationers - serve their communities every day, but most of
them have no online presence, while large e-commerce platforms cannot offer the speed and personal trust of a
nearby shop. **Mini Bazaar** is a web-based hyperlocal marketplace that connects customers with shops in their own
area. Customers discover nearby shops, search products, fill a cart and place a cash-on-delivery order. Shopkeepers
manage their shop, stock and incoming orders. Delivery partners receive assigned deliveries and update their
progress, and an administrator approves shops, manages users and categories, and assigns delivery partners.

The system is a modular monolith built with **Python and Flask**, **SQLAlchemy** for data access, **Jinja2** templates
with plain **HTML, CSS and JavaScript**, and **SQLite** (with PostgreSQL support). It has four user roles with strict
role-based and ownership-based access control. Business rules - one shop per order, safe stock reservation, a
validated order lifecycle, verified-purchase reviews - are enforced on the server. Advanced features include
distance-based shop search, product reviews and shop ratings, low-stock alerts and sales analytics. The project is
covered by **367 automated tests**, has been security-reviewed, and is prepared for deployment.

**Keywords:** hyperlocal commerce, Flask, role-based access control, order management, delivery management, web application.

## 2. Introduction

E-commerce has changed how people shop, yet a large share of everyday purchases (vegetables, milk, bread, stationery)
still happens at nearby shops. These shopkeepers know their customers and deliver quickly, but they lack tools for
online ordering, stock management and delivery coordination. Mini Bazaar brings these local shops online in one
platform designed to be simple to use, secure and easy to explain.

## 3. Problem statement

*How can local shopkeepers offer online ordering and delivery to customers in their neighbourhood without building
their own website, while giving customers a trustworthy, simple way to shop from several nearby stores?*

Sub-problems addressed:

1. Customers cannot easily find out which nearby shops sell what they need, or whether items are in stock.
2. Shopkeepers have no simple way to publish products, track stock and manage orders online.
3. Coordinating delivery between shop, rider and customer is manual (phone calls and messages).
4. A multi-user platform needs safe handling of accounts, permissions, stock and money-related data.

## 4. Existing system

| Existing approach | Limitations |
|---|---|
| Phone calls / WhatsApp orders with the shop | No catalogue or prices, no stock visibility, orders are easily lost, no status tracking, no history |
| Large national e-commerce and quick-commerce apps | Not focused on the local shopkeeper, commissions and fees, shopkeepers lose their own customer relationship |
| Shopkeepers building individual websites | Costly to build and maintain, low discoverability, no shared delivery network |
| Paper records for stock and sales | Time-consuming, error-prone, no analytics or alerts |

## 5. Proposed system

Mini Bazaar is one web platform where many local shops list products and receive orders, with built-in delivery
coordination and administration:

* **Customers** browse approved shops, search and filter products, find shops **near them**, add items to a cart,
  place cash-on-delivery orders, track them, and review what they received.
* **Shopkeepers** get a dashboard with products, stock, **low-stock alerts**, incoming orders and **sales analytics**.
* **Delivery partners** see assigned deliveries with pickup and drop-off details and update each stage.
* **Admins** approve shops, manage users and categories, monitor the whole platform and assign delivery partners.

Advantages: one place for many shops, orders from a single shop at a time (simple logistics), verified reviews,
real-time stock reservation, clear order status for everyone, and strict security.

## 6. Objectives

1. Provide an easy online storefront for local shops (shop profile, products, stock, photos).
2. Let customers discover, compare and order from nearby shops quickly and safely.
3. Implement a complete, validated order lifecycle from placement to delivery.
4. Support delivery partners with clear tasks and status updates.
5. Give administrators control over shops, users, categories, orders and delivery assignment.
6. Protect data with authentication, authorization, input validation and secure configuration.
7. Build a maintainable, modular, well-tested codebase suitable for further extension.
8. Prepare the system for real deployment with documentation and repeatable checks.

## 7. Scope

**In scope (implemented):**
* Registration and login for customers, shopkeepers, delivery partners; admin created from the terminal.
* Shops, products (with photos), categories, search, filters, nearby-shop search.
* Cart (one shop per cart), checkout, cash-on-delivery orders, order history, cancellation.
* Shopkeeper order handling, delivery assignment and delivery status tracking.
* Admin dashboard, user management, shop approval, category management.
* Reviews and ratings, low-stock alerts, sales analytics.
* Security review, automated tests, deployment preparation and documentation.

**Out of scope (future work):** online payments, live map tracking, SMS/e-mail notifications, coupons, mobile apps,
multi-shop carts, refunds, and automatic delivery-partner allocation.

## 8. User roles

| Role | How the account is created | Main responsibilities |
|---|---|---|
| **Visitor** (not logged in) | - | Browse shops and products, search |
| **Customer** | Register page | Cart, checkout, orders, reviews |
| **Shopkeeper** | Register page (then admin approves the shop) | Shop profile, products, stock, orders, analytics |
| **Delivery partner** | Register page | Accept and complete assigned deliveries |
| **Admin** | Terminal command `flask create-admin` only | Approve shops, manage users/categories, view all orders, assign partners |

## 9. Features

**Customer:** registration and login; browse approved shops and products; search by product, shop, category or description;
category filters and price sorting; nearby-shop search with distance; product pages with stock and ratings; cart with quantity
control and stock checks; delivery-fee calculation (free above ₹199); checkout with validated delivery details; order confirmation;
order history with a progress bar; cancel while pending; write, edit and delete reviews after delivery.

**Shopkeeper:** create and edit the shop (with optional map location); add, edit, hide and delete products with photos; quick
price/stock editing; low-stock alerts and filter; incoming orders with accept, reject, prepare and ready actions; sales analytics
(7/30/90 days) with chart, top products and categories; dashboard summary.

**Delivery partner:** dashboard of assigned deliveries; pickup shop details; customer delivery address and cash to collect; accept,
picked up, out for delivery, delivered; delivery history.

**Admin:** platform statistics; user list with search and deactivation; shop approval or rejection with a reason; category
management; all orders with filters; assign or reassign delivery partners with workload limits; delivery-partner overview.

**Platform:** role-based access; CSRF protection; secure headers; login throttling; friendly error pages; health check endpoint.

## 10. Technology stack

| Layer | Technology | Purpose |
|---|---|---|
| Language | Python 3 | Application logic |
| Web framework | Flask 3 (application factory, blueprints) | Routing, requests, templates |
| Database access | Flask-SQLAlchemy / SQLAlchemy 2 | Models, queries, relationships |
| Database | SQLite (development, tested); PostgreSQL (production option) | Data storage |
| Authentication | Flask-Login, Werkzeug password hashing (scrypt) | Sessions and passwords |
| Forms security | Flask-WTF (CSRF protection) | Forged-request protection |
| Migrations | Flask-Migrate + built-in additive upgrader | Database changes |
| Templates | Jinja2 (auto-escaping) | Server-rendered HTML |
| Front end | HTML5, CSS3 (own design system), vanilla JavaScript | User interface (no framework) |
| Production server | gunicorn / waitress | Serving the live site |
| Testing | `unittest` + Flask test client | 367 automated tests |
| Tools | Git, headless Edge/Chrome (screenshots), Mermaid (diagrams) | Development and documentation |

## 11. System architecture

The application is a **modular monolith**: one deployable Flask application divided into clear layers and modules.

```mermaid
flowchart TB
    Browser["Web browser<br/>HTML, CSS, JavaScript"] -->|HTTP requests| Proxy["Web server / proxy<br/>HTTPS"]
    Proxy --> WSGI["Production server<br/>gunicorn or waitress"]
    WSGI --> App

    subgraph App["Flask application - create_app()"]
        direction TB
        Sec["Security layer<br/>CSRF, headers, login throttle, error pages"]
        Routes["Routes (blueprints)<br/>main, shop, auth, customer, shopkeeper,<br/>delivery, admin, dashboard"]
        Services["Services - business rules<br/>catalog, cart, checkout, order, delivery,<br/>admin, shop, product, review, inventory,<br/>analytics, location, auth"]
        Models["Models - SQLAlchemy<br/>User, Shop, Category, Product, Cart, Order,<br/>OrderItem, Delivery, Review"]
        Templates["Templates (Jinja2)<br/>and static files"]
        Sec --> Routes --> Services --> Models
        Routes --> Templates
    end

    Models --> DB[("Database<br/>SQLite or PostgreSQL")]
    Services --> Files[("Uploaded product photos")]
```

**Design principles**

* **Routes stay thin.** They read the request, call a service, and choose a template.
* **Services hold the rules.** Cart limits, stock reservation, order transitions and permissions checks live in services, so they
  are testable without a browser.
* **Models describe data only** (columns, relationships, simple validation).
* **Two-layer authorization:** a role check on the route and an ownership check in every query.

**Typical request (placing an order)**

```mermaid
sequenceDiagram
    actor C as Customer
    participant R as Route /checkout
    participant S as checkout_service
    participant DB as Database

    C->>R: POST delivery details (+ CSRF token)
    R->>R: Check role = customer, validate form
    R->>S: place_order(customer, details)
    S->>DB: Load cart, re-check availability and prices
    S->>DB: Reserve stock (UPDATE ... WHERE stock >= qty)
    S->>DB: Create Order + OrderItems, empty the cart
    alt anything fails
        S->>DB: Roll back everything
        S-->>R: Error message
    else success
        S->>DB: Commit
        S-->>R: New order
        R-->>C: Redirect to confirmation page
    end
```

## 12. Database design

The database has **10 tables**. The diagram below is generated directly from the SQLAlchemy models by
`scripts/generate_er_diagram.py`, so it always matches the code.

### 12.1 ER diagram

```mermaid
erDiagram
    CARTS ||--o{ CART_ITEMS : "cart_id"
    PRODUCTS ||--o{ CART_ITEMS : "product_id"
    USERS ||--o| CARTS : "customer_id"
    ORDERS ||--o| DELIVERIES : "order_id"
    USERS |o--o{ DELIVERIES : "delivery_partner_id"
    ORDERS ||--o{ ORDER_ITEMS : "order_id"
    PRODUCTS ||--o{ ORDER_ITEMS : "product_id"
    USERS ||--o{ ORDERS : "customer_id"
    SHOPS ||--o{ ORDERS : "shop_id"
    SHOPS ||--o{ PRODUCTS : "shop_id"
    CATEGORIES |o--o{ PRODUCTS : "category_id"
    USERS ||--o{ REVIEWS : "customer_id"
    PRODUCTS ||--o{ REVIEWS : "product_id"
    USERS ||--o| SHOPS : "owner_id"

    CART_ITEMS {
        int id PK
        int cart_id FK
        int product_id FK
        int quantity
    }
    CARTS {
        int id PK
        int customer_id FK,UK
        datetime created_at
    }
    CATEGORIES {
        int id PK
        string name UK
    }
    DELIVERIES {
        int id PK
        int order_id FK,UK
        int delivery_partner_id FK
        string status
        datetime assigned_at
        datetime delivered_at
    }
    ORDER_ITEMS {
        int id PK
        int order_id FK
        int product_id FK
        int quantity
        decimal price_at_purchase
    }
    ORDERS {
        int id PK
        int customer_id FK
        int shop_id FK
        decimal total_amount
        string delivery_address
        string status
        string payment_status
        datetime created_at
    }
    PRODUCTS {
        int id PK
        int shop_id FK
        int category_id FK
        string name
        text description
        decimal price
        int stock_quantity
        string image
        bool is_available
        datetime created_at
    }
    REVIEWS {
        int id PK
        int customer_id FK
        int product_id FK
        int rating
        text comment
        datetime created_at
    }
    SHOPS {
        int id PK
        int owner_id FK,UK
        string name
        text description
        string address
        string phone
        float latitude
        float longitude
        bool is_approved
        string rejection_reason
        datetime created_at
    }
    USERS {
        int id PK
        string name
        string email UK
        string password_hash
        string role
        bool is_active
        datetime created_at
    }
```

### 12.2 Relationships in words

* A **User** has one role (customer, shopkeeper, delivery partner, admin). A shopkeeper **owns one Shop**.
* A **Shop** has many **Products**; each Product belongs to one optional **Category**.
* A customer has at most one **Cart** with many **CartItems** (each item refers to a Product; a product appears once per cart).
* An **Order** belongs to one customer and **one shop** (business rule) and has many **OrderItems**. Each OrderItem stores
  `price_at_purchase`, so later price changes never alter old orders.
* An Order has at most one **Delivery** (`order_id` is unique), handled by one delivery-partner User.
* A **Review** links a customer to a product (one review per customer per product).

### 12.3 Data dictionary (main tables)

| Table | Important columns | Notes |
|---|---|---|
| `users` | name, email (unique), password_hash, role, is_active | Passwords stored only as salted hashes |
| `shops` | owner_id (unique), name, address, phone, latitude, longitude, is_approved, rejection_reason | Not public until approved |
| `categories` | name (unique) | Managed by the admin |
| `products` | shop_id, category_id, name, price (decimal), stock_quantity, image, is_available | Price uses exact decimals, never floats |
| `carts` / `cart_items` | customer_id (unique) / cart_id, product_id, quantity | One row per product per cart |
| `orders` | customer_id, shop_id, total_amount, delivery_address, status, payment_status | Status follows the lifecycle in section 15 |
| `order_items` | order_id, product_id, quantity, price_at_purchase | Price frozen at purchase |
| `deliveries` | order_id (unique), delivery_partner_id, status, assigned_at, delivered_at | Created when the admin assigns a partner |
| `reviews` | customer_id, product_id, rating (1-5), comment | Unique per customer and product |

Integrity: primary keys, foreign keys (enforced on SQLite too), unique constraints, non-null columns, sensible defaults, and
validation rules in models and services. New columns are added to older databases by a safe additive upgrader.

## 13. Use-case diagram

Use cases are grouped by the actor who performs them. A customer can also do everything a visitor can.

```mermaid
flowchart LR
    V([Visitor])
    C([Customer])
    S([Shopkeeper])
    D([Delivery Partner])
    A([Admin])

    subgraph G1["Public"]
        U1(("Browse shops and products"))
        U2(("Search and filter"))
        U3(("Find nearby shops"))
        U4(("Register and log in"))
    end
    subgraph G2["Customer"]
        U5(("Manage cart"))
        U6(("Checkout and place order"))
        U7(("Track and cancel orders"))
        U8(("Write reviews"))
    end
    subgraph G3["Shopkeeper"]
        U9(("Manage shop and products"))
        U10(("View low-stock alerts"))
        U11(("Process orders"))
        U12(("View sales analytics"))
    end
    subgraph G4["Delivery"]
        U13(("Accept and update deliveries"))
        U14(("View delivery history"))
    end
    subgraph G5["Administration"]
        U15(("Approve or reject shops"))
        U16(("Manage users and categories"))
        U17(("View all orders and statistics"))
        U18(("Assign delivery partners"))
    end

    V --- G1
    C --- G1
    C --- G2
    S --- G3
    D --- G4
    A --- G5
```

## 14. Data flow diagrams

### 14.1 Level 0 (context diagram)

```mermaid
flowchart LR
    C["Customer"] -->|"registration, search, cart, order, review, location"| P(("Mini Bazaar<br/>System"))
    P -->|"shops, products, order status, confirmation"| C
    S["Shopkeeper"] -->|"shop details, products, stock, order updates"| P
    P -->|"orders, alerts, analytics"| S
    D["Delivery Partner"] -->|"accept, pickup, delivery updates"| P
    P -->|"assigned deliveries, addresses"| D
    A["Admin"] -->|"approvals, assignments, category and user changes"| P
    P -->|"statistics, all orders, pending items"| A
```

### 14.2 Level 1

Solid arrows show data given to a process or stored; dotted arrows show results returned to a person.

```mermaid
flowchart TB
    C["Customer"]
    S["Shopkeeper"]
    D["Delivery Partner"]
    A["Admin"]

    P1(("1.0 Account<br/>and access"))
    P2(("2.0 Catalogue<br/>and search"))
    P3(("3.0 Cart and<br/>checkout"))
    P4(("4.0 Order<br/>processing"))
    P5(("5.0 Delivery<br/>management"))
    P6(("6.0 Admin<br/>functions"))
    P7(("7.0 Reviews and<br/>analytics"))

    D1[("D1 Users")]
    D2[("D2 Shops and<br/>products")]
    D3[("D3 Carts")]
    D4[("D4 Orders<br/>and items")]
    D5[("D5 Deliveries")]
    D6[("D6 Reviews")]

    C -->|"register, log in"| P1
    C -->|"search, location"| P2
    C -->|"cart, checkout"| P3
    C -->|"reviews"| P7
    S -->|"shop, products, stock"| P2
    S -->|"accept, prepare, ready"| P4
    A -->|"approve, assign"| P6
    D -->|"delivery updates"| P5

    P1 --> D1
    P2 --> D2
    P3 --> D3
    P3 -->|"new order"| P4
    P4 --> D4
    P6 --> D1
    P6 --> D2
    P6 -->|"create delivery"| P5
    P5 --> D5
    P7 --> D6

    P4 -.->|"order status"| C
    P4 -.->|"ready orders"| A
    P5 -.->|"assigned jobs"| D
    P7 -.->|"analytics, alerts"| S
```

## 15. Order and delivery lifecycle

### 15.1 Order states

```mermaid
stateDiagram-v2
    [*] --> Pending : customer places order (stock reserved)
    Pending --> Accepted : shopkeeper accepts
    Pending --> Rejected : shopkeeper rejects (stock returned)
    Pending --> Cancelled : customer cancels (stock returned)
    Accepted --> Preparing : shopkeeper starts preparing
    Preparing --> ReadyForPickup : shopkeeper marks ready
    ReadyForPickup --> OutForDelivery : delivery partner starts delivery
    OutForDelivery --> Delivered : delivery partner hands over (cash marked paid)
    Delivered --> [*]
    Rejected --> [*]
    Cancelled --> [*]
```

Every change is checked against one table of valid transitions and a rule about **who** may perform it (shopkeeper, customer or
delivery partner). Anything else is refused and changes nothing.

### 15.2 Delivery states

```mermaid
stateDiagram-v2
    [*] --> Assigned : admin assigns a partner (order must be Ready for pickup)
    Assigned --> Accepted : partner accepts
    Accepted --> PickedUp : partner collects from shop
    PickedUp --> OutForDelivery : partner sets off
    OutForDelivery --> Delivered : partner delivers
    Delivered --> [*]
```

Controls: only Ready-for-pickup orders can be assigned; only active partners; at most 5 active jobs per partner; the admin can
reassign only until the partner accepts; the order and delivery are updated in a single database transaction.

## 16. Modules

| # | Module | Purpose | Main files |
|---|---|---|---|
| 1 | Authentication and access | Registration, login, logout, roles, deactivation, redirect safety | `routes/auth.py`, `services/auth_service.py`, `decorators.py` |
| 2 | Catalogue and search | Approved shops, visible products, categories, search, popularity | `routes/shop.py`, `services/catalog_service.py` |
| 3 | Cart | One-shop cart, quantity/stock rules, totals, delivery fee | `routes/customer.py`, `services/cart_service.py` |
| 4 | Checkout and orders | Atomic order creation, stock reservation, history, cancellation | `services/checkout_service.py`, `services/order_service.py` |
| 5 | Shopkeeper | Shop profile, products, photos, orders, dashboard | `routes/shopkeeper.py`, `services/shop_service.py`, `product_service.py` |
| 6 | Delivery | Assignment, partner tasks, status flow | `routes/delivery.py`, `services/delivery_service.py` |
| 7 | Admin | Statistics, users, shop approval, categories, all orders | `routes/admin.py`, `services/admin_service.py` |
| 8 | Nearby shops | Coordinates, haversine distance, radius filter | `services/location_service.py` |
| 9 | Reviews and ratings | Verified-purchase reviews, shop ratings | `services/review_service.py` |
| 10 | Inventory alerts | Low-stock detection | `services/inventory_service.py` |
| 11 | Analytics | Sales report, daily series, top products | `services/analytics_service.py` |
| 12 | Security | Headers, throttling, error pages, production config | `security.py`, `config.py` |
| 13 | Database tools | Additive upgrader, CLI (`init-db`, `create-admin`, `approve-shop`, ...) | `schema_upgrade.py`, `cli.py` |
| 14 | User interface | Templates, macros, CSS design system, JavaScript | `templates/`, `static/css`, `static/js` |

## 17. Screenshots

All screenshots are generated from the running application with realistic demonstration data
(`python scripts/capture_screenshots.py`).

### Public pages

| | |
|---|---|
| ![Home page](screenshots/01_home.png)<br>**Figure 1** - Home page | ![Nearby shops](screenshots/04_shops_nearby.png)<br>**Figure 2** - Nearby shop search with distances |
| ![Login](screenshots/02_login.png)<br>**Figure 3** - Login | ![Register](screenshots/03_register.png)<br>**Figure 4** - Registration with role selection |
| ![Search](screenshots/06_search.png)<br>**Figure 5** - Search results | ![Mobile](screenshots/23_mobile_home.png)<br>**Figure 6** - Mobile layout |

### Customer

| | |
|---|---|
| ![Product page with reviews](screenshots/05_product_reviews.png)<br>**Figure 7** - Product page with reviews | ![Cart](screenshots/07_cart.png)<br>**Figure 8** - Shopping cart |
| ![Checkout](screenshots/08_checkout.png)<br>**Figure 9** - Checkout | ![Order confirmation](screenshots/09_order_confirmation.png)<br>**Figure 10** - Order confirmation |
| ![Order history](screenshots/10_customer_orders.png)<br>**Figure 11** - Order history with progress | ![Customer dashboard](screenshots/11_customer_dashboard.png)<br>**Figure 12** - Customer dashboard |

### Shopkeeper

| | |
|---|---|
| ![Shopkeeper dashboard](screenshots/12_shopkeeper_dashboard.png)<br>**Figure 13** - Dashboard with low-stock alert | ![Products](screenshots/13_shopkeeper_products.png)<br>**Figure 14** - Product management |
| ![Order details](screenshots/14_shopkeeper_order.png)<br>**Figure 15** - Order details and actions | ![Analytics](screenshots/15_shopkeeper_analytics.png)<br>**Figure 16** - Sales analytics |
| ![Shop location](screenshots/16_shop_location_form.png)<br>**Figure 17** - Shop location form | |

### Admin

| | |
|---|---|
| ![Admin dashboard](screenshots/17_admin_dashboard.png)<br>**Figure 18** - Admin dashboard | ![Shop approval](screenshots/18_admin_shops.png)<br>**Figure 19** - Shop approval |
| ![Users](screenshots/19_admin_users.png)<br>**Figure 20** - User management | ![Assign partner](screenshots/20_admin_order_assign.png)<br>**Figure 21** - Assigning a delivery partner |

### Delivery partner

| | |
|---|---|
| ![Delivery dashboard](screenshots/21_delivery_dashboard.png)<br>**Figure 22** - Delivery dashboard | ![Delivery task](screenshots/22_delivery_task.png)<br>**Figure 23** - Delivery task details |

## 18. Testing

### 18.1 Strategy

| Level | Description |
|---|---|
| Unit tests | Rules such as distance calculation, coordinate parsing, validation and the order workflow |
| Integration tests | Forms, pages, permissions and the database working together (Flask test client, in-memory database) |
| Security tests | Configuration, headers, login throttling, injection attempts, error pages |
| Smoke test | A running site (local or live) answers correctly: `scripts/smoke_test.py` |
| Manual tests | 131 documented cases in `docs/TEST_PLAN.md` for demonstration and viva |

### 18.2 Results

| Item | Result |
|---|---|
| Automated tests | **367 tests, all passing** (`python -m unittest discover -s tests -t .`) |
| Local production check | **23 of 23** smoke checks passing (production mode, waitress server, fresh database) |
| Documented manual cases | 131 (Registration, Login, Role access, Shops, Products, Search, Cart, Checkout, Orders, Delivery, Admin, Invalid input, Advanced features, Security) |

| Test module | Tests | Area |
|---|---|---|
| `test_auth` | 16 | Registration, login, roles, CSRF |
| `test_registration_limits` | 7 | Email/name validation |
| `test_models` | 4 | Models and relationships |
| `test_catalog` | 25 | Browsing, visibility, search |
| `test_shopkeeper` | 37 | Shop, products, seller authorization |
| `test_cart` | 40 | Cart rules, privacy |
| `test_orders` | 42 | Checkout, order workflow, cancellation |
| `test_delivery` | 20 | Delivery lifecycle, isolation |
| `test_admin` | 32 | Admin functions |
| `test_location` | 25 | Nearby shops |
| `test_reviews` | 25 | Reviews and ratings |
| `test_low_stock` | 21 | Low-stock alerts |
| `test_analytics` | 23 | Sales analytics |
| `test_schema_upgrade` | 6 | Database upgrade |
| `test_security` | 44 | Security review |

The full list of test cases (ID, feature, steps, expected result, actual-result and status placeholders) is in
**`docs/TEST_PLAN.md`**.

## 19. Security

A dedicated review (see **`docs/SECURITY_REVIEW.md`**) covered password security, authorization, input validation,
SQL injection, CSRF, secret key handling and debug mode. Ten issues were found and fixed, including an open-redirect bypass, a
silent default secret key, debug mode reaching production, missing login throttling and missing security headers.

Key protections: salted scrypt password hashes; role and ownership checks on every request; server-side validation
that matches database limits; ORM-only database access; automatic output escaping with a strict Content-Security-Policy; CSRF
tokens on every state-changing request; strict production configuration.

## 20. Deployment

Deployment is documented in **`docs/DEPLOYMENT.md`**: environment variables, production server, database choices,
step-by-step PythonAnywhere (recommended for beginners) and Render guides, a smoke test for the live site, and a troubleshooting table.
The application has **not** been deployed automatically; it is ready to deploy on request.

## 21. Challenges and design decisions

| Challenge | Decision |
|---|---|
| Keeping the project explainable | Modular monolith with routes, services and models; no framework on the front end |
| Money accuracy | Decimal prices; totals calculated only on the server; prices frozen in order items |
| Overselling stock | Stock reserved with one conditional database update inside a transaction that rolls back completely on any failure |
| Simple logistics | One shop per cart and per order |
| Trustworthy reviews | Only customers with a delivered order can review |
| Changing an existing database | A tiny additive upgrader adds new columns without losing data |
| Nearby search without a paid map service | Store latitude/longitude and calculate distance with the haversine formula |
| Access control mistakes | Two layers (role + ownership) and tests that attack every route as every other role |

## 22. Future enhancements

| Area | Idea |
|---|---|
| Payments | Online payment gateway (hosted payment page), refunds |
| Notifications | E-mail and SMS/WhatsApp order updates; in-app notifications |
| Delivery | Live map tracking, automatic partner allocation, delivery-fee by distance, delivery time slots |
| Shopping | Coupons and offers, wishlist, repeat-order button, multiple addresses, multi-shop carts |
| Accounts | E-mail verification, password reset, two-factor authentication for admins |
| Shopkeepers | Bulk product upload, opening hours, product variants, inventory history |
| Analytics | Downloadable reports, comparisons with previous periods, admin-level charts |
| Scale | PostgreSQL in production, background jobs, caching, image storage on cloud, Docker, CI pipeline |
| Product | Mobile app or installable web app (PWA), regional languages, recommendation features |

## 23. Conclusion

Mini Bazaar demonstrates a complete, realistic multi-role e-commerce platform. It solves the stated problem by giving local shops
an online storefront, giving customers a simple way to find nearby shops and order safely, and coordinating delivery and administration
in one system. The project applies core software-engineering practice: layered architecture, careful data modelling, business rules
enforced on the server, security review, extensive automated testing, and deployment preparation with documentation. It is small
enough to explain end to end and structured well enough to extend with the future enhancements listed above.

## 24. Appendix

### 24.1 Project statistics

| Item | Count |
|---|---|
| Python source (application and configuration) | 43 files, about 4,100 lines |
| HTML templates | 44 files, about 2,300 lines |
| CSS and JavaScript | 2 files, about 770 lines |
| Automated tests | 19 files, about 4,200 lines, **367 tests** |
| Database tables | 10 |
| Web routes | 57 |
| Documentation | 5 documents plus 24 screenshots |

### 24.2 Folder structure

```
minibazar/
├── app/
│   ├── __init__.py          application factory (create_app)
│   ├── extensions.py        database, login, CSRF objects
│   ├── security.py          headers, login throttle, error pages
│   ├── decorators.py        role_required, shop_required
│   ├── schema_upgrade.py    additive database upgrader
│   ├── cli.py               terminal commands
│   ├── models/              10 database tables
│   ├── routes/              main, shop, auth, customer, shopkeeper, delivery, admin, dashboard
│   ├── services/            business rules (one module per feature)
│   ├── templates/           Jinja2 pages (auth, shop, customer, shopkeeper, delivery, admin, errors)
│   └── static/              css, js, uploads
├── tests/                   367 automated tests
├── scripts/                 smoke_test, local_production_check, capture_screenshots, generate_er_diagram
├── docs/                    this report, test plan, security review, deployment guide, presentation, screenshots
├── config.py                development / production settings
├── run.py                   development server
├── wsgi.py                  production entry point
├── requirements.txt         libraries
├── requirements-prod.txt    libraries + production server
├── Procfile                 start command for hosts
└── .env.example             list of settings
```

### 24.3 Useful commands

```bash
python run.py                                  # start the app on your computer
python -m unittest discover -s tests -t .      # run all 367 tests
flask --app run init-db                        # create tables and default categories
flask --app run create-admin                   # create an admin account
flask --app run approve-shop --email <owner>   # approve a shop from the terminal
flask --app run upgrade-db                     # add new columns to an older database
python scripts/local_production_check.py       # run everything in production mode + smoke test
python scripts/capture_screenshots.py          # regenerate the screenshots
python scripts/generate_er_diagram.py          # regenerate the ER diagram
```

### 24.4 References

1. Flask documentation - <https://flask.palletsprojects.com>
2. SQLAlchemy documentation - <https://docs.sqlalchemy.org>
3. Flask-Login and Flask-WTF documentation
4. OWASP Top Ten - <https://owasp.org/www-project-top-ten/>
5. Haversine formula for great-circle distance
6. Mermaid diagram syntax - <https://mermaid.js.org>
