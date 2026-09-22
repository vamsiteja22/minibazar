"""Create the screenshots used in the project report (docs/screenshots/*.png).

    python scripts/capture_screenshots.py

It builds a throw-away demo database in memory (your real database is never touched), walks
through the real pages as each kind of user, saves them as HTML and photographs them with a
headless Edge or Chrome browser (needs one of them installed).
"""
import os
import random
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from flask import g  # noqa: E402

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models.category import Category  # noqa: E402
from app.models.order import Order, OrderItem  # noqa: E402
from app.models.product import Product  # noqa: E402
from app.models.review import Review  # noqa: E402
from app.models.shop import Shop  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import cart_service, product_service  # noqa: E402
from config import DevelopmentConfig  # noqa: E402

OUT = ROOT / "docs" / "screenshots"
PASSWORD = "demo-password-1"


class DemoConfig(DevelopmentConfig):
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    TESTING = True
    DEBUG = False
    WTF_CSRF_ENABLED = False
    UPLOAD_FOLDER = tempfile.mkdtemp(prefix="minibazar_shots_")


def find_browser():
    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for name in ("msedge", "google-chrome", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    return next((c for c in candidates if os.path.exists(c)), None)


def build_demo(app):
    """Fill the database with a believable little marketplace. Returns the clients and ids."""
    random.seed(7)
    db.create_all()
    product_service.ensure_default_categories()
    cat = {c.name: c for c in Category.query.all()}

    def make_user(email, role, name):
        user = User(name=name, email=email, role=role)
        user.set_password(PASSWORD)
        db.session.add(user)
        db.session.commit()
        return user

    def login(email):
        client = app.test_client()
        client.post("/login", data={"email": email, "password": PASSWORD})
        return client

    customers = [make_user("cathy@demo.in", "customer", "Cathy Customer"),
                 make_user("arjun@demo.in", "customer", "Arjun Rao"),
                 make_user("meera@demo.in", "customer", "Meera Iyer")]
    make_user("admin@demo.in", "admin", "Ada Admin")
    ravi = make_user("ravi@demo.in", "delivery_partner", "Ravi Rider")
    make_user("dev@demo.in", "delivery_partner", "Dev Dasher")

    shop_rows = [
        ("greens@demo.in", "Fresh Basket Greens", "12, Market Road, Gandhi Nagar", 17.3860, 78.4867, "approved",
         "Farm-fresh vegetables and fruits every morning."),
        ("bakery@demo.in", "Golden Crust Bakery", "21, Station Road, Lakshmi Colony", 17.4120, 78.4867, "approved",
         "Breads, buns and cakes baked in small batches."),
        ("dairy@demo.in", "Sharma Dairy & Sweets", "4, Temple Street, Gandhi Nagar", 17.3900, 78.4700, "approved",
         "Fresh milk, paneer and homemade sweets."),
        ("kirana@demo.in", "Anand Kirana Store", "8, Bazaar Lane, Lakshmi Colony", 17.4930, 78.4867, "approved",
         "Rice, dals, oils and everyday groceries."),
        ("corner@demo.in", "Corner Store", "5, Lane 3, University Area", None, None, "pending",
         "A new shop waiting for approval."),
        ("quick@demo.in", "Quick Mart", "9, Ring Road", None, None, "rejected", "Convenience store."),
    ]
    shops = {}
    for email, name, address, lat, lng, state, description in shop_rows:
        owner = make_user(email, "shopkeeper", name.split()[0] + " Owner")
        shop = Shop(owner=owner, name=name, address=address, latitude=lat, longitude=lng, phone="9876543210",
                    description=description, is_approved=state == "approved",
                    rejection_reason="Address looks incomplete. Please add a landmark." if state == "rejected" else None)
        db.session.add(shop)
        db.session.commit()
        shops[name] = shop

    def add_product(shop_name, name, price, stock, category, description):
        product = Product(shop_id=shops[shop_name].id, category_id=cat[category].id, name=name,
                          price=Decimal(price), stock_quantity=stock, description=description)
        db.session.add(product)
        db.session.commit()
        return product

    fb, gc, sd, ak = "Fresh Basket Greens", "Golden Crust Bakery", "Sharma Dairy & Sweets", "Anand Kirana Store"
    tomato = add_product(fb, "Country Tomatoes", "28", 4, "Fruits & Vegetables", "Juicy, firm tomatoes picked this morning.")
    banana = add_product(fb, "Robusta Bananas", "52.50", 38, "Fruits & Vegetables", "Sweet, soft and energy-packed.")
    onion = add_product(fb, "Onions", "34", 0, "Fruits & Vegetables", "Everyday red onions.")
    spinach = add_product(fb, "Fresh Spinach", "20", 2, "Fruits & Vegetables", "Tender leaves, washed and ready to cook.")
    add_product(fb, "Shimla Apples", "180", 25, "Fruits & Vegetables", "Crisp, sweet apples from the hills.")
    bread = add_product(gc, "Whole Wheat Bread", "45", 30, "Bakery", "Soft sandwich bread, 100% whole wheat.")
    add_product(gc, "Butter Croissant", "70", 20, "Bakery", "Flaky, buttery croissants baked this morning.")
    add_product(gc, "Chocolate Muffin", "55", 24, "Bakery", "Rich chocolate muffin with a gooey centre.")
    add_product(sd, "Full Cream Milk", "68", 80, "Dairy & Sweets", "Fresh full cream milk, delivered chilled.")
    add_product(sd, "Fresh Paneer", "90", 18, "Dairy & Sweets", "Soft, made-today paneer.")
    add_product(ak, "Basmati Rice", "110", 50, "Groceries & Staples", "Long-grain aged basmati.")
    add_product(ak, "Masala Chips", "40", 70, "Snacks", "Crunchy potato chips with a tangy kick.")

    # A month of past orders for the first shop (feeds the analytics and dashboard).
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for days_ago in range(40, -1, -1):
        for _ in range(random.choice([0, 1, 1, 2, 3])):
            product = random.choice([tomato, banana, onion, spinach])
            quantity = random.randint(1, 4)
            order = Order(customer_id=random.choice(customers).id, shop_id=shops[fb].id, delivery_address="Home, Town",
                          status=random.choice(["delivered"] * 8 + ["rejected", "cancelled"]),
                          created_at=now - timedelta(days=days_ago, hours=random.randint(0, 10)), total_amount=0)
            order.items.append(OrderItem(product_id=product.id, quantity=quantity, price_at_purchase=product.price))
            order.total_amount = product.price * quantity + 25
            db.session.add(order)
    db.session.commit()
    for i, (product, rating, comment) in enumerate([
            (banana, 5, "Sweet and fresh - arrived in 20 minutes!"), (banana, 4, "Good quality, fair price."),
            (tomato, 4, "Nice and firm tomatoes."), (spinach, 5, "Very fresh leaves."), (banana, 5, None)]):
        customer = customers[i % 3]
        if not Review.query.filter_by(customer_id=customer.id, product_id=product.id).first():
            db.session.add(Review(customer_id=customer.id, product_id=product.id, rating=rating, comment=comment))
    db.session.commit()

    return {
        "customer": login("cathy@demo.in"), "greens": login("greens@demo.in"), "bakery": login("bakery@demo.in"),
        "admin": login("admin@demo.in"), "rider": login("ravi@demo.in"), "visitor": app.test_client(),
        "ravi_id": ravi.id, "banana": banana, "tomato": tomato, "bread": bread, "shops": shops,
    }


def main():
    browser = find_browser()
    if not browser:
        raise SystemExit("No Edge/Chrome browser found - install one to create screenshots.")
    OUT.mkdir(parents=True, exist_ok=True)
    html_dir = Path(tempfile.mkdtemp(prefix="minibazar_html_"))
    css_url = (ROOT / "app" / "static").as_uri() + "/"

    app = create_app(DemoConfig)

    @app.before_request
    def forget_cached_user():
        g.pop("_login_user", None)  # every request behaves like a fresh page load

    pages = []   # (file name, window size)

    with app.app_context():
        world = build_demo(app)
        c, greens, bakery, admin, rider, visitor = (world[k] for k in
                                                    ("customer", "greens", "bakery", "admin", "rider", "visitor"))

        def save(name, client, path, size, method="get", data=None):
            response = getattr(client, method)(path, data=data) if data is not None else getattr(client, method)(path)
            html = response.get_data(as_text=True).replace('href="/static/', f'href="{css_url}')
            html = html.replace('src="/static/', f'src="{css_url}')
            (html_dir / f"{name}.html").write_text(html, encoding="utf-8")
            pages.append((name, size))
            return response

        def place_order(items):
            for product, quantity in items:
                c.post("/cart/add", data={"product_id": product.id, "quantity": quantity})
            total = cart_service.summary(User.query.filter_by(email="cathy@demo.in").one())["total"]
            return c.post("/checkout", data=dict(
                full_name="Cathy Customer", phone="9876543210", address="12, Rose Villa, Gandhi Nagar, near the park",
                notes="Ring the bell twice", payment="cod", expected_total=str(total)))

        save("01_home", visitor, "/", "1280,2100")
        save("02_login", visitor, "/login", "1280,700")
        save("03_register", visitor, "/register?role=shopkeeper", "1280,900")
        save("04_shops_nearby", visitor, "/shops?lat=17.385&lng=78.4867&radius=10", "1280,1050")
        save("05_product_reviews", c, f"/products/{world['banana'].id}", "1280,1650")
        save("06_search", visitor, "/search?q=bread", "1280,1000")

        # Customer journey
        for product, quantity in ((world["tomato"], 2), (world["banana"], 1)):
            c.post("/cart/add", data={"product_id": product.id, "quantity": quantity})
        save("07_cart", c, "/cart", "1280,900")
        save("08_checkout", c, "/checkout", "1280,1250")
        response = place_order([])   # the cart already holds the two items
        order_id = int(response.location.split("/orders/")[1].split("/")[0])
        save("09_order_confirmation", c, f"/orders/{order_id}/confirmation", "1280,1300")

        # A second order at the bakery, taken to "Ready for pickup"
        second = place_order([(world["bread"], 2)])
        second_id = int(second.location.split("/orders/")[1].split("/")[0])
        for action in ("accept", "preparing", "ready"):
            bakery.post(f"/shopkeeper/orders/{second_id}/{action}")
        save("10_customer_orders", c, "/orders", "1280,1000")
        save("11_customer_dashboard", c, "/dashboard/customer", "1280,1100")

        # Shopkeeper
        save("12_shopkeeper_dashboard", greens, "/dashboard/shopkeeper", "1280,1250")
        save("13_shopkeeper_products", greens, "/shopkeeper/products", "1280,1250")
        save("14_shopkeeper_order", greens, f"/shopkeeper/orders/{order_id}", "1280,950")
        save("15_shopkeeper_analytics", greens, "/shopkeeper/analytics?days=30", "1280,1400")
        save("16_shop_location_form", greens, "/shopkeeper/shop/edit", "1280,1200")

        # Admin (the bakery order is ready and waiting for a delivery partner)
        save("17_admin_dashboard", admin, "/dashboard/admin", "1280,1350")
        save("18_admin_shops", admin, "/admin/shops?state=all", "1280,1300")
        save("19_admin_users", admin, "/admin/users", "1280,1100")
        save("20_admin_order_assign", admin, f"/admin/orders/{second_id}", "1280,1000")
        admin.post(f"/admin/orders/{second_id}/assign", data={"partner_id": world["ravi_id"]})

        # Delivery partner
        save("21_delivery_dashboard", rider, "/dashboard/delivery", "1280,900")
        rider.post("/delivery/tasks/1/accept")
        save("22_delivery_task", rider, "/delivery/tasks/1", "1280,1000")

        # Phone-sized views (headless browsers cannot go much narrower than 500 px)
        save("23_mobile_home", visitor, "/", "500,1900")
        save("24_mobile_shops", visitor, "/shops", "500,1500")

    print(f"Photographing {len(pages)} pages with {os.path.basename(browser)} ...")
    for name, size in pages:
        target = OUT / f"{name}.png"
        if target.exists():
            target.unlink()
        subprocess.run([browser, "--headless", "--disable-gpu", "--hide-scrollbars", "--allow-file-access-from-files",
                        f"--window-size={size}", f"--screenshot={target}", (html_dir / f"{name}.html").as_uri()],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        print(f"  {'ok ' if target.exists() else 'MISSING'}  {target.name}")
    shutil.rmtree(html_dir, ignore_errors=True)
    shutil.rmtree(DemoConfig.UPLOAD_FOLDER, ignore_errors=True)


if __name__ == "__main__":
    main()
