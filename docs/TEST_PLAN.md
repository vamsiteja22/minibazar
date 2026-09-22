# Mini Bazaar - Test Plan and Test Cases

## 1. Purpose

This document lists the test cases used to verify Mini Bazaar. Every case has an ID, the feature
under test, the steps, the expected result, and empty **Actual Result** and **Status** columns to fill in
during a test session (for example the final demonstration).

The last column, **Automated coverage**, points to the automated test that checks the same behaviour, so
the whole plan is backed by the test suite in the `tests/` folder (367 tests, all passing).

## 2. Test approach

| Level | What it checks | How |
|---|---|---|
| Unit tests | Pure rules: distance maths, coordinate parsing, status workflow, validation | `python -m unittest` |
| Integration tests | Pages, forms, database and permissions working together, using Flask's test client and an in-memory database | `python -m unittest` |
| Security tests | Configuration, headers, login protection, injection, error pages | `tests/test_security.py` |
| Smoke test | A running site answers correctly (local or live) | `python scripts/smoke_test.py <url>` |
| Manual (UI) tests | What a person sees and does in a browser | Cases in this document |

Run everything automatically:

```bash
python -m unittest discover -s tests -t .
```

## 3. Test environment and data

* Python 3.13, Flask 3, SQLite (tests use an in-memory database).
* Browsers: Microsoft Edge / Google Chrome (latest), at desktop width and about 500 px wide.
* Start the app with `python run.py` and open `http://127.0.0.1:5000`.

Suggested manual test accounts (password for all: `Test@12345`). Create them on the Register page, except the admin:

| Account | Role | How to create |
|---|---|---|
| `cathy@test.com` | Customer | Register page |
| `olive@test.com` | Customer (second customer) | Register page |
| `sam@test.com` | Shopkeeper (owns "Sam's Store") | Register page |
| `tina@test.com` | Shopkeeper (second shop) | Register page |
| `ravi@test.com` | Delivery partner | Register page |
| `admin@test.com` | Admin | `flask --app run create-admin` |

Pre-conditions used by several cases: Sam's shop exists and is **approved** (`flask --app run approve-shop --email sam@test.com`,
or Admin > Shops > Approve) and has products such as "Apple" (price 10, stock 20) and "Pear" (price 20.50, stock 3).

## 4. Test cases

**Status legend:** fill in *Pass*, *Fail* or *Blocked*. The "Actual Result" column is left blank for the tester.

### 4.1 Registration

| ID | Feature | Steps | Expected result | Actual result | Status | Automated coverage |
|---|---|---|---|---|---|---|
| REG-01 | Register a customer | 1. Open Register.<br>2. Choose *Customer*, enter a name, a new email, password `Test@12345` twice.<br>3. Submit. | Redirected to Login with "Account created! Please log in." The user exists. | | | `test_auth` RegistrationTests |
| REG-02 | Register a shopkeeper and a delivery partner | Repeat REG-01 choosing *Shopkeeper*, then *Delivery Partner*. | Both accounts are created with the chosen role. | | | `test_auth` RegistrationTests |
| REG-03 | Admin role cannot be chosen | Send the register form with `role=admin` (edit the page with the browser's developer tools). | Registration is refused with "Please choose a valid account type." No user is created. | | | `test_auth` RegistrationTests; `test_security` DemoDataSafetyTests |
| REG-04 | Duplicate email | Register an email that already exists (also try different capital letters). | "An account with this email already exists." No second user. | | | `test_auth` RegistrationTests |
| REG-05 | Password rules | Try passwords of 7 characters, 129 characters, and two that do not match. | Each is refused with a clear message (8 to 128 characters, must match). | | | `test_auth`; `test_security` PasswordSecurityTests |
| REG-06 | Invalid email | Try `plain`, `a@b`, `a b@x.com`, `a'b@x.com`, and an address longer than 120 characters. | Refused: "Please enter a valid email address". | | | `test_registration_limits` EmailValidationTests |
| REG-07 | Name limits | Try a name of 1 character and one of 101 characters. | Refused: name must be 2 to 100 characters. | | | `test_registration_limits` NameValidationTests |
| REG-08 | Password is stored safely | After REG-01, inspect the `users` table (`instance/minibazar.db`). | `password_hash` starts with `scrypt:` or `pbkdf2:`; the plain password is nowhere in the database. | | | `test_security` PasswordSecurityTests |

### 4.2 Login and logout

| ID | Feature | Steps | Expected result | Actual result | Status | Automated coverage |
|---|---|---|---|---|---|---|
| LOG-01 | Customer login | Log in as `cathy@test.com`. | Landing page is the Customer dashboard. Navigation shows Cart, Orders, Logout. | | | `test_auth` LoginAndAccessTests |
| LOG-02 | Role-based landing page | Log in as a shopkeeper, a delivery partner, then the admin. | Each lands on their own dashboard (Shopkeeper, Delivery, Admin). | | | `test_auth` LoginAndAccessTests |
| LOG-03 | Wrong password | Enter a valid email with a wrong password. | "Invalid email or password." Not logged in. | | | `test_auth` LoginAndAccessTests |
| LOG-04 | Unknown email | Enter an email that does not exist. | The **same** message as LOG-03 (no hint whether the email exists). | | | `test_auth`; `test_security` PasswordSecurityTests |
| LOG-05 | Logout | Press Logout, then press the browser Back button and open `/cart`. | Logged out; protected pages send you to Login. | | | `test_auth` LoginAndAccessTests |
| LOG-06 | Logout needs a form post | Type `/logout` directly in the address bar. | Page is not allowed (405); you stay logged in. | | | `test_auth` LoginAndAccessTests |
| LOG-07 | Login throttling | Enter a wrong password 5 times, then the correct one. | "Too many failed attempts. Please try again in N minutes." Even the correct password is refused until the wait ends. | | | `test_security` LoginProtectionTests |
| LOG-08 | Redirect after login | Open `/cart` while logged out, log in. | You return to the page you asked for. A `next` value pointing to another website is ignored. | | | `test_auth`; `test_security` RedirectSafetyTests |
| LOG-09 | Deactivated account | Admin deactivates a user; that user (already logged in) clicks any page; then tries to log in again. | The user is logged out at once; login says the account has been deactivated. | | | `test_admin` UserManagementTests |

### 4.3 Role-based access

| ID | Feature | Steps | Expected result | Actual result | Status | Automated coverage |
|---|---|---|---|---|---|---|
| RBAC-01 | Visitors are sent to login | While logged out open `/cart`, `/orders`, `/dashboard/admin`, `/shopkeeper/products`, `/delivery/history`. | Every one redirects to the Login page. | | | `test_cart`, `test_admin`, `test_delivery`; smoke test |
| RBAC-02 | Customer cannot open shop pages | As a customer open `/shopkeeper/products`, `/shopkeeper/orders`. | "403 - Access denied". | | | `test_auth` LoginAndAccessTests |
| RBAC-03 | Customer cannot open admin pages | As a customer open `/admin/users`, `/dashboard/admin`. | 403 Access denied. | | | `test_admin` AdminAccessTests |
| RBAC-04 | Shopkeeper cannot use the cart | As a shopkeeper open `/cart`, `/checkout`. | 403 Access denied. | | | `test_cart` AccessTests |
| RBAC-05 | Delivery partner is limited | As a partner open `/shopkeeper/products`, `/admin/orders`, `/cart`. | 403 Access denied for each. | | | `test_delivery` PartnerAccessTests |
| RBAC-06 | Admin cannot use customer pages | As admin open `/cart` and `/shopkeeper/products`. | 403 Access denied. | | | `test_admin` AdminAccessTests |
| RBAC-07 | Shopkeepers are isolated | Log in as Tina and open a product or order URL belonging to Sam's shop. | "Page not found" (404): the item is not revealed. | | | `test_shopkeeper` AuthorizationTests |
| RBAC-08 | Customers are isolated | Log in as Olive and open one of Cathy's order URLs or cart item actions. | 404; Cathy's data is unchanged. | | | `test_orders` OrderPrivacyTests; `test_cart` TwoCustomersTests |
| RBAC-09 | Partners are isolated | Log in as a second partner and open the first partner's delivery task. | 404. | | | `test_delivery` PartnerIsolationTests |
| RBAC-10 | Wrong-role actions change nothing | As a partner or customer send a POST to a shop, product or admin URL. | Refused; data unchanged. | | | `test_delivery`, `test_admin` |

### 4.4 Shop creation and approval

| ID | Feature | Steps | Expected result | Actual result | Status | Automated coverage |
|---|---|---|---|---|---|---|
| SHOP-01 | Shopkeeper without a shop | Log in as a new shopkeeper and open Products. | Redirected to "Create your shop". | | | `test_shopkeeper` ShopProfileTests |
| SHOP-02 | Create a shop | Enter name, address, phone, description; submit. | Shop created, status "Awaiting approval". | | | `test_shopkeeper` ShopProfileTests |
| SHOP-03 | Shop is hidden until approved | As a visitor open Shops and search for the new shop. | It does not appear; its page returns 404. | | | `test_catalog` VisibilityTests |
| SHOP-04 | Admin approves | Admin > Shops > *Waiting for approval* > Approve. | Shop appears for customers; owner sees "Approved". | | | `test_admin` ShopApprovalTests |
| SHOP-05 | Admin rejects with a reason | Enter a reason of fewer than 5 characters, then a proper reason. | Short reason refused; proper one hides the shop and the owner sees the reason. | | | `test_admin` ShopApprovalTests |
| SHOP-06 | Resubmission | As the owner edit a rejected shop and save. | Status returns to "Awaiting approval". | | | `test_admin` ShopApprovalTests |

### 4.5 Product management

| ID | Feature | Steps | Expected result | Actual result | Status | Automated coverage |
|---|---|---|---|---|---|---|
| PROD-01 | Add a product | Shopkeeper > Add product: name, category, price `25.50`, stock `10`. | Product appears in the list, available. | | | `test_shopkeeper` ProductTests |
| PROD-02 | Price validation | Try price `0`, `-5`, `abc`, `1.234`, `100001`. | Each refused with a clear message; nothing saved. | | | `test_shopkeeper` ProductTests |
| PROD-03 | Stock validation | Try stock `-1`, `1.5`, empty, `100001`. | Each refused. | | | `test_shopkeeper` ProductTests |
| PROD-04 | Upload a photo | Add a product with a PNG under 3 MB. | Photo shows on the product card and page. | | | `test_shopkeeper` ProductTests |
| PROD-05 | Reject a fake image | Upload a text file renamed `evil.png`, and a file over 3 MB. | Refused (real content is checked); the large file shows a friendly "too large" page. | | | `test_shopkeeper` ProductTests |
| PROD-06 | Edit price, stock, category | Edit a product and save. | Changes appear on the list and on the customer page. | | | `test_shopkeeper` ProductTests |
| PROD-07 | Quick update | Change price and stock in the list row; press Save. | Updated; invalid values refused. | | | `test_shopkeeper` ProductTests |
| PROD-08 | Hide / show | Press Hide on a product. | It disappears for customers; Show restores it. | | | `test_shopkeeper` ProductTests |
| PROD-09 | Delete an unused product | Delete a product that was never ordered. | Product and its photo are removed. | | | `test_shopkeeper` ProductTests |
| PROD-10 | Delete a product that was ordered | Delete a product that appears in an old order. | It is hidden instead, and old orders still show it. | | | `test_shopkeeper` ProductTests |

### 4.6 Product search and browsing

| ID | Feature | Steps | Expected result | Actual result | Status | Automated coverage |
|---|---|---|---|---|---|---|
| SRCH-01 | Search by name | Search for `apple` and `APPLE`. | Same results either way. | | | `test_catalog` SearchTests |
| SRCH-02 | Search finds shops, categories, descriptions | Search a shop name, a category name, and a word from a description. | Matching shops and products are listed. | | | `test_catalog` SearchTests |
| SRCH-03 | No results | Search `zzzzzz`. | "Nothing found" with category suggestions. | | | `test_catalog` SearchTests |
| SRCH-04 | Category filter and sort | Products page: pick a category, sort by price low to high. | Only that category, cheapest first. | | | `test_catalog` FilterAndSortTests |
| SRCH-05 | Hidden and unapproved items never appear | Search for a hidden product and for a product of an unapproved shop. | Not found anywhere (lists, search, direct link). | | | `test_catalog` VisibilityTests |
| SRCH-06 | Special characters | Search `%`, `_`, `<script>alert(1)</script>`. | Treated as plain text; nothing runs; page stays normal. | | | `test_catalog` SearchTests; `test_security` InjectionTests |

### 4.7 Cart

| ID | Feature | Steps | Expected result | Actual result | Status | Automated coverage |
|---|---|---|---|---|---|---|
| CART-01 | Add to cart | As a customer press Add on a product. | "Added 1 x Apple"; cart badge increases. | | | `test_cart` AddToCartTests |
| CART-02 | Same product twice | Add Apple twice. | One cart line with quantity 2. | | | `test_cart` AddToCartTests |
| CART-03 | Change quantity | Cart page: change quantity to 4 and press Update. | Line total and summary update. | | | `test_cart` UpdateRemoveTests |
| CART-04 | Stock limit | Try to add more than the stock (Pear has 3). | "Only 3 of Pear in stock". Also blocked when the cart already holds some. | | | `test_cart` AddToCartTests |
| CART-05 | Remove / clear | Remove one item, then Clear cart. | Removed; "Your cart is empty" state. | | | `test_cart` UpdateRemoveTests |
| CART-06 | Totals and delivery fee | Cart worth under 199, then over 199. | Delivery fee is 25, then Free. Total = items + delivery. | | | `test_cart` TotalsTests |
| CART-07 | One shop per cart | With Sam's items in the cart, add a product from Tina's shop. | A page explains the rule and offers "Clear my cart and add..." or "Keep my cart". Nothing is mixed. | | | `test_cart` OneShopPerCartTests |
| CART-08 | Unavailable products | Add a product, then (as the shopkeeper) lower its stock or hide it. Reopen the cart. | The line is flagged in red and checkout is disabled until fixed. | | | `test_cart` ProblemLineTests |
| CART-09 | Invalid quantities | Send quantity `0`, `-1`, `abc`, `1.5`. | "Please enter a quantity of 1 or more". | | | `test_cart` AddToCartTests |
| CART-10 | Carts are private | Customer B tries to change customer A's cart item. | 404; A's cart unchanged. | | | `test_cart` TwoCustomersTests |

### 4.8 Checkout

| ID | Feature | Steps | Expected result | Actual result | Status | Automated coverage |
|---|---|---|---|---|---|---|
| CHK-01 | Empty cart | Open `/checkout` with an empty cart. | Redirected to the cart with a message. | | | `test_cart` CheckoutPageTests |
| CHK-02 | Summary shown | Open checkout with items. | Items, delivery fee and total match the cart. | | | `test_cart` CheckoutPageTests |
| CHK-03 | Delivery details validation | Submit with a 1-letter name, phone `12345`, address `short`, note of 51 characters. | Each field shows an error; no order is created; typed values are kept. | | | `test_orders` CheckoutValidationTests |
| CHK-04 | Payment method | Only "Cash on delivery" can be chosen; try sending `payment=online`. | Online is disabled; a forged value is refused. | | | `test_orders` CheckoutValidationTests |
| CHK-05 | Price changed while checking out | Open checkout; the shopkeeper changes a price; press Place order. | "Prices in your cart changed"; nothing is ordered; new total shown. | | | `test_orders` PlaceOrderTests |
| CHK-06 | Stock ran out | After adding to cart the shop sets stock to 0; press Place order. | Sent back to the cart with a clear message; no order. | | | `test_orders` UnavailableProductTests |
| CHK-07 | Double click | Press Place order twice quickly. | Exactly one order; stock reduced once. | | | `test_orders` CheckoutValidationTests |
| CHK-08 | Browser cannot set the amount | Edit the form to send `total_amount=1`, `price=0.01`, another `shop_id`, `status=delivered`. | Ignored: the server calculates everything. | | | `test_orders` PlaceOrderTests |

### 4.9 Order creation and status updates

| ID | Feature | Steps | Expected result | Actual result | Status | Automated coverage |
|---|---|---|---|---|---|---|
| ORD-01 | Place an order | Complete checkout. | Confirmation page with order number, items, total and address. Order status Pending. | | | `test_orders` PlaceOrderTests |
| ORD-02 | Stock and cart effects | Compare product stock and the cart before and after. | Stock reduced by the ordered quantity; cart emptied. | | | `test_orders` PlaceOrderTests |
| ORD-03 | All-or-nothing | (Automated only) Make the second product fail during ordering. | Whole order is undone, including the first product's stock. | | | `test_orders` UnavailableProductTests |
| ORD-04 | Order history and details | Open My orders, then a single order. | Newest first, with status and progress bar. | | | `test_orders` OrderHistoryAndDashboardTests |
| ORD-05 | Shopkeeper sees the order | As the shopkeeper open Orders. | The new order is listed, with a badge on the Orders tab. | | | `test_orders` ShopkeeperLifecycleTests |
| ORD-06 | Accept, prepare, ready | Press Accept, Start preparing, Mark ready for pickup. | Status changes Accepted, Preparing, Ready for pickup; the customer sees each change. | | | `test_orders` ShopkeeperLifecycleTests |
| ORD-07 | Reject | Reject a pending order. | Status Rejected; stock returned. | | | `test_orders` ShopkeeperLifecycleTests |
| ORD-08 | Customer cancels | Cancel a Pending order; try after the shop accepted. | Cancelled and stock returned; after acceptance the button is gone and the action is refused. | | | `test_orders` CustomerCancelTests |
| ORD-09 | Invalid status jumps | Try to send `preparing` or `ready` on a Pending order (URL edit). | Refused: "that action is not available". | | | `test_orders` WorkflowRuleTests |
| ORD-10 | Prices are frozen | Change a product price after an order. | The old order still shows the price paid. | | | `test_orders` PlaceOrderTests |

### 4.10 Delivery assignment and status

| ID | Feature | Steps | Expected result | Actual result | Status | Automated coverage |
|---|---|---|---|---|---|---|
| DEL-01 | Orders needing a partner | Admin > Orders > *Needs a delivery partner*. | Lists only orders that are Ready for pickup without a partner. | | | `test_delivery` FullJourneyTests |
| DEL-02 | Assign a partner | Open the order, choose a partner, assign. | Delivery created (Assigned); partner sees it. | | | `test_admin` OrderViewAndAssignTests |
| DEL-03 | Assignment rules | Try to assign a Pending order, an already assigned order, a deactivated partner, a customer id. | Each refused with a clear message. | | | `test_admin` OrderViewAndAssignTests |
| DEL-04 | Workload limit | Give one partner 5 active deliveries, then assign a 6th. | "already has 5 active deliveries". | | | `test_admin` OrderViewAndAssignTests |
| DEL-05 | Reassign until accepted | Change the partner before acceptance; try after acceptance. | Allowed before; refused after ("already accepted"). | | | `test_admin` OrderViewAndAssignTests |
| DEL-06 | Partner sees job details | Partner opens the task. | Pickup shop name, address, phone; customer delivery address; items; cash to collect. | | | `test_delivery` PartnerTaskViewTests |
| DEL-07 | Delivery steps | Partner presses Accept, Picked up, Start delivery, Delivered. | Delivery status advances; order becomes Out for delivery, then Delivered; cash marked Paid. | | | `test_delivery` FullJourneyTests |
| DEL-08 | Steps cannot be skipped | Try `deliver` right after Assigned; press Accept twice. | Refused; state unchanged. | | | `test_delivery` PartnerTaskViewTests |
| DEL-09 | Delivery history | Partner opens History. | Only their finished deliveries, newest first. | | | `test_delivery` HistoryAndDashboardTests |

### 4.11 Admin

| ID | Feature | Steps | Expected result | Actual result | Status | Automated coverage |
|---|---|---|---|---|---|---|
| ADM-01 | Dashboard statistics | Open the admin dashboard. | Total users, shops, products, orders, plus orders by status and sales. | | | `test_admin` DashboardStatsTests |
| ADM-02 | Manage users | Filter by role, search by name/email. | Correct lists; admin accounts are not listed. | | | `test_admin` UserManagementTests |
| ADM-03 | Deactivate / reactivate | Deactivate then reactivate a customer. | Cannot log in while deactivated; can after reactivation. | | | `test_admin` UserManagementTests |
| ADM-04 | Deactivate a shopkeeper | Deactivate an owner. | Their shop leaves the public site; re-approval is needed after reactivation. | | | `test_admin` UserManagementTests |
| ADM-05 | Partner with active jobs | Deactivate a partner who is mid-delivery. | Refused: "deliveries in progress". | | | `test_admin` UserManagementTests |
| ADM-06 | Categories | Add "Pet Supplies"; add a duplicate; rename; delete an unused one; delete one that products use. | Duplicates refused (any capitalisation); unused deleted; used one refused. | | | `test_admin` CategoryTests |
| ADM-07 | View all orders | Admin > Orders, try every filter. | All orders visible with customer, shop, delivery and total. | | | `test_admin` OrderViewAndAssignTests |
| ADM-08 | Delivery partners page | Admin > Delivery partners. | Each partner with active and delivered counts. | | | `test_admin` OrderViewAndAssignTests |
| ADM-09 | Admin created from terminal only | Try to register as admin on the website; run `flask --app run create-admin`. | Website refuses; terminal command works. | | | `test_auth` AdminCliTests |
| ADM-10 | Admin accounts are protected | Send a deactivate request for an admin user id. | 404; admin unaffected. | | | `test_admin` UserManagementTests |

### 4.12 Invalid input handling

| ID | Feature | Steps | Expected result | Actual result | Status | Automated coverage |
|---|---|---|---|---|---|---|
| INP-01 | Unknown pages and ids | Open `/nothing`, `/products/9999`, `/shops/9999`. | Friendly 404 page. | | | `test_catalog` EmptySiteTests |
| INP-02 | Bad URL parameters | Open `/products?category=abc`, `/products?sort=weird`, `/shops?radius=banana`. | Page loads normally; bad values ignored. | | | `test_catalog`, `test_location` |
| INP-03 | Long text | Enter 500+ characters into shop description, review comment, product name. | Refused with a clear message (limits match the database). | | | `test_shopkeeper`, `test_reviews` |
| INP-04 | HTML in text | Enter `<b>bold</b>` as a product name and `<script>` in a review. | Shown as plain text; nothing executes. | | | `test_catalog`, `test_reviews` |
| INP-05 | Wrong request type | Type an action URL such as `/cart/clear` in the address bar. | "405 Method Not Allowed"; nothing happens. | | | `test_cart` AccessTests |
| INP-06 | Missing form token | Submit a form from a page opened long ago / from another tab after logout. | Friendly "That page expired" page (400). | | | `test_security` FriendlyErrorTests |
| INP-07 | Empty fields | Submit each main form empty. | Every required field shows an error; no crash. | | | various |
| INP-08 | Numbers as text | Type `abc` in quantity, price, stock, latitude fields. | Refused with a message. | | | `test_cart`, `test_shopkeeper`, `test_location` |

### 4.13 Advanced features (Phase 9)

| ID | Feature | Steps | Expected result | Actual result | Status | Automated coverage |
|---|---|---|---|---|---|---|
| NEAR-01 | Save a shop location | Shopkeeper > My shop > Edit; enter latitude/longitude or press *Use my current location*. | Saved; profile shows a map link. | | | `test_location` ShopLocationFormTests |
| NEAR-02 | Location validation | Enter latitude `95`, longitude `200`, only one of the two, or text. | Each refused with a clear message. | | | `test_location` ParseCoordinateTests |
| NEAR-03 | Nearby search | Shops page: choose 5 km, press *Use my location* (or type coordinates). | Only shops within range, nearest first, with "x m/km away". | | | `test_location` NearbyShopsTests |
| NEAR-04 | Shops without location | Search nearby when some shops have no location. | They are left out, and a note says how many. | | | `test_location` NearbyShopsTests |
| NEAR-05 | Distance accuracy | Compare two known points with an online calculator. | Within about 1 % (straight-line distance). | | | `test_location` DistanceMathTests |
| REV-01 | Review only after delivery | As a customer open a product you never received. | Message explains reviews unlock after delivery; no form. | | | `test_reviews` EligibilityTests |
| REV-02 | Post a review | After a delivered order, give 4 stars and a comment. | Review appears with "Your review"; average rating updates. | | | `test_reviews` WritingReviewsTests |
| REV-03 | One review per product | Post again with different stars. | The same review is updated, not duplicated. | | | `test_reviews` WritingReviewsTests |
| REV-04 | Delete own review | Press *Delete my review*. | Removed; others' reviews are untouched. | | | `test_reviews` DeletingReviewsTests |
| REV-05 | Review validation | Rating `0`/`6`/empty; comment over 500 characters. | Refused. | | | `test_reviews` WritingReviewsTests |
| REV-06 | Shop rating | Open shop cards after several reviews. | Shop shows the average of its products' ratings and the review count. | | | `test_reviews` RatingDisplayTests |
| LOW-01 | Low-stock alert | Set a product's stock to 3 (threshold 5). | Dashboard alert, red badge on Products tab, "Low stock" label. | | | `test_low_stock` ShopkeeperAlertPagesTests |
| LOW-02 | Sold-out vs low | Set another product's stock to 0. | Listed as "Sold out", separate from "Only 3 left". | | | `test_low_stock` InventoryRuleTests |
| LOW-03 | Low-stock filter | Products > *Low stock*. | Only alerting products. | | | `test_low_stock` ShopkeeperAlertPagesTests |
| LOW-04 | Restock clears the alert | Set stock to 30 in the row and Save. | Alert disappears. | | | `test_low_stock` ShopkeeperAlertPagesTests |
| ANA-01 | Analytics figures | Open Analytics with several delivered orders. | Sales, orders, average, items and top products match the orders (delivery fees excluded). | | | `test_analytics` NumbersTests |
| ANA-02 | Period selection | Choose 7, 30 and 90 days. | Chart shows that many days; totals change accordingly. | | | `test_analytics` PeriodBoundaryTests |
| ANA-03 | Empty shop | Open Analytics for a shop with no orders. | Friendly empty state, no errors. | | | `test_analytics` AnalyticsPageTests |
| ANA-04 | Privacy | Two shopkeepers compare their Analytics pages. | Each sees only their own figures. | | | `test_analytics` AnalyticsAccessTests |

### 4.14 Security and deployment checks

| ID | Feature | Steps | Expected result | Actual result | Status | Automated coverage |
|---|---|---|---|---|---|---|
| SEC-01 | Secret key required | Start with `APP_ENV=production` and no `SECRET_KEY`. | The app refuses to start with a clear message. | | | `test_security` ConfigurationTests |
| SEC-02 | Debug off in production | Run in production mode, open a broken URL and `/console`. | No error details, no developer console. | | | smoke test; `test_security` FriendlyErrorTests |
| SEC-03 | Dev server refuses production | Run `python run.py` with `APP_ENV=production`. | "Refusing to start the development server". | | | `test_security` ConfigurationTests |
| SEC-04 | Security headers | Open the site and view response headers in the browser's network tab. | Content-Security-Policy, X-Frame-Options, X-Content-Type-Options, Referrer-Policy present. | | | `test_security` SecurityHeaderTests |
| SEC-05 | SQL injection attempts | Search / log in with `' OR '1'='1` and `'; DROP TABLE users; --`. | Treated as plain text; no error, no extra results, tables intact. | | | `test_security` InjectionTests |
| SEC-06 | Open redirect | Log in via `/login?next=/\evil.com` and `?next=https://evil.com`. | You land on your dashboard, never on another site. | | | `test_security` RedirectSafetyTests |
| SEC-07 | Health check | Open `/healthz`. | `{"status": "ok"}`. | | | `test_security` HealthCheckTests |
| SEC-08 | Live smoke test | `python scripts/smoke_test.py https://<your-site>`. | Every check passes (including HSTS and Secure cookie on HTTPS). | | | `scripts/smoke_test.py` |

## 5. Test result summary (to complete)

| Section | Cases | Passed | Failed | Blocked | Tester | Date |
|---|---|---|---|---|---|---|
| 4.1 Registration | 8 | | | | | |
| 4.2 Login and logout | 9 | | | | | |
| 4.3 Role-based access | 10 | | | | | |
| 4.4 Shop creation and approval | 6 | | | | | |
| 4.5 Product management | 10 | | | | | |
| 4.6 Search and browsing | 6 | | | | | |
| 4.7 Cart | 10 | | | | | |
| 4.8 Checkout | 8 | | | | | |
| 4.9 Orders | 10 | | | | | |
| 4.10 Delivery | 9 | | | | | |
| 4.11 Admin | 10 | | | | | |
| 4.12 Invalid input | 8 | | | | | |
| 4.13 Advanced features | 19 | | | | | |
| 4.14 Security and deployment | 8 | | | | | |
| **Total** | **131** | | | | | |

## 6. Automated test suite summary

Last run: **367 tests, all passing** (`python -m unittest discover -s tests -t .`).

| Test module | Tests | Area |
|---|---|---|
| `test_auth` | 16 | Registration, login, logout, roles, CSRF, admin creation |
| `test_registration_limits` | 7 | Email and name validation |
| `test_models` | 4 | Database models and relationships |
| `test_catalog` | 25 | Browsing, visibility, search, filters, product pages |
| `test_shopkeeper` | 37 | Shop profile, product management, seller authorization |
| `test_cart` | 40 | Cart rules, stock limits, one shop per cart, privacy |
| `test_orders` | 42 | Checkout, order creation, workflow rules, cancellation |
| `test_delivery` | 20 | Delivery lifecycle, partner isolation |
| `test_admin` | 32 | Admin access, users, shop approval, categories, assignment |
| `test_location` | 25 | Distance maths, coordinates, nearby shops |
| `test_reviews` | 25 | Reviews and ratings |
| `test_low_stock` | 21 | Low-stock alerts |
| `test_analytics` | 23 | Sales analytics |
| `test_schema_upgrade` | 6 | Automatic database upgrade |
| `test_security` | 44 | Configuration, headers, throttling, injection, error pages |
