"""Delivery: assigning partners (admin) and moving a delivery along (partner).

Flow:
    order "Ready for pickup"
        -> admin assigns a partner          Delivery(status="assigned")
        -> partner accepts                  "accepted"
        -> partner picks it up at the shop  "picked_up"
        -> partner sets off                 "out_for_delivery"   (order -> Out for delivery)
        -> partner hands it over            "delivered"          (order -> Delivered, cash marked paid)

An order has at most one Delivery (Delivery.order_id is unique). Only orders that are
ready for pickup can be assigned, and a partner may hold only a few active jobs at once.
The admin can swap the partner only until the partner has accepted.
"""
from collections import namedtuple
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.delivery import (
    DELIVERY_ACCEPTED,
    DELIVERY_ASSIGNED,
    DELIVERY_DELIVERED,
    DELIVERY_OUT,
    DELIVERY_PICKED_UP,
    Delivery,
)
from app.models.order import ORDER_READY, PAYMENT_PAID, Order
from app.models.user import ROLE_DELIVERY, User
from app.services import order_service

MAX_ACTIVE_DELIVERIES = 5

ACTIVE_STATUSES = (DELIVERY_ASSIGNED, DELIVERY_ACCEPTED, DELIVERY_PICKED_UP, DELIVERY_OUT)

DELIVERY_LABELS = {
    DELIVERY_ASSIGNED: "Assigned",
    DELIVERY_ACCEPTED: "Accepted",
    DELIVERY_PICKED_UP: "Picked up",
    DELIVERY_OUT: "Out for delivery",
    DELIVERY_DELIVERED: "Delivered",
}

# Progress bar for a delivery (len(DELIVERY_STEPS) means every step is finished).
DELIVERY_STEPS = ["Assigned", "Accepted", "Picked up", "Out for delivery", "Delivered"]
DELIVERY_PROGRESS = {
    DELIVERY_ASSIGNED: 0,
    DELIVERY_ACCEPTED: 1,
    DELIVERY_PICKED_UP: 2,
    DELIVERY_OUT: 3,
    DELIVERY_DELIVERED: len(DELIVERY_STEPS),
}

DeliveryAction = namedtuple("DeliveryAction", "from_status to_status order_action label message confirm")

# action name -> what it does. `order_action` is the matching order step (or None).
ACTIONS = {
    "accept": DeliveryAction(DELIVERY_ASSIGNED, DELIVERY_ACCEPTED, None,
                             "Accept delivery", "Delivery accepted.", None),
    "pickup": DeliveryAction(DELIVERY_ACCEPTED, DELIVERY_PICKED_UP, None,
                             "Mark picked up", "Marked as picked up from the shop.", None),
    "out": DeliveryAction(DELIVERY_PICKED_UP, DELIVERY_OUT, "start_delivery",
                          "Start delivery", "You are out for delivery.", None),
    "deliver": DeliveryAction(DELIVERY_OUT, DELIVERY_DELIVERED, "deliver",
                              "Mark delivered", "Delivered - thank you!",
                              "Confirm the order was handed over to the customer?"),
}


class DeliveryError(ValueError):
    """A problem to show to the person (its text is a friendly message)."""


# ---- reading -------------------------------------------------------------------
def eligible_orders():
    """Orders waiting for a delivery partner: ready for pickup and not yet assigned."""
    return (
        Order.query.outerjoin(Delivery, Delivery.order_id == Order.id)
        .filter(Order.status == ORDER_READY, Delivery.id.is_(None))
        .order_by(Order.created_at.asc(), Order.id.asc())
        .all()
    )


def active_count(partner_id):
    return Delivery.query.filter(
        Delivery.delivery_partner_id == partner_id, Delivery.status.in_(ACTIVE_STATUSES)
    ).count()


def available_partners():
    """[(partner, active delivery count)] for active partners, least busy first."""
    partners = User.query.filter_by(role=ROLE_DELIVERY, is_active=True).all()
    rows = [(partner, active_count(partner.id)) for partner in partners]
    return sorted(rows, key=lambda row: (row[1], row[0].name.lower()))


def partner_active_deliveries(partner):
    return (
        Delivery.query.filter(Delivery.delivery_partner_id == partner.id,
                              Delivery.status.in_(ACTIVE_STATUSES))
        .order_by(Delivery.assigned_at.desc(), Delivery.id.desc())
        .all()
    )


def partner_history(partner):
    return (
        Delivery.query.filter_by(delivery_partner_id=partner.id, status=DELIVERY_DELIVERED)
        .order_by(Delivery.delivered_at.desc(), Delivery.id.desc())
        .all()
    )


def partner_counts(partner):
    def count(*statuses):
        return Delivery.query.filter(
            Delivery.delivery_partner_id == partner.id, Delivery.status.in_(statuses)
        ).count()

    return {
        "awaiting": count(DELIVERY_ASSIGNED),
        "in_progress": count(DELIVERY_ACCEPTED, DELIVERY_PICKED_UP, DELIVERY_OUT),
        "delivered": count(DELIVERY_DELIVERED),
    }


def get_partner_delivery_or_none(partner, delivery_id):
    """Partners load deliveries ONLY through this: it must be assigned to them."""
    return Delivery.query.filter_by(id=delivery_id, delivery_partner_id=partner.id).first()


def available_actions(delivery):
    """The button a partner may press now: [(action, label, confirm text or None)]."""
    return [
        (name, action.label, action.confirm)
        for name, action in ACTIONS.items()
        if action.from_status == delivery.status
    ]


# ---- assigning (admin) ----------------------------------------------------------
def _check_partner(partner):
    if partner is None or partner.role != ROLE_DELIVERY:
        raise DeliveryError("Please choose a delivery partner.")
    if not partner.is_active:
        raise DeliveryError(f"{partner.name}'s account is deactivated.")
    if active_count(partner.id) >= MAX_ACTIVE_DELIVERIES:
        raise DeliveryError(
            f"{partner.name} already has {MAX_ACTIVE_DELIVERIES} active deliveries. Choose someone else."
        )


def assign(order, partner):
    """Give a ready order to a delivery partner. Returns the new Delivery."""
    if order.status != ORDER_READY:
        raise DeliveryError("Only orders that are 'Ready for pickup' can be assigned.")
    if order.delivery is not None:
        raise DeliveryError("This order already has a delivery partner.")
    _check_partner(partner)

    delivery = Delivery(order_id=order.id, delivery_partner_id=partner.id, status=DELIVERY_ASSIGNED)
    db.session.add(delivery)
    try:
        db.session.commit()
    except IntegrityError:  # another admin assigned it a moment ago
        db.session.rollback()
        raise DeliveryError("This order was just assigned by someone else.")
    return delivery


def reassign(delivery, partner):
    """Swap the partner - allowed only until they have accepted the job."""
    if delivery.status != DELIVERY_ASSIGNED:
        raise DeliveryError("The partner already accepted this delivery, so it can no longer be changed.")
    if delivery.delivery_partner_id == partner.id:
        raise DeliveryError("That partner is already assigned.")
    _check_partner(partner)
    delivery.delivery_partner_id = partner.id
    delivery.assigned_at = datetime.now(timezone.utc)
    db.session.commit()
    return delivery


# ---- moving a delivery along (partner) ------------------------------------------
def advance(delivery, action_name, partner):
    """Do the next step of a delivery. Raises DeliveryError if it isn't allowed.

    The delivery and its order are saved together in ONE commit, so they can
    never disagree.
    """
    if delivery.delivery_partner_id != partner.id:
        raise DeliveryError("This delivery is not assigned to you.")
    action = ACTIONS.get(action_name)
    if action is None:
        raise DeliveryError("Unknown action.")
    if delivery.status != action.from_status:
        raise DeliveryError(
            f"This delivery is '{DELIVERY_LABELS[delivery.status]}', so that step is not available."
        )

    order = delivery.order
    try:
        if action.order_action:
            order_service.apply_action(order, action.order_action, order_service.ACTOR_DELIVERY,
                                       commit=False)
        delivery.status = action.to_status
        if action.to_status == DELIVERY_DELIVERED:
            delivery.delivered_at = datetime.now(timezone.utc)
            order.payment_status = PAYMENT_PAID  # cash on delivery: collected at the door
        db.session.commit()
    except ValueError as error:
        db.session.rollback()
        raise DeliveryError(str(error))
    return action.message
