from functools import wraps

from flask import abort, flash, redirect, url_for
from flask_login import current_user, login_required

from app.models.user import ROLE_SHOPKEEPER


def role_required(*roles):
    """Allow a route only for logged-in users who have one of the given roles.

    Not logged in -> sent to the login page.
    Logged in with the wrong role -> 403 Forbidden page.
    """

    def decorator(view):
        @wraps(view)
        @login_required
        def wrapper(*args, **kwargs):
            if current_user.role not in roles:
                abort(403)
            return view(*args, **kwargs)

        return wrapper

    return decorator


def shop_required(view):
    """Shopkeeper-only route that also needs the shopkeeper to have created a shop.

    Checks, in order: logged in -> is a shopkeeper -> owns a shop.
    """

    @wraps(view)
    def wrapper(*args, **kwargs):
        if current_user.shop is None:
            flash("Please create your shop first.", "error")
            return redirect(url_for("shopkeeper.shop_create"))
        return view(*args, **kwargs)

    return role_required(ROLE_SHOPKEEPER)(wrapper)
