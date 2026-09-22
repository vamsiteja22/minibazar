"""What customers can see: approved shops and their available products.

Visibility rule used everywhere in this file:
    a product is visible  =  its shop is approved  AND  the shopkeeper has not hidden it.
(Out-of-stock products stay visible, marked "Out of stock".)
"""
from sqlalchemy import func, or_

from app.extensions import db
from app.models.category import Category
from app.models.order import OrderItem
from app.models.product import Product
from app.models.shop import Shop

SORT_OPTIONS = {
    "newest": "Newest first",
    "price_low": "Price: low to high",
    "price_high": "Price: high to low",
}


def _contains(column, text):
    """Case-insensitive 'column contains text' where % and _ in text are plain characters."""
    safe = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return column.ilike(f"%{safe}%", escape="\\")


def visible_products_query():
    return (
        Product.query.join(Shop, Product.shop_id == Shop.id)
        .filter(Shop.is_approved.is_(True), Product.is_available.is_(True))
    )


# ---- products ----------------------------------------------------------------
def list_products(category_id=None, shop_id=None, sort="newest", limit=None):
    query = visible_products_query()
    if category_id:
        query = query.filter(Product.category_id == category_id)
    if shop_id:
        query = query.filter(Product.shop_id == shop_id)

    if sort == "price_low":
        query = query.order_by(Product.price.asc(), Product.id.asc())
    elif sort == "price_high":
        query = query.order_by(Product.price.desc(), Product.id.asc())
    else:
        query = query.order_by(Product.created_at.desc(), Product.id.desc())
    return query.limit(limit).all() if limit else query.all()


def get_visible_product(product_id):
    return visible_products_query().filter(Product.id == product_id).first()


def popular_products(limit=8):
    """Best-selling products first; products nobody bought yet are ordered newest first."""
    sold = (
        db.session.query(OrderItem.product_id, func.sum(OrderItem.quantity).label("sold"))
        .group_by(OrderItem.product_id)
        .subquery()
    )
    return (
        visible_products_query()
        .outerjoin(sold, sold.c.product_id == Product.id)
        .order_by(func.coalesce(sold.c.sold, 0).desc(), Product.created_at.desc(), Product.id.desc())
        .limit(limit)
        .all()
    )


def related_products(product, limit=4):
    same = (
        visible_products_query()
        .filter(Product.id != product.id, Product.category_id == product.category_id)
        .order_by(Product.created_at.desc())
        .limit(limit)
        .all()
    )
    if same or product.category_id is None:
        return same
    return []


# ---- shops -------------------------------------------------------------------
def approved_shops(category_id=None, limit=None):
    query = Shop.query.filter(Shop.is_approved.is_(True))
    if category_id:
        # only shops that sell something visible in this category
        query = query.filter(
            Shop.id.in_(
                db.session.query(Product.shop_id).filter(
                    Product.category_id == category_id, Product.is_available.is_(True)
                )
            )
        )
    query = query.order_by(Shop.created_at.desc(), Shop.id.desc())
    return query.limit(limit).all() if limit else query.all()


def get_approved_shop(shop_id):
    return Shop.query.filter_by(id=shop_id, is_approved=True).first()


def visible_product_counts():
    """{shop_id: number of visible products} for all approved shops."""
    rows = (
        db.session.query(Product.shop_id, func.count(Product.id))
        .join(Shop, Product.shop_id == Shop.id)
        .filter(Shop.is_approved.is_(True), Product.is_available.is_(True))
        .group_by(Product.shop_id)
        .all()
    )
    return dict(rows)


# ---- categories --------------------------------------------------------------
def categories_with_counts(shop_id=None):
    """[(Category, visible product count)] - only categories that have products."""
    query = (
        db.session.query(Category, func.count(Product.id))
        .join(Product, Product.category_id == Category.id)
        .join(Shop, Product.shop_id == Shop.id)
        .filter(Shop.is_approved.is_(True), Product.is_available.is_(True))
    )
    if shop_id:
        query = query.filter(Product.shop_id == shop_id)
    return query.group_by(Category.id).order_by(Category.name).all()


def get_category(category_id):
    return db.session.get(Category, category_id) if category_id else None


# ---- search ------------------------------------------------------------------
def search(text):
    """Return (shops, products) whose name/description/category matches the text."""
    text = (text or "").strip()
    if not text:
        return [], []

    shops = (
        Shop.query.filter(
            Shop.is_approved.is_(True),
            or_(_contains(Shop.name, text), _contains(Shop.description, text),
                _contains(Shop.address, text)),
        )
        .order_by(Shop.name)
        .all()
    )
    products = (
        visible_products_query()
        .outerjoin(Category, Product.category_id == Category.id)
        .filter(
            or_(_contains(Product.name, text), _contains(Product.description, text),
                _contains(Category.name, text), _contains(Shop.name, text))
        )
        .order_by(Product.name)
        .all()
    )
    return shops, products
