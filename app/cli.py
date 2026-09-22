import click

from app.extensions import db
from app.models.shop import Shop
from app.models.user import ROLE_ADMIN, User
from app.services import auth_service, demo_service, product_service


def register_commands(app):
    """Terminal commands, run like:  flask --app run <command>"""

    @app.cli.command("init-db")
    def init_db():
        """Create all database tables (quick setup, no migrations)."""
        db.create_all()
        product_service.ensure_default_categories()
        click.echo("Database tables created (default categories added).")

    @app.cli.command("upgrade-db")
    def upgrade_db():
        """Add any new columns to an older database (safe to run repeatedly)."""
        from app.schema_upgrade import upgrade_schema

        added = upgrade_schema(db.engine)
        click.echo("Added: " + ", ".join(added) if added else "Database is already up to date.")

    @app.cli.command("list-shops")
    def list_shops():
        """Show every shop and whether it is approved."""
        shops = Shop.query.order_by(Shop.id).all()
        if not shops:
            click.echo("No shops yet.")
        for shop in shops:
            state = "approved" if shop.is_approved else "waiting for approval"
            click.echo(f"#{shop.id}  {shop.name}  (owner: {shop.owner.email})  - {state}")

    @app.cli.command("approve-shop")
    @click.option("--email", prompt="Shopkeeper email")
    @click.option("--revoke", is_flag=True, help="Hide the shop from customers again.")
    def approve_shop(email, revoke):
        """Approve (or with --revoke, un-approve) a shopkeeper's shop.

        Temporary admin tool: an admin screen for this comes in a later phase.
        """
        user = User.query.filter_by(email=email.strip().lower()).first()
        if user is None or user.shop is None:
            raise click.ClickException("No shopkeeper with a shop found for that email.")
        user.shop.is_approved = not revoke
        db.session.commit()
        action = "hidden from customers" if revoke else "approved - customers can now see it"
        click.echo(f"'{user.shop.name}' is {action}.")

    @app.cli.command("seed-demo-orders")
    @click.option("--email", prompt="Shopkeeper email")
    def seed_demo_orders(email):
        """Add sample orders to a shopkeeper's shop (for local testing only)."""
        if not (app.debug or app.testing):
            # It creates an account with a publicly known password, so never on a live site.
            raise click.ClickException(
                "seed-demo-orders is for local development only. It is disabled when "
                "APP_ENV=production."
            )
        user = User.query.filter_by(email=email.strip().lower()).first()
        if user is None or user.shop is None:
            raise click.ClickException("No shopkeeper with a shop found for that email.")
        try:
            count = demo_service.create_demo_orders(user.shop)
        except ValueError as error:
            raise click.ClickException(str(error))
        click.echo(f"Created {count} demo orders for '{user.shop.name}'.")
        click.echo(
            f"Demo customer login: {demo_service.DEMO_CUSTOMER_EMAIL} / "
            f"{demo_service.DEMO_CUSTOMER_PASSWORD}"
        )

    @app.cli.command("create-admin")
    @click.option("--name", prompt="Admin name")
    @click.option("--email", prompt="Admin email")
    @click.password_option(help="Admin password (asked securely, not shown).")
    def create_admin(name, email, password):
        """Create an admin account. Admins cannot be created from the website."""
        email = email.strip().lower()
        if len(password) < auth_service.MIN_PASSWORD_LENGTH:
            raise click.ClickException(
                f"Password must be at least {auth_service.MIN_PASSWORD_LENGTH} characters."
            )
        if User.query.filter_by(email=email).first():
            raise click.ClickException("A user with this email already exists.")
        auth_service.create_user(name, email, password, ROLE_ADMIN)
        click.echo(f"Admin account created for {email}.")
