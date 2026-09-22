"""Delivery partner pages.

Authorization: only delivery partners get in (@role_required), and deliveries are
loaded through delivery_service.get_partner_delivery_or_none(), which only finds jobs
assigned to the logged-in partner - any other id is a 404. Partners have no route
that changes products, prices or shop details.
"""
from flask import Blueprint, abort, flash, redirect, render_template, url_for
from flask_login import current_user

from app.decorators import role_required
from app.models.user import ROLE_DELIVERY
from app.services import delivery_service

delivery_bp = Blueprint("delivery", __name__, url_prefix="/delivery")


def _own_delivery_or_404(delivery_id):
    return delivery_service.get_partner_delivery_or_none(current_user, delivery_id) or abort(404)


def dashboard_context():
    return {
        "counts": delivery_service.partner_counts(current_user),
        "deliveries": delivery_service.partner_active_deliveries(current_user),
        "actions_for": delivery_service.available_actions,
    }


@delivery_bp.route("/tasks/<int:delivery_id>")
@role_required(ROLE_DELIVERY)
def task_detail(delivery_id):
    delivery = _own_delivery_or_404(delivery_id)
    return render_template(
        "delivery/task_detail.html",
        delivery=delivery,
        order=delivery.order,
        actions=delivery_service.available_actions(delivery),
        steps=delivery_service.DELIVERY_STEPS,
        step_index=delivery_service.DELIVERY_PROGRESS[delivery.status],
    )


@delivery_bp.route("/tasks/<int:delivery_id>/<action>", methods=["POST"])
@role_required(ROLE_DELIVERY)
def task_action(delivery_id, action):
    delivery = _own_delivery_or_404(delivery_id)
    try:
        flash(delivery_service.advance(delivery, action, current_user), "success")
    except delivery_service.DeliveryError as error:
        flash(str(error), "error")
    return redirect(url_for("delivery.task_detail", delivery_id=delivery.id))


@delivery_bp.route("/history")
@role_required(ROLE_DELIVERY)
def history():
    return render_template(
        "delivery/history.html", deliveries=delivery_service.partner_history(current_user)
    )
