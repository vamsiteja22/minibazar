"""Public browsing pages: shops, products, product details and search.

Customers only ever see approved shops and products the shopkeeper has not hidden
(see catalog_service). Anything else is a 404.
"""
from flask import Blueprint, abort, render_template, request
from flask_login import current_user

from app.services import catalog_service, location_service, review_service

shop_bp = Blueprint("shop", __name__)


def _category_from_request():
    """The chosen Category, or None when there is no filter (or the id doesn't exist)."""
    return catalog_service.get_category(request.args.get("category", type=int))


def _sort_from_request():
    sort = request.args.get("sort", "newest")
    return sort if sort in catalog_service.SORT_OPTIONS else "newest"


@shop_bp.route("/shops")
def shop_list():
    category = _category_from_request()
    shops = catalog_service.approved_shops(category_id=category.id if category else None)

    # "Shops near me": only when a valid position was sent (?lat=..&lng=..&radius=..).
    nearby, distances, location_error, without_location = None, {}, None, 0
    if request.args.get("lat") or request.args.get("lng"):
        try:
            lat, lng = location_service.parse_coordinates(request.args.get("lat"), request.args.get("lng"))
            radius = location_service.parse_radius(request.args.get("radius"))
            rows, without_location = location_service.shops_near(shops, lat, lng, radius)
            shops = [shop for shop, _distance in rows]
            distances = {shop.id: distance for shop, distance in rows}
            nearby = {"lat": lat, "lng": lng, "radius": radius}
        except location_service.LocationError as error:
            location_error = str(error)

    return render_template(
        "shop/shops.html",
        shops=shops,
        counts=catalog_service.visible_product_counts(),
        ratings=review_service.shop_ratings(),
        categories=catalog_service.categories_with_counts(),
        active_category=category,
        nearby=nearby,
        distances=distances,
        without_location=without_location,
        location_error=location_error,
        radius_options=location_service.RADIUS_OPTIONS,
        format_distance=location_service.format_distance,
        typed_lat=request.args.get("lat", ""),
        typed_lng=request.args.get("lng", ""),
    )


@shop_bp.route("/shops/<int:shop_id>")
def shop_detail(shop_id):
    shop = catalog_service.get_approved_shop(shop_id) or abort(404)
    category = _category_from_request()
    sort = _sort_from_request()
    return render_template(
        "shop/shop_detail.html",
        shop=shop,
        products=catalog_service.list_products(
            category_id=category.id if category else None, shop_id=shop.id, sort=sort
        ),
        categories=catalog_service.categories_with_counts(shop_id=shop.id),
        active_category=category,
        total_products=catalog_service.visible_product_counts().get(shop.id, 0),
        rating=review_service.shop_rating(shop),
        sort=sort,
        sort_options=catalog_service.SORT_OPTIONS,
    )


@shop_bp.route("/products")
def product_list():
    category = _category_from_request()
    sort = _sort_from_request()
    return render_template(
        "shop/products.html",
        products=catalog_service.list_products(category_id=category.id if category else None, sort=sort),
        categories=catalog_service.categories_with_counts(),
        active_category=category,
        sort=sort,
        sort_options=catalog_service.SORT_OPTIONS,
    )


@shop_bp.route("/products/<int:product_id>")
def product_detail(product_id):
    product = catalog_service.get_visible_product(product_id) or abort(404)

    # Review form: only a logged-in customer, and only once the product was delivered to them.
    is_customer = current_user.is_authenticated and current_user.role == "customer"
    can_review = is_customer and review_service.has_delivered_purchase(current_user, product)
    return render_template(
        "shop/product_detail.html",
        product=product,
        shop=product.shop,
        related=catalog_service.related_products(product),
        reviews=review_service.reviews_for(product),
        my_review=review_service.get_review(current_user, product) if is_customer else None,
        can_review=can_review,
        is_customer=is_customer,
        max_comment=review_service.MAX_COMMENT,
    )


@shop_bp.route("/search")
def search():
    query = request.args.get("q", "").strip()
    found_shops, found_products = catalog_service.search(query)
    return render_template(
        "shop/search.html",
        query=query,
        shops=found_shops,
        products=found_products,
        counts=catalog_service.visible_product_counts(),
        ratings=review_service.shop_ratings(),
        categories=catalog_service.categories_with_counts(),
    )
