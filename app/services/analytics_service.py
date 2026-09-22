"""Sales analytics for a shopkeeper.

"Sales" means goods in DELIVERED orders (item price x quantity; delivery fees are not
the shop's money). Orders are placed on a day in the shop's local time, and each
delivered order is counted on the day it was placed.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from flask import current_app
from sqlalchemy import func

from app.extensions import db
from app.models.category import Category
from app.models.order import (
    ORDER_CANCELLED,
    ORDER_DELIVERED,
    ORDER_REJECTED,
    Order,
    OrderItem,
)
from app.models.product import Product

PERIOD_OPTIONS = (7, 30, 90)   # days offered on the page
DEFAULT_PERIOD = 30
TOP_LIMIT = 5


def parse_period(text):
    try:
        value = int((text or "").strip())
    except ValueError:
        return DEFAULT_PERIOD
    return value if value in PERIOD_OPTIONS else DEFAULT_PERIOD


def _offset():
    return timedelta(minutes=current_app.config["DISPLAY_TZ_OFFSET_MINUTES"])


def _order_goods(order):
    return sum((item.price_at_purchase * item.quantity for item in order.items), 0)


def sales_report(shop, days):
    """Everything the analytics page shows for the last `days` days (including today)."""
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    today = (now_utc + _offset()).date()
    first_day = today - timedelta(days=days - 1)
    # Start of the first local day, expressed in UTC (how orders are stored).
    since_utc = datetime.combine(first_day, datetime.min.time()) - _offset()

    orders_in_period = Order.query.filter(Order.shop_id == shop.id, Order.created_at >= since_utc).all()
    delivered = [o for o in orders_in_period if o.status == ORDER_DELIVERED]

    revenue_by_day = defaultdict(int)
    orders_by_day = defaultdict(int)
    for order in delivered:
        day = (order.created_at + _offset()).date()
        revenue_by_day[day] += _order_goods(order)
        orders_by_day[day] += 1

    series = []
    for n in range(days):
        day = first_day + timedelta(days=n)
        series.append({"day": day, "revenue": revenue_by_day.get(day, 0), "orders": orders_by_day.get(day, 0)})
    biggest = max((point["revenue"] for point in series), default=0)
    for point in series:
        point["percent"] = round(point["revenue"] * 100 / biggest) if biggest else 0

    revenue = sum(revenue_by_day.values())
    units = sum(item.quantity for order in delivered for item in order.items)
    closed = sum(1 for o in orders_in_period if o.status in (ORDER_REJECTED, ORDER_CANCELLED))
    best = max(series, key=lambda point: point["revenue"]) if biggest else None

    return {
        "days": days,
        "first_day": first_day,
        "last_day": today,
        "series": series,
        "revenue": revenue,
        "orders": len(delivered),
        "units": units,
        "average_order": (revenue / len(delivered)) if delivered else 0,
        "orders_placed": len(orders_in_period),
        "closed_orders": closed,
        "closed_percent": round(closed * 100 / len(orders_in_period)) if orders_in_period else 0,
        "best_day": best,
        "top_products": _top_products(shop, since_utc),
        "top_categories": _top_categories(shop, since_utc),
    }


def _delivered_lines(shop, since_utc):
    return (
        db.session.query(OrderItem)
        .join(Order, Order.id == OrderItem.order_id)
        .filter(Order.shop_id == shop.id, Order.status == ORDER_DELIVERED, Order.created_at >= since_utc)
    )


def _top_products(shop, since_utc):
    revenue = func.sum(OrderItem.price_at_purchase * OrderItem.quantity)
    rows = (
        _delivered_lines(shop, since_utc)
        .join(Product, Product.id == OrderItem.product_id)
        .with_entities(Product.name, func.sum(OrderItem.quantity), revenue)
        .group_by(Product.id)
        .order_by(revenue.desc(), Product.name)
        .limit(TOP_LIMIT)
        .all()
    )
    return [{"name": name, "units": int(units), "revenue": rev} for name, units, rev in rows]


def _top_categories(shop, since_utc):
    revenue = func.sum(OrderItem.price_at_purchase * OrderItem.quantity)
    rows = (
        _delivered_lines(shop, since_utc)
        .join(Product, Product.id == OrderItem.product_id)
        .outerjoin(Category, Category.id == Product.category_id)
        .with_entities(func.coalesce(Category.name, "No category"), revenue)
        .group_by(func.coalesce(Category.name, "No category"))
        .order_by(revenue.desc())
        .limit(TOP_LIMIT)
        .all()
    )
    return [{"name": name, "revenue": rev} for name, rev in rows]
