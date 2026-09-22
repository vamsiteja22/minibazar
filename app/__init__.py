import logging
import sys

from flask import Flask, render_template
from werkzeug.middleware.proxy_fix import ProxyFix

from app.extensions import csrf, db, login_manager, migrate
from config import get_config


def create_app(config_class=None):
    """Application factory: builds and returns a configured Flask app.

    With no argument the settings come from the APP_ENV environment variable
    (development by default, or production - see config.py).
    """
    config_class = config_class or get_config()
    if hasattr(config_class, "validate"):
        config_class.validate()   # production refuses to start with a weak SECRET_KEY

    app = Flask(__name__)
    app.config.from_object(config_class)

    # Behind the host's web server, trust its "X-Forwarded-*" headers (real visitor address,
    # and whether the visitor used HTTPS).
    proxies = app.config.get("TRUSTED_PROXIES", 0)
    if proxies:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=proxies, x_proto=proxies, x_host=proxies)

    # A live site logs to the console, where the host collects it.
    if not app.debug and not app.testing:
        logging.basicConfig(stream=sys.stdout, level=logging.INFO,
                            format="%(asctime)s %(levelname)s %(name)s: %(message)s")
        app.logger.setLevel(logging.INFO)

    # Connect extensions to this app.
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"  # where anonymous users are sent
    login_manager.login_message = "Please log in to access that page."
    login_manager.login_message_category = "error"

    # Import models so SQLAlchemy knows every table.
    from app import models  # noqa: F401
    from app.models.user import User

    # Bring an older database up to date (adds new columns only; never removes data).
    with app.app_context():
        try:
            from app.schema_upgrade import upgrade_schema

            for column in upgrade_schema(db.engine):
                app.logger.warning("Database upgraded: added column %s", column)
        except Exception:  # never stop the app from starting because of this
            app.logger.exception("Could not check the database schema")

    @login_manager.user_loader
    def load_user(user_id):
        """Flask-Login calls this on each request to get the user from the session.

        A deactivated user is treated as logged out, so deactivation takes effect
        immediately, even for someone who is already signed in.
        """
        user = db.session.get(User, int(user_id))
        return user if user is not None and user.is_active else None

    # Register route groups (blueprints).
    from app.routes.auth import auth_bp
    from app.routes.admin import admin_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.delivery import delivery_bp
    from app.routes.customer import customer_bp
    from app.routes.main import main_bp
    from app.routes.shop import shop_bp
    from app.routes.shopkeeper import shopkeeper_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(shop_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(customer_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(shopkeeper_bp)
    app.register_blueprint(delivery_bp)
    app.register_blueprint(admin_bp)

    @app.template_filter("inr")
    def inr(amount):
        """Format a number as Indian rupees: 1250 -> ₹1,250 and 12.5 -> ₹12.50."""
        if amount != int(amount):
            return f"₹{amount:,.2f}"
        return f"₹{amount:,.0f}"

    @app.template_filter("local_time")
    def local_time(value):
        """Show a stored UTC time in local time, e.g. '19 Sep 2026, 05:40 PM'."""
        from datetime import timedelta

        if value is None:
            return ""
        local = value + timedelta(minutes=app.config["DISPLAY_TZ_OFFSET_MINUTES"])
        return local.strftime("%d %b %Y, %I:%M %p")

    @app.template_filter("delivery_label")
    def delivery_label(status):
        from app.services.delivery_service import DELIVERY_LABELS

        return DELIVERY_LABELS.get(status, status)

    @app.template_filter("status_label")
    def status_label(status):
        from app.services.order_service import STATUS_LABELS

        return STATUS_LABELS.get(status, status)

    @app.context_processor
    def shopkeeper_context():
        """New-order and low-stock numbers, shown as badges on the shopkeeper's tabs."""
        from flask_login import current_user

        if current_user.is_authenticated and current_user.role == "shopkeeper" and current_user.shop:
            from app.models.order import ORDER_PENDING, Order

            from app.services import inventory_service

            count = Order.query.filter_by(shop_id=current_user.shop.id, status=ORDER_PENDING).count()
            return {
                "pending_orders": count,
                "low_stock_count": inventory_service.low_stock_count(current_user.shop),
            }
        return {"pending_orders": 0, "low_stock_count": 0}

    @app.context_processor
    def staff_context():
        """Small "to do" numbers for the admin and delivery-partner tab bars."""
        from flask_login import current_user

        if not current_user.is_authenticated:
            return {}
        if current_user.role == "admin":
            from app.models.shop import Shop
            from app.services import delivery_service

            pending = Shop.query.filter(Shop.is_approved.is_(False), Shop.rejection_reason.is_(None)).count()
            return {"todo_shops": pending, "todo_orders": len(delivery_service.eligible_orders())}
        if current_user.role == "delivery_partner":
            from app.services import delivery_service

            return {"todo_deliveries": delivery_service.partner_counts(current_user)["awaiting"]}
        return {}

    @app.context_processor
    def nav_cart_count():
        """Number of items in the customer's cart, shown on the cart link."""
        from flask_login import current_user

        from app.services import cart_service

        if current_user.is_authenticated and current_user.role == "customer":
            return {"nav_cart_count": cart_service.item_count(current_user)}
        return {"nav_cart_count": None}

    from app.services import presentation

    app.jinja_env.globals.update(
        category_style=presentation.category_style,
        shop_tint=presentation.shop_tint,
    )

    # Security: browser headers, friendly 400/500 pages, and password-guessing protection.
    from app import security

    security.add_security_headers(app)
    security.register_error_pages(app)
    app.extensions["login_throttle"] = security.LoginThrottle(
        max_failures=app.config["MAX_FAILED_LOGINS"],
        lockout_seconds=app.config["LOGIN_LOCKOUT_SECONDS"],
    )

    @app.errorhandler(403)
    def forbidden(error):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(413)
    def too_large(error):
        return render_template("errors/413.html"), 413

    from app.cli import register_commands

    register_commands(app)

    return app
