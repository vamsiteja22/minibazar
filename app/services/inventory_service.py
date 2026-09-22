"""Low-stock alerts for shopkeepers.

An alert is raised for every AVAILABLE product whose stock is at or below the
threshold (LOW_STOCK_THRESHOLD in config.py). Products the shopkeeper has hidden
are ignored - they are not for sale, so running low does not matter.
"""
from flask import current_app

from app.models.product import Product


def threshold():
    return current_app.config["LOW_STOCK_THRESHOLD"]


def low_stock_query(shop):
    return Product.query.filter(
        Product.shop_id == shop.id,
        Product.is_available.is_(True),
        Product.stock_quantity <= threshold(),
    )


def low_stock_products(shop):
    """{'out': [sold out products], 'low': [running low], 'count': total alerts}."""
    products = low_stock_query(shop).order_by(Product.stock_quantity.asc(), Product.name.asc()).all()
    out = [p for p in products if p.stock_quantity <= 0]
    low = [p for p in products if p.stock_quantity > 0]
    return {"out": out, "low": low, "count": len(products)}


def low_stock_count(shop):
    return low_stock_query(shop).count()
