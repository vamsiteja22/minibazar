"""Product reviews and shop ratings.

Rules:
* Only a customer who has RECEIVED the product (an order with it is "delivered") may review it.
* One review per customer per product: posting again edits the old one.
* A customer can delete only their own review.
* A shop's rating is the average of all ratings given to its products.
"""
from sqlalchemy import func

from app.extensions import db
from app.models.order import ORDER_DELIVERED, Order, OrderItem
from app.models.product import Product
from app.models.review import Review

MAX_COMMENT = 500


class ReviewError(ValueError):
    """Something to tell the customer (its text is a friendly message)."""


def has_delivered_purchase(customer, product):
    """True if the customer has a delivered order that contains this product."""
    return (
        db.session.query(Order.id)
        .join(OrderItem, OrderItem.order_id == Order.id)
        .filter(
            Order.customer_id == customer.id,
            Order.status == ORDER_DELIVERED,
            OrderItem.product_id == product.id,
        )
        .first()
        is not None
    )


def get_review(customer, product):
    return Review.query.filter_by(customer_id=customer.id, product_id=product.id).first()


def reviews_for(product, limit=50):
    """Newest reviews first."""
    return (
        Review.query.filter_by(product_id=product.id)
        .order_by(Review.created_at.desc(), Review.id.desc())
        .limit(limit)
        .all()
    )


def parse_rating(text):
    text = (text or "").strip()
    if text not in ("1", "2", "3", "4", "5"):
        raise ReviewError("Please choose a rating from 1 to 5 stars.")
    return int(text)


def save_review(customer, product, rating_text, comment_text):
    """Create the customer's review, or update it if they already wrote one.

    Returns (review, created).
    """
    rating = parse_rating(rating_text)
    comment = " ".join((comment_text or "").split())
    if len(comment) > MAX_COMMENT:
        raise ReviewError(f"Your comment can be at most {MAX_COMMENT} characters.")
    if not has_delivered_purchase(customer, product):
        raise ReviewError("You can review a product after an order containing it has been delivered.")

    review = get_review(customer, product)
    created = review is None
    if created:
        review = Review(customer_id=customer.id, product_id=product.id)
        db.session.add(review)
    review.rating = rating
    review.comment = comment or None
    db.session.commit()
    return review, created


def delete_review(customer, product):
    """Delete the customer's own review. Returns False if they had none."""
    review = get_review(customer, product)
    if review is None:
        return False
    db.session.delete(review)
    db.session.commit()
    return True


# ---- shop ratings --------------------------------------------------------------------
def shop_ratings():
    """{shop_id: (average rating, number of reviews)} for every shop that has reviews."""
    rows = (
        db.session.query(Product.shop_id, func.avg(Review.rating), func.count(Review.id))
        .join(Review, Review.product_id == Product.id)
        .group_by(Product.shop_id)
        .all()
    )
    return {shop_id: (float(average), count) for shop_id, average, count in rows}


def shop_rating(shop):
    """(average, count) for one shop, or None when nobody has reviewed its products yet."""
    return shop_ratings().get(shop.id)
