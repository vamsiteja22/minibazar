"""The delivery partner side, and the whole customer -> shop -> admin -> partner journey."""
import unittest
from decimal import Decimal

from app.extensions import db
from app.models.delivery import Delivery
from app.services import delivery_service, order_service
from tests.staff_base import StaffTestCase
from tests.test_auth import CsrfEnabledConfig


class FullJourneyTests(StaffTestCase):
    def test_every_role_plays_its_part(self):
        # 1. customer orders, shopkeeper prepares it
        order = self.ready_order()
        self.assertIsNone(order.delivery)

        # 2. admin sees it needs a partner, and assigns one
        self.assertIn("Needs a delivery partner", self.page(self.admin, "/admin/orders?status=needs_partner"))
        self.assertIn(f"#{order.id}", self.page(self.admin, "/admin/orders?status=needs_partner"))
        self.assertIn("is assigned to Ravi Rider", self.assign(order).get_data(as_text=True))
        delivery = self.delivery()
        self.assertEqual((delivery.status, delivery.delivery_partner_id), ("assigned", self.partner.id))
        self.assertEqual(self.order_now(order).status, "ready_for_pickup")   # order itself is unchanged
        self.assertNotIn(f"#{order.id}", self.page(self.admin, "/admin/orders?status=needs_partner"))

        # 3. partner accepts, picks up, sets off, delivers
        self.assertIn("Delivery accepted", self.step(delivery, "accept").get_data(as_text=True))
        self.assertEqual(self.delivery().status, "accepted")
        self.assertEqual(self.order_now(order).status, "ready_for_pickup")

        self.step(delivery, "pickup")
        self.assertEqual(self.delivery().status, "picked_up")
        self.assertEqual(self.order_now(order).status, "ready_for_pickup")

        self.step(delivery, "out")
        self.assertEqual(self.delivery().status, "out_for_delivery")
        self.assertEqual(self.order_now(order).status, "out_for_delivery")
        self.assertIn("Out for delivery", self.page(self.customer, f"/orders/{order.id}"))
        self.assertEqual(self.order_now(order).payment_status, "pending")   # cash not collected yet

        self.step(delivery, "deliver")
        delivery = self.delivery()
        order = self.order_now(order)
        self.assertEqual(delivery.status, "delivered")
        self.assertIsNotNone(delivery.delivered_at)
        self.assertEqual((order.status, order.payment_status), ("delivered", "paid"))

        # 4. everyone sees the result
        page = self.page(self.customer, f"/orders/{order.id}")
        self.assertIn("Delivered", page)
        self.assertIn("Ravi Rider", page)
        self.assertIn("Ravi Rider", self.page(self.seller_a, f"/shopkeeper/orders/{order.id}"))
        self.assertIn("Delivered", self.page(self.admin, f"/admin/orders/{order.id}"))
        self.assertIn("Delivered so far", self.page(self.rider, "/dashboard/delivery"))
        self.assertEqual(delivery_service.partner_counts(self.partner)["delivered"], 1)
        self.assertEqual(order_service.available_actions(order, "shopkeeper"), [])


class PartnerTaskViewTests(StaffTestCase):
    def setUp(self):
        super().setUp()
        self.order = self.ready_order()
        self.assign(self.order)
        self.task = self.delivery()

    def test_partner_sees_what_is_needed_for_the_job(self):
        page = self.page(self.rider, f"/delivery/tasks/{self.task.id}")
        for text in ("Shop A", "12 Market Road, Town", "Cathy Customer · 9876543210",
                     "12 Market Road, Gandhi Nagar", "Apple", "Pear", "× 2", "₹65.50",
                     "collect this amount", "Accept delivery"):
            self.assertIn(text, page)

    def test_dashboard_lists_the_task_with_its_next_step(self):
        page = self.page(self.rider, "/dashboard/delivery")
        for text in ("Waiting for you to accept", f"Delivery #{self.task.id}", "Shop A",
                     "Accept delivery", "₹65.50"):
            self.assertIn(text, page)
        self.assertIn('cart-badge">1<', page)  # one job waiting for acceptance

    def test_only_the_next_step_is_offered_and_steps_cannot_be_skipped(self):
        for action in ("pickup", "out", "deliver", "nonsense"):
            page = self.step(self.task, action).get_data(as_text=True)
            self.assertTrue("not available" in page or "Unknown action" in page, action)
        self.assertEqual(self.delivery().status, "assigned")
        self.step(self.task, "accept")
        page = self.step(self.task, "accept").get_data(as_text=True)   # double click
        self.assertIn("not available", page)
        self.assertEqual(self.delivery().status, "accepted")
        self.assertEqual(self.order_now(self.order).status, "ready_for_pickup")

    def test_delivered_is_final_and_cash_shows_as_paid(self):
        for action in ("accept", "pickup", "out", "deliver"):
            self.step(self.task, action)
        for action in ("accept", "pickup", "out", "deliver"):
            self.assertIn("not available", self.step(self.task, action).get_data(as_text=True))
        page = self.page(self.rider, f"/delivery/tasks/{self.task.id}")
        self.assertIn("Nothing to collect", page)
        self.assertNotIn("Mark delivered", page)

    def test_order_and_delivery_never_disagree_when_a_step_fails(self):
        for action in ("accept", "pickup"):
            self.step(self.task, action)
        broken = self.order_now(self.order)
        broken.status = "cancelled"          # something else changed the order meanwhile
        db.session.commit()
        page = self.step(self.task, "out").get_data(as_text=True)
        self.assertIn("not available", page)
        self.assertEqual(self.delivery().status, "picked_up")   # nothing half-saved

    def test_actions_need_post(self):
        self.assertEqual(self.rider.get(f"/delivery/tasks/{self.task.id}/accept").status_code, 405)


class PartnerIsolationTests(StaffTestCase):
    def setUp(self):
        super().setUp()
        self.order = self.ready_order()
        self.assign(self.order)
        self.task = self.delivery()
        self.other_partner, self.other = self.new_partner("dev@example.com", "Dev Dasher")

    def test_other_partners_cannot_see_or_change_the_job(self):
        self.assertEqual(self.other.get(f"/delivery/tasks/{self.task.id}").status_code, 404)
        for action in ("accept", "pickup", "out", "deliver"):
            self.assertEqual(self.other.post(f"/delivery/tasks/{self.task.id}/{action}").status_code, 404)
        self.assertEqual(self.delivery().status, "assigned")
        self.assertNotIn(f"Delivery #{self.task.id}", self.page(self.other, "/dashboard/delivery"))
        self.assertIn("No deliveries right now", self.page(self.other, "/dashboard/delivery"))

    def test_history_shows_only_your_own_finished_jobs(self):
        for action in ("accept", "pickup", "out", "deliver"):
            self.step(self.task, action)
        self.assertIn(f"#{self.task.id}", self.page(self.rider, "/delivery/history"))
        self.assertIn("No completed deliveries yet", self.page(self.other, "/delivery/history"))
        self.assertEqual(self.other.get(f"/delivery/tasks/{self.task.id}").status_code, 404)

    def test_service_layer_refuses_someone_elses_delivery_too(self):
        with self.assertRaises(delivery_service.DeliveryError):
            delivery_service.advance(self.task, "accept", self.other_partner)
        self.assertEqual(self.delivery().status, "assigned")

    def test_unknown_delivery_is_404(self):
        self.assertEqual(self.rider.get("/delivery/tasks/9999").status_code, 404)


class PartnerAccessTests(StaffTestCase):
    def setUp(self):
        super().setUp()
        self.order = self.ready_order()
        self.assign(self.order)
        self.task = self.delivery()

    def test_only_delivery_partners_may_use_delivery_pages(self):
        paths = [("get", "/dashboard/delivery"), ("get", "/delivery/history"),
                 ("get", f"/delivery/tasks/{self.task.id}"), ("post", f"/delivery/tasks/{self.task.id}/accept")]
        visitor = self.app.test_client()
        for method, path in paths:
            response = getattr(visitor, method)(path)
            self.assertEqual(response.status_code, 302, path)
            self.assertIn("/login", response.location)
        for client in (self.customer, self.seller_a, self.admin):
            for method, path in paths:
                self.assertEqual(getattr(client, method)(path).status_code, 403, path)
        self.assertEqual(self.delivery().status, "assigned")

    def test_partners_cannot_reach_shop_or_admin_functions(self):
        product = self.apple
        attempts = [
            ("get", "/shopkeeper/products"), ("get", f"/shopkeeper/products/{product.id}/edit"),
            ("post", f"/shopkeeper/products/{product.id}/edit"),
            ("post", f"/shopkeeper/products/{product.id}/quick-update"),
            ("post", f"/shopkeeper/products/{product.id}/delete"), ("get", "/shopkeeper/shop/edit"),
            ("post", f"/shopkeeper/orders/{self.order.id}/accept"),
            ("get", "/admin/users"), ("get", "/admin/shops"), ("get", "/admin/orders"),
            ("post", f"/admin/orders/{self.order.id}/assign"), ("get", "/dashboard/admin"),
            ("get", "/cart"), ("post", "/checkout"),
        ]
        for method, path in attempts:
            response = getattr(self.rider, method)(path, data={"price": "1", "stock_quantity": "0"})
            self.assertEqual(response.status_code, 403, path)
        db.session.expire_all()
        self.assertEqual(self.apple.price, Decimal("10.00"))
        self.assertEqual(self.apple.stock_quantity, 3)

    def test_a_deactivated_partner_is_logged_out_immediately(self):
        self.assertEqual(self.rider.get("/dashboard/delivery").status_code, 200)
        self.partner.is_active = False
        db.session.commit()
        response = self.rider.get("/dashboard/delivery")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.location)


class HistoryAndDashboardTests(StaffTestCase):
    def test_history_lists_newest_first_and_dashboard_counts(self):
        first = self.ready_order()
        self.assign(first)
        first_task = self.delivery()
        for action in ("accept", "pickup", "out", "deliver"):
            self.step(first_task, action)

        self.add(self.customer, self.apple, 1)
        self.checkout()
        second = self.all_orders()[-1]
        for action in ("accept", "preparing", "ready"):
            self.order_for(self.seller_a, second, action)
        self.assign(second)
        second_task = self.delivery()
        for action in ("accept", "pickup", "out", "deliver"):
            self.step(second_task, action)

        page = self.page(self.rider, "/delivery/history")
        self.assertLess(page.index(f"#{second_task.id}"), page.index(f"#{first_task.id}"))
        self.assertIn("2 completed deliveries", page)
        self.assertEqual(delivery_service.partner_counts(self.partner),
                         {"awaiting": 0, "in_progress": 0, "delivered": 2})

    def test_empty_states(self):
        self.assertIn("No deliveries right now", self.page(self.rider, "/dashboard/delivery"))
        self.assertIn("No completed deliveries yet", self.page(self.rider, "/delivery/history"))


class DeliveryRulesTests(StaffTestCase):
    def test_table_of_actions_matches_the_order_workflow(self):
        for name, action in delivery_service.ACTIONS.items():
            if action.order_action:
                order_action = order_service.ACTIONS[action.order_action]
                self.assertEqual(order_action.actor, "delivery_partner", name)
        self.assertEqual(set(delivery_service.DELIVERY_LABELS), set(delivery_service.DELIVERY_PROGRESS))

    def test_buttons_offered_per_status(self):
        order = self.ready_order()
        self.assign(order)
        task = self.delivery()
        seen = []
        for status in ("assigned", "accepted", "picked_up", "out_for_delivery", "delivered"):
            task.status = status
            seen.append([name for name, _label, _confirm in delivery_service.available_actions(task)])
        self.assertEqual(seen, [["accept"], ["pickup"], ["out"], ["deliver"], []])

    def test_the_delivery_table_still_allows_one_delivery_per_order(self):
        order = self.ready_order()
        self.assign(order)
        db.session.add(Delivery(order_id=order.id, delivery_partner_id=self.partner.id))
        with self.assertRaises(Exception):
            db.session.commit()
        db.session.rollback()


class DeliveryCsrfTests(StaffTestCase):
    base_config = CsrfEnabledConfig

    def test_delivery_posts_need_a_token(self):
        with self.rider.session_transaction() as session:
            session["_user_id"] = str(self.partner.id)
            session["_fresh"] = True
        self.assertEqual(self.rider.post("/delivery/tasks/1/accept").status_code, 400)


if __name__ == "__main__":
    unittest.main()
