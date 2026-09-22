"""The order lifecycle: who may change an order's status, and how.

Workflow (arrows show every VALID move; anything else is refused):

    pending ──> confirmed ("Accepted") ──> preparing ──> ready_for_pickup ──> out_for_delivery ──> delivered
       │
       ├──> rejected    (the shopkeeper declines)
       └──> cancelled   (the customer changes their mind, only while still pending)

Who does what:
    shopkeeper        accept, reject, start preparing, mark ready
    customer          cancel (only while pending)
    delivery partner  start delivery and mark delivered (delivery_service does this,
                      so the order and its Delivery record stay in step)

Stock: it is reserved when the order is placed, so a rejected or cancelled order
gives the stock back.
"""
from collections import namedtuple

from sqlalchemy import update

from app.extensions import db
from app.models.order import (
    ORDER_CANCELLED,
    ORDER_CONFIRMED,
    ORDER_DELIVERED,
    ORDER_OUT_FOR_DELIVERY,
    ORDER_PENDING,
    ORDER_PREPARING,
    ORDER_READY,
    ORDER_REJECTED,
    Order,
)
from app.models.product import Product

ACTOR_SHOPKEEPER = "shopkeeper"
ACTOR_CUSTOMER = "customer"
ACTOR_DELIVERY = "delivery_partner"

STATUS_LABELS = {
    ORDER_PENDING: "Pending",
    ORDER_CONFIRMED: "Accepted",
    ORDER_PREPARING: "Preparing",
    ORDER_READY: "Ready for pickup",
    ORDER_OUT_FOR_DELIVERY: "Out for delivery",
    ORDER_DELIVERED: "Delivered",
    ORDER_REJECTED: "Rejected",
    ORDER_CANCELLED: "Cancelled",
}

# The complete map of valid status changes (regardless of who makes them).
WORKFLOW = {
    ORDER_PENDING: {ORDER_CONFIRMED, ORDER_REJECTED, ORDER_CANCELLED},
    ORDER_CONFIRMED: {ORDER_PREPARING},
    ORDER_PREPARING: {ORDER_READY},
    ORDER_READY: {ORDER_OUT_FOR_DELIVERY},      # delivery partner
    ORDER_OUT_FOR_DELIVERY: {ORDER_DELIVERED},  # delivery partner
    ORDER_DELIVERED: set(),
    ORDER_REJECTED: set(),
    ORDER_CANCELLED: set(),
}

# Statuses in which an order is finished (nothing more will happen to it).
FINISHED_STATUSES = (ORDER_DELIVERED, ORDER_REJECTED, ORDER_CANCELLED)
# Statuses that give the reserved stock back.
STOCK_RETURNING_STATUSES = (ORDER_REJECTED, ORDER_CANCELLED)

Action = namedtuple("Action", "actor from_statuses to_status label message")

ACTIONS = {
    "accept": Action(ACTOR_SHOPKEEPER, (ORDER_PENDING,), ORDER_CONFIRMED,
                     "Accept order", "Order accepted."),
    "reject": Action(ACTOR_SHOPKEEPER, (ORDER_PENDING,), ORDER_REJECTED,
                     "Reject order", "Order rejected."),
    "preparing": Action(ACTOR_SHOPKEEPER, (ORDER_CONFIRMED,), ORDER_PREPARING,
                        "Start preparing", "Order is now being prepared."),
    "ready": Action(ACTOR_SHOPKEEPER, (ORDER_PREPARING,), ORDER_READY,
                    "Mark ready for pickup", "Order is ready for pickup."),
    "cancel": Action(ACTOR_CUSTOMER, (ORDER_PENDING,), ORDER_CANCELLED,
                     "Cancel order", "Your order was cancelled."),
    "start_delivery": Action(ACTOR_DELIVERY, (ORDER_READY,), ORDER_OUT_FOR_DELIVERY,
                             "Start delivery", "Delivery started."),
    "deliver": Action(ACTOR_DELIVERY, (ORDER_OUT_FOR_DELIVERY,), ORDER_DELIVERED,
                      "Mark delivered", "Order delivered."),
}

# Tabs on the shopkeeper's orders page: key -> (label, statuses included or None for all)
FILTERS = {
    "all": ("All", None),
    "pending": ("New", (ORDER_PENDING,)),
    "active": ("In progress", (ORDER_CONFIRMED, ORDER_PREPARING, ORDER_READY, ORDER_OUT_FOR_DELIVERY)),
    "completed": ("Completed", (ORDER_DELIVERED,)),
    "closed": ("Rejected / cancelled", (ORDER_REJECTED, ORDER_CANCELLED)),
}

# Progress bar shown on order pages. A status maps to the step it is on now;
# len(PROGRESS_STEPS) means every step is finished. Rejected/cancelled have no bar.
PROGRESS_STEPS = ["Placed", "Accepted", "Preparing", "Ready for pickup", "Out for delivery", "Delivered"]
PROGRESS_INDEX = {
    ORDER_PENDING: 0,
    ORDER_CONFIRMED: 1,
    ORDER_PREPARING: 2,
    ORDER_READY: 3,
    ORDER_OUT_FOR_DELIVERY: 4,
    ORDER_DELIVERED: len(PROGRESS_STEPS),
}


# ---- reading orders ----------------------------------------------------------
def shop_orders(shop, filter_key="all"):
    query = Order.query.filter_by(shop_id=shop.id)
    statuses = FILTERS.get(filter_key, FILTERS["all"])[1]
    if statuses:
        query = query.filter(Order.status.in_(statuses))
    return query.order_by(Order.created_at.desc(), Order.id.desc()).all()


def filter_counts(shop):
    return {key: len(shop_orders(shop, key)) for key in FILTERS}


def get_shop_order_or_none(shop, order_id):
    """Shopkeepers load orders ONLY through this: it must belong to their shop."""
    return Order.query.filter_by(id=order_id, shop_id=shop.id).first()


def customer_orders(customer):
    return (
        Order.query.filter_by(customer_id=customer.id)
        .order_by(Order.created_at.desc(), Order.id.desc())
        .all()
    )


def get_customer_order_or_none(customer, order_id):
    """Customers load orders ONLY through this: it must be one of their own."""
    return Order.query.filter_by(id=order_id, customer_id=customer.id).first()


def subtotal(order):
    """Sum of the item lines (the order total minus the delivery fee)."""
    return sum((item.price_at_purchase * item.quantity for item in order.items), 0)


def delivery_fee(order):
    return order.total_amount - subtotal(order)


# ---- changing status ---------------------------------------------------------
def available_actions(order, actor):
    """Buttons this person may press on this order right now: [(action, label), ...]."""
    return [
        (name, action.label)
        for name, action in ACTIONS.items()
        if action.actor == actor and order.status in action.from_statuses
    ]


def apply_action(order, action_name, actor, commit=True):
    """Move the order to its next status. Raises ValueError with a friendly message if not allowed.

    Pass commit=False when the caller saves other changes in the same step (the
    delivery service does, so an order and its delivery never get out of step).
    """
    action = ACTIONS.get(action_name)
    if action is None or action.actor != actor:
        raise ValueError("Unknown action.")
    if order.status not in action.from_statuses:
        raise ValueError(
            f"This order is '{STATUS_LABELS[order.status]}', so that action is not available."
        )
    assert action.to_status in WORKFLOW[order.status], "ACTIONS must follow WORKFLOW"

    order.status = action.to_status
    if action.to_status in STOCK_RETURNING_STATUSES:
        return_stock(order)
    if commit:
        db.session.commit()
    return action.message


def return_stock(order):
    """Give the reserved stock back (added to the session; the caller commits)."""
    for item in order.items:
        db.session.execute(
            update(Product)
            .where(Product.id == item.product_id)
            .values(stock_quantity=Product.stock_quantity + item.quantity)
        )
