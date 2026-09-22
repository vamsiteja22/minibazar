"""Product rules: validation, categories, image files, and safe deletion."""
import os
import uuid
from decimal import Decimal, InvalidOperation

from flask import current_app

from app.extensions import db
from app.models.cart import CartItem
from app.models.category import Category
from app.models.order import OrderItem
from app.models.product import Product
from app.models.review import Review

MAX_PRICE = Decimal("100000")
MAX_STOCK = 100000

DEFAULT_CATEGORIES = [
    "Fruits & Vegetables",
    "Dairy & Sweets",
    "Bakery",
    "Groceries & Staples",
    "Snacks",
    "Household",
    "Stationery",
]


def ensure_default_categories():
    """Add the default categories if the table is empty (safe to call many times)."""
    if Category.query.count() == 0:
        db.session.add_all(Category(name=name) for name in DEFAULT_CATEGORIES)
        db.session.commit()


def category_choices():
    ensure_default_categories()
    return Category.query.order_by(Category.name).all()


# ---- validation --------------------------------------------------------------
def parse_price(text):
    """Return (price, error). Price must be above 0, max 2 decimals, at most MAX_PRICE."""
    try:
        price = Decimal((text or "").strip())
        if not price.is_finite() or price <= 0 or price > MAX_PRICE:
            raise InvalidOperation
        if price.as_tuple().exponent < -2:
            raise InvalidOperation
        return price, None
    except InvalidOperation:
        return None, "Price must be a number above 0 (up to 2 decimal places, max 1,00,000)."


def parse_stock(text):
    """Return (stock, error). Stock is a whole number from 0 to MAX_STOCK."""
    text = (text or "").strip()
    if text.isdigit() and int(text) <= MAX_STOCK:
        return int(text), None
    return None, f"Stock must be a whole number from 0 to {MAX_STOCK}."


def validate_product_form(form, files):
    """Check the product form. Returns (cleaned_values, image_file, errors)."""
    errors = []
    name = form.get("name", "").strip()
    description = form.get("description", "").strip()

    if not 2 <= len(name) <= 120:
        errors.append("Product name must be between 2 and 120 characters.")
    if len(description) > 1000:
        errors.append("Description can be at most 1000 characters.")

    price, price_error = parse_price(form.get("price"))
    stock, stock_error = parse_stock(form.get("stock_quantity"))
    errors += [e for e in (price_error, stock_error) if e]

    category_id = None
    category_text = form.get("category_id", "").strip()
    if category_text.isdigit() and db.session.get(Category, int(category_text)):
        category_id = int(category_text)
    else:
        errors.append("Please choose a category.")

    image_file = files.get("image")
    if image_file and image_file.filename:
        if detect_image_type(image_file) is None:
            errors.append("Image must be a PNG, JPG, WEBP or GIF file.")
    else:
        image_file = None

    cleaned = {
        "name": name,
        "description": description or None,
        "price": price,
        "stock_quantity": stock,
        "category_id": category_id,
        "is_available": form.get("is_available") == "on",
    }
    return cleaned, image_file, errors


# ---- images ------------------------------------------------------------------
def detect_image_type(file_storage):
    """Look at the file's first bytes (not its name) to find the real image type."""
    head = file_storage.stream.read(16)
    file_storage.stream.seek(0)
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    return None


def save_image(file_storage):
    """Save an already-validated image under a random name and return that name."""
    extension = detect_image_type(file_storage)
    filename = f"{uuid.uuid4().hex}.{extension}"
    folder = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(folder, exist_ok=True)
    file_storage.save(os.path.join(folder, filename))
    return filename


def delete_image(filename):
    if not filename:
        return
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], os.path.basename(filename))
    if os.path.isfile(path):
        os.remove(path)


# ---- create / update / delete -----------------------------------------------
def create_product(shop, cleaned, image_file):
    product = Product(shop_id=shop.id, **cleaned)
    if image_file:
        product.image = save_image(image_file)
    db.session.add(product)
    db.session.commit()
    return product


def update_product(product, cleaned, image_file, remove_image=False):
    for field, value in cleaned.items():
        setattr(product, field, value)
    old_image = product.image
    if image_file:
        product.image = save_image(image_file)
    elif remove_image:
        product.image = None
    db.session.commit()
    if old_image and old_image != product.image:
        delete_image(old_image)
    return product


def get_shop_product_or_none(shop, product_id):
    """The ONLY way routes load a product: it must belong to the given shop."""
    return Product.query.filter_by(id=product_id, shop_id=shop.id).first()


def delete_product(product):
    """Delete a product. Returns True if deleted, False if it was only hidden.

    A product that appears in past orders must stay in the database so order
    history keeps working, so it is marked unavailable instead.
    """
    if OrderItem.query.filter_by(product_id=product.id).first():
        product.is_available = False
        db.session.commit()
        return False

    CartItem.query.filter_by(product_id=product.id).delete()
    Review.query.filter_by(product_id=product.id).delete()
    image = product.image
    db.session.delete(product)
    db.session.commit()
    delete_image(image)
    return True
