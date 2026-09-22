import math

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user

from app.services import auth_service

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for(auth_service.dashboard_endpoint(current_user)))

    if request.method == "POST":
        name = request.form.get("name", "")
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        role = request.form.get("role", "")

        errors = auth_service.validate_registration(name, email, password, confirm, role)
        if errors:
            for message in errors:
                flash(message, "error")
        else:
            auth_service.create_user(name, email, password, role)
            flash("Account created! Please log in.", "success")
            return redirect(url_for("auth.login"))

    # Allows links like /register?role=shopkeeper to preselect the account type.
    selected_role = request.form.get("role") or request.args.get("role", "customer")
    return render_template(
        "auth/register.html",
        roles=auth_service.PUBLIC_ROLES,
        selected_role=selected_role,
    )


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for(auth_service.dashboard_endpoint(current_user)))

    if request.method == "POST":
        email = request.form.get("email", "")
        password = request.form.get("password", "")
        # Password-guessing protection: too many wrong passwords means a short wait.
        throttle = current_app.extensions["login_throttle"]
        key = throttle.key(request.remote_addr, email)
        wait = throttle.seconds_left(key)
        if wait:
            minutes = math.ceil(wait / 60)
            flash(f"Too many failed attempts. Please try again in {minutes} minute{'s' if minutes != 1 else ''}.", "error")
            return render_template("auth/login.html"), 429

        user = auth_service.authenticate(email, password)

        if user is None:
            throttle.record_failure(key)
            # Same message for "no such email" and "wrong password" on purpose.
            flash("Invalid email or password.", "error")
        elif not user.is_active:
            # Only said AFTER the password was correct, so it can't be used to probe accounts.
            flash("This account has been deactivated. Please contact support.", "error")
        else:
            throttle.clear(key)
            login_user(user)
            flash(f"Welcome back, {user.name}!", "success")
            next_url = request.args.get("next")
            if auth_service.is_safe_redirect(next_url):
                return redirect(next_url)
            return redirect(url_for(auth_service.dashboard_endpoint(user)))

    return render_template("auth/login.html")


@auth_bp.route("/logout", methods=["POST"])
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("main.home"))
