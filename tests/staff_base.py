"""Shared setup for the delivery and admin tests: a customer's order that is ready for pickup."""
from app.extensions import db
from app.models.delivery import Delivery
from tests.test_orders import OrderTestCase


class StaffTestCase(OrderTestCase):
    """Cart of Cathy (customer) -> order at Shop A. Plus an admin and a delivery partner."""

    def setUp(self):
        super().setUp()
        self.admin = self.login_client("admin@example.com", "admin", "Ada Admin")
        self.partner = self.make_user("rider@example.com", "delivery_partner", "Ravi Rider")
        self.rider = self.login_client("rider@example.com", "delivery_partner")
        self.seller_a = self.seller_client(self.shop_a)

    def ready_order(self):
        """Place an order and let the shopkeeper take it all the way to 'Ready for pickup'."""
        order = self.place()
        for action in ("accept", "preparing", "ready"):
            self.order_for(self.seller_a, order, action)
        self.assertEqual(self.all_orders()[-1].status, "ready_for_pickup")
        return self.all_orders()[-1]

    def assign(self, order, partner=None, client=None):
        partner = partner or self.partner
        return (client or self.admin).post(
            f"/admin/orders/{order.id}/assign", data={"partner_id": partner.id}, follow_redirects=True
        )

    def delivery(self):
        db.session.expire_all()
        return Delivery.query.order_by(Delivery.id.desc()).first()

    def step(self, delivery, action, client=None):
        return (client or self.rider).post(f"/delivery/tasks/{delivery.id}/{action}", follow_redirects=True)

    def order_now(self, order):
        db.session.expire_all()
        return db.session.get(type(order), order.id)

    def new_partner(self, email, name, role="delivery_partner"):
        user = self.make_user(email, role, name)
        return user, self.login_client(email, role)
