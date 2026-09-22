from flask import Blueprint, jsonify, render_template
from sqlalchemy import text

from app.extensions import db

from app.services import catalog_service, review_service

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def home():
    return render_template(
        "home.html",
        categories=catalog_service.categories_with_counts(),
        shops=catalog_service.approved_shops(limit=4),
        counts=catalog_service.visible_product_counts(),
        ratings=review_service.shop_ratings(),
        popular_products=catalog_service.popular_products(limit=8),
        shop_total=len(catalog_service.approved_shops()),
    )


@main_bp.route("/healthz")
def health_check():
    """Used by hosting platforms (and the smoke test) to see that the app and database are up."""
    try:
        db.session.execute(text("SELECT 1"))
    except Exception:
        return jsonify(status="error"), 503
    return jsonify(status="ok")
