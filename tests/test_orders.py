"""Placing orders, the order workflow, and who may see or change an order."""
import unittest
from decimal import Decimal
from unittest import mock

from app.extensions import db
from app.models.cart import CartItem
from app.models.order import Order, OrderItem
from app.models.product import Product
from app.services import cart_service, checkout_service, order_service, shop_service
from tests.test_auth import CsrfEnabledConfig
from tests.test_cart import CartTestCase

DELIVERY = {
    "full_name": "Cathy Customer",
    "phone": "9876543210",
    "address": "12 Market Road, Gandhi Nagar",
    "notes": "",
    "payment": "cod",
}


class OrderTestCase(CartTestCase):
    """Cart with 2 x Apple (10.00) + 1 x Pear (20.50) from Shop A = 40.50, delivery 25.00."""

    def fill_cart(self, client=None):
        client = client or self.customer
        self.add(client, self.apple, 2)
        self.add(client, self.pear, 1)

    def total(self, email="cathy@example.com"):
        return cart_service.summary(self.user(email))["total"]

    def checkout(self, client=None, email="cathy@example.com", **overrides):
        client = client or self.customer
        data = dict(DELIVERY, expected_total=str(self.total(email)))
        data.update(overrides)
        return client.post("/checkout", data=data)

    def all_orders(self):
        db.session.expire_all()
        return Order.query.order_by(Order.id).all()

    def stock(self, product):
        db.session.expire_all()
        return db.session.get(Product, product.id).stock_quantity

    def place(self):
        """Fill the cart and check out; return the new Order."""
        self.fill_cart()
        response = self.checkout()
        self.assertEqual(response.status_code, 302, response.get_data(as_text=True)[:300])
        return self.all_orders()[-1]

    def seller_client(self, shop):
        return self.login_client(shop.owner.email, role="shopkeeper")

    def order_for(self, client, order, action):
        return client.post(f"/shopkeeper/orders/{order.id}/{action}", follow_redirects=True)


class PlaceOrderTests(OrderTestCase):
    def test_successful_order(self):
        self.fill_cart()
        response = self.checkout()
        self.assertEqual(response.status_code, 302)

        order = self.all_orders()[0]
        self.assertTrue(response.location.endswith(f"/orders/{order.id}/confirmation"))
        self.assertEqual(order.customer_id, self.user().id)
        self.assertEqual(order.shop_id, self.shop_a.id)
        self.assertEqual(order.status, "pending")
        self.assertEqual(order.payment_status, "pending")
        self.assertEqual(order.total_amount, Decimal("65.50"))       # 40.50 + 25.00 delivery
        self.assertEqual(sorted((i.product.name, i.quantity, i.price_at_purchase) for i in order.items),
                         [("Apple", 2, Decimal("10.00")), ("Pear", 1, Decimal("20.50"))])

    def test_stock_is_reduced_and_cart_is_emptied(self):
        self.fill_cart()
        self.checkout()
        self.assertEqual(self.stock(self.apple), 3)
        self.assertEqual(self.stock(self.pear), 9)
        self.assertEqual(self.items(), {})
        self.assertEqual(CartItem.query.count(), 0)

    def test_confirmation_page(self):
        order = self.place()
        page = self.page(self.customer, f"/orders/{order.id}/confirmation")
        for text in ("Your order is placed", f"#{order.id}", "Shop A", "₹65.50", "₹25",
                     "Cash on delivery", "Apple", "Pending"):
            self.assertIn(text, page)

    def test_free_delivery_over_the_limit(self):
        big = self.make_product(self.shop_a, "Big Item", "250.00")
        self.add(self.customer, big)
        self.checkout()
        self.assertEqual(self.all_orders()[0].total_amount, Decimal("250.00"))

    def test_browser_cannot_set_price_total_shop_or_status(self):
        self.fill_cart()
        self.checkout(total_amount="1", total="1", price="0.01", shop_id=str(self.shop_b.id),
                      status="delivered", payment_status="paid", customer_id="999",
                      product_id=str(self.bread.id))
        order = self.all_orders()[0]
        self.assertEqual(order.total_amount, Decimal("65.50"))
        self.assertEqual(order.shop_id, self.shop_a.id)
        self.assertEqual((order.status, order.payment_status), ("pending", "pending"))
        self.assertEqual(order.customer_id, self.user().id)

    def test_expected_total_is_only_a_price_change_check(self):
        self.fill_cart()
        response = self.checkout(expected_total="1.00")  # a lie
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.all_orders(), [])  # refused, not trusted
        self.assertEqual(self.items(), {"Apple": 2, "Pear": 1})
        # leaving it out entirely is harmless: the amount is still computed on the server
        data = dict(DELIVERY)
        self.customer.post("/checkout", data=data)
        self.assertEqual(self.all_orders()[0].total_amount, Decimal("65.50"))

    def test_price_change_between_viewing_and_confirming(self):
        self.fill_cart()
        seen = self.total()
        self.pear.price = Decimal("30.00")
        db.session.commit()
        response = self.customer.post("/checkout", data=dict(DELIVERY, expected_total=str(seen)),
                                      follow_redirects=True)
        self.assertIn("Prices in your cart changed", response.get_data(as_text=True))
        self.assertEqual(self.all_orders(), [])
        self.assertEqual(self.stock(self.apple), 5)
        self.assertIn("₹75", self.page(self.customer, "/checkout"))   # the new total is shown
        self.assertEqual(self.checkout().status_code, 302)              # confirming again works
        self.assertEqual(self.all_orders()[0].total_amount, Decimal("75.00"))

    def test_prices_are_frozen_in_the_order(self):
        order = self.place()
        self.apple.price = Decimal("99.00")
        db.session.commit()
        page = self.page(self.customer, f"/orders/{order.id}")
        self.assertIn("₹10 each", page)
        self.assertNotIn("₹99", page)
        self.assertEqual(self.all_orders()[0].total_amount, Decimal("65.50"))

    def test_delivery_details_are_saved_together(self):
        self.fill_cart()
        self.checkout(full_name="  Cathy   C ", phone="+91 98765-43210",
                      address="12  Market Road,   Gandhi Nagar", notes="Ring   twice")
        order = self.all_orders()[0]
        self.assertEqual(order.delivery_address,
                         "Cathy C · 9876543210\n12 Market Road, Gandhi Nagar\nNote: Ring twice")
        self.assertLessEqual(len(order.delivery_address), 255)


class CheckoutValidationTests(OrderTestCase):
    def setUp(self):
        super().setUp()
        self.fill_cart()

    def refused(self, **overrides):
        response = self.checkout(**overrides)
        self.assertEqual(response.status_code, 200, overrides)  # form shown again
        self.assertEqual(self.all_orders(), [], overrides)
        self.assertEqual(self.stock(self.apple), 5, overrides)
        self.assertEqual(self.items(), {"Apple": 2, "Pear": 1}, overrides)
        return response.get_data(as_text=True)

    def test_bad_delivery_details(self):
        self.refused(full_name="A")
        self.refused(full_name="x" * 51)
        for phone in ("", "12345", "5876543210", "abcdefghij", "98765432101"):
            self.assertIn("valid 10-digit mobile number", self.refused(phone=phone), phone)
        self.refused(address="short")
        self.refused(address="x" * 111)
        self.refused(notes="x" * 51)

    def test_only_cash_on_delivery(self):
        self.assertIn("Only cash on delivery", self.refused(payment="online"))
        self.assertIn("Only cash on delivery", self.refused(payment="card"))

    def test_form_keeps_what_was_typed(self):
        page = self.refused(full_name="Kept Name", phone="123")
        self.assertIn("Kept Name", page)

    def test_empty_cart_cannot_check_out(self):
        self.customer.post("/cart/clear")
        response = self.customer.post("/checkout", data=DELIVERY, follow_redirects=True)
        self.assertIn("Your cart is empty", response.get_data(as_text=True))
        self.assertEqual(self.all_orders(), [])

    def test_pressing_place_order_twice_makes_one_order(self):
        data = dict(DELIVERY, expected_total=str(self.total()))
        self.customer.post("/checkout", data=data)
        self.customer.post("/checkout", data=data)
        self.assertEqual(len(self.all_orders()), 1)
        self.assertEqual(self.stock(self.apple), 3)  # reduced once, not twice


class UnavailableProductTests(OrderTestCase):
    def setUp(self):
        super().setUp()
        self.fill_cart()

    def assert_nothing_happened(self, response):
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith("/cart"))
        self.assertEqual(self.all_orders(), [])
        self.assertEqual(self.items(), {"Apple": 2, "Pear": 1})

    def test_stock_dropped_after_adding(self):
        self.apple.stock_quantity = 1
        db.session.commit()
        self.assert_nothing_happened(self.checkout())
        self.assertEqual(self.stock(self.apple), 1)
        self.assertEqual(self.stock(self.pear), 10)

    def test_product_hidden_or_shop_unapproved_after_adding(self):
        self.pear.is_available = False
        db.session.commit()
        self.assert_nothing_happened(self.checkout(expected_total="0"))
        self.pear.is_available = True
        self.shop_a.is_approved = False
        db.session.commit()
        self.assert_nothing_happened(self.checkout(expected_total="0"))
        self.assertEqual(self.stock(self.apple), 5)

    def test_last_item_taken_by_someone_else_at_the_very_last_moment(self):
        """Stock reservation is one conditional UPDATE, so it can't oversell."""
        self.assertFalse(checkout_service.reserve_stock(self.apple.id, 6))
        self.assertEqual(self.stock(self.apple), 5)
        self.assertTrue(checkout_service.reserve_stock(self.apple.id, 5))
        self.assertFalse(checkout_service.reserve_stock(self.apple.id, 1))
        self.assertEqual(self.stock(self.apple), 0)
        db.session.rollback()

    def test_a_failure_halfway_undoes_everything(self):
        real = checkout_service.reserve_stock
        calls = []

        def second_line_fails(product_id, quantity):
            calls.append(product_id)
            return False if len(calls) == 2 else real(product_id, quantity)

        with mock.patch.object(checkout_service, "reserve_stock", second_line_fails):
            response = self.customer.post("/checkout", data=dict(DELIVERY, expected_total=str(self.total())),
                                          follow_redirects=True)
        self.assertIn("just ran out of stock", response.get_data(as_text=True))
        self.assertEqual(len(calls), 2)
        self.assertEqual(self.stock(self.apple), 5)   # the first line's reservation was rolled back
        self.assertEqual(self.stock(self.pear), 10)
        self.assertEqual(self.all_orders(), [])
        self.assertEqual(OrderItem.query.count(), 0)
        self.assertEqual(self.items(), {"Apple": 2, "Pear": 1})

    def test_a_cart_with_two_shops_is_refused(self):
        cart = self.user().cart
        db.session.add(CartItem(cart_id=cart.id, product_id=self.bread.id, quantity=1))
        db.session.commit()
        response = self.customer.post("/checkout", data=DELIVERY, follow_redirects=True)
        self.assertIn("only contain items from one shop", response.get_data(as_text=True))
        self.assertEqual(self.all_orders(), [])
        self.assertEqual(self.stock(self.bread), 10)


class WorkflowRuleTests(OrderTestCase):
    """The status rules, tested as pure rules."""

    def order_in(self, status):
        order = Order(customer_id=self.user().id, shop_id=self.shop_a.id, delivery_address="Home, Town",
                      total_amount=Decimal("10.00"), status=status)
        order.items.append(OrderItem(product_id=self.apple.id, quantity=1, price_at_purchase=Decimal("10.00")))
        db.session.add(order)
        db.session.commit()
        return order

    def test_every_status_is_in_the_workflow_and_has_a_label(self):
        from app.models.order import ORDER_STATUSES
        self.assertEqual(set(order_service.WORKFLOW), set(ORDER_STATUSES))
        self.assertEqual(set(order_service.STATUS_LABELS), set(ORDER_STATUSES))

    def test_finished_orders_have_no_way_out(self):
        for status in order_service.FINISHED_STATUSES:
            self.assertEqual(order_service.WORKFLOW[status], set(), status)

    def test_every_action_follows_the_workflow(self):
        for name, action in order_service.ACTIONS.items():
            for start in action.from_statuses:
                self.assertIn(action.to_status, order_service.WORKFLOW[start], name)

    def test_who_may_press_what(self):
        expected = {
            ("pending", "shopkeeper"): {"accept", "reject"},
            ("pending", "customer"): {"cancel"},
            ("confirmed", "shopkeeper"): {"preparing"},
            ("confirmed", "customer"): set(),
            ("preparing", "shopkeeper"): {"ready"},
            ("preparing", "customer"): set(),
            ("ready_for_pickup", "shopkeeper"): set(),
            ("ready_for_pickup", "customer"): set(),
            ("out_for_delivery", "shopkeeper"): set(),
            ("delivered", "shopkeeper"): set(),
            ("delivered", "customer"): set(),
            ("rejected", "shopkeeper"): set(),
            ("cancelled", "customer"): set(),
        }
        for (status, actor), names in expected.items():
            order = self.order_in(status)
            got = {name for name, _label in order_service.available_actions(order, actor)}
            self.assertEqual(got, names, (status, actor))

    def test_invalid_moves_are_refused_and_change_nothing(self):
        for status in order_service.WORKFLOW:
            for name, action in order_service.ACTIONS.items():
                if status in action.from_statuses:
                    continue
                order = self.order_in(status)
                with self.assertRaises(ValueError, msg=(status, name)):
                    order_service.apply_action(order, name, action.actor)
                db.session.refresh(order)
                self.assertEqual(order.status, status)

    def test_wrong_person_cannot_use_an_action(self):
        order = self.order_in("pending")
        for name, actor in (("accept", "customer"), ("cancel", "shopkeeper"), ("reject", "customer"),
                            ("nonsense", "shopkeeper")):
            with self.assertRaises(ValueError):
                order_service.apply_action(order, name, actor)
        self.assertEqual(order.status, "pending")


class CustomerCancelTests(OrderTestCase):
    def test_cancel_pending_order_returns_the_stock(self):
        order = self.place()
        self.assertEqual(self.stock(self.apple), 3)
        response = self.customer.post(f"/orders/{order.id}/cancel", follow_redirects=True)
        page = response.get_data(as_text=True)
        self.assertIn("Your order was cancelled", page)
        self.assertIn("returned to the shop", page)
        self.assertEqual(self.all_orders()[0].status, "cancelled")
        self.assertEqual(self.stock(self.apple), 5)
        self.assertEqual(self.stock(self.pear), 10)

    def test_cancelling_twice_does_not_return_stock_twice(self):
        order = self.place()
        self.customer.post(f"/orders/{order.id}/cancel")
        page = self.customer.post(f"/orders/{order.id}/cancel", follow_redirects=True).get_data(as_text=True)
        self.assertIn("not available", page)
        self.assertEqual(self.stock(self.apple), 5)

    def test_cannot_cancel_once_the_shop_accepted(self):
        order = self.place()
        self.order_for(self.seller_client(self.shop_a), order, "accept")
        page = self.customer.post(f"/orders/{order.id}/cancel", follow_redirects=True).get_data(as_text=True)
        self.assertIn("not available", page)
        self.assertEqual(self.all_orders()[0].status, "confirmed")
        self.assertEqual(self.stock(self.apple), 3)
        self.assertNotIn("Cancel order", self.page(self.customer, f"/orders/{order.id}"))

    def test_cancel_button_shown_only_while_pending(self):
        order = self.place()
        self.assertIn("Cancel order", self.page(self.customer, f"/orders/{order.id}"))

    def test_shopkeeper_cannot_cancel_for_the_customer(self):
        order = self.place()
        page = self.order_for(self.seller_client(self.shop_a), order, "cancel").get_data(as_text=True)
        self.assertIn("Unknown action", page)
        self.assertEqual(self.all_orders()[0].status, "pending")


class ShopkeeperLifecycleTests(OrderTestCase):
    def test_full_path_to_ready_for_pickup(self):
        order = self.place()
        seller = self.seller_client(self.shop_a)

        page = self.page(seller, "/shopkeeper/orders")
        for text in (f"Order #{order.id}", "Customer", "Accept order", "Pending"):
            self.assertIn(text, page)
        detail = self.page(seller, f"/shopkeeper/orders/{order.id}")
        for text in ("12 Market Road, Gandhi Nagar", "9876543210", "₹65.50", "Delivery fee"):
            self.assertIn(text, detail)

        for action, status, label in (("accept", "confirmed", "Accepted"),
                                      ("preparing", "preparing", "Preparing"),
                                      ("ready", "ready_for_pickup", "Ready for pickup")):
            self.order_for(seller, order, action)
            self.assertEqual(self.all_orders()[0].status, status)
            self.assertIn(label, self.page(self.customer, f"/orders/{order.id}"))

        self.assertEqual(order_service.available_actions(self.all_orders()[0], "shopkeeper"), [])

    def test_reject_returns_stock_and_customer_sees_it(self):
        order = self.place()
        self.order_for(self.seller_client(self.shop_a), order, "reject")
        self.assertEqual(self.all_orders()[0].status, "rejected")
        self.assertEqual(self.stock(self.apple), 5)
        self.assertEqual(self.stock(self.pear), 10)
        page = self.page(self.customer, f"/orders/{order.id}")
        self.assertIn("Rejected", page)
        self.assertIn("could not accept", page)

    def test_the_shops_sales_do_not_include_delivery_fees(self):
        order = self.place()
        order.status = "delivered"
        db.session.commit()
        stats = shop_service.dashboard_stats(self.shop_a)
        self.assertEqual(order.total_amount, Decimal("65.50"))
        self.assertEqual(stats["total_sales"], Decimal("40.50"))

    def test_other_shops_cannot_see_the_order(self):
        order = self.place()
        seller_b = self.seller_client(self.shop_b)
        self.assertEqual(seller_b.get(f"/shopkeeper/orders/{order.id}").status_code, 404)
        self.assertEqual(seller_b.post(f"/shopkeeper/orders/{order.id}/accept").status_code, 404)
        self.assertNotIn(f"Order #{order.id}", self.page(seller_b, "/shopkeeper/orders"))
        self.assertEqual(self.all_orders()[0].status, "pending")


class OrderPrivacyTests(OrderTestCase):
    def setUp(self):
        super().setUp()
        self.order = self.place()
        self.other = self.login_client("olive@example.com")

    def test_customers_cannot_open_each_others_orders(self):
        for path in (f"/orders/{self.order.id}", f"/orders/{self.order.id}/confirmation"):
            self.assertEqual(self.other.get(path).status_code, 404, path)
        self.assertEqual(self.other.post(f"/orders/{self.order.id}/cancel").status_code, 404)
        self.assertEqual(self.all_orders()[0].status, "pending")
        self.assertEqual(self.customer.get(f"/orders/{self.order.id}").status_code, 200)

    def test_history_lists_only_your_own_orders(self):
        self.assertIn(f"Order #{self.order.id}", self.page(self.customer, "/orders"))
        page = self.page(self.other, "/orders")
        self.assertNotIn(f"Order #{self.order.id}", page)
        self.assertIn("No orders yet", page)

    def test_unknown_order_is_404(self):
        self.assertEqual(self.customer.get("/orders/9999").status_code, 404)

    def test_visitors_and_other_roles_are_kept_out(self):
        paths = [("get", "/orders"), ("get", f"/orders/{self.order.id}"),
                 ("get", f"/orders/{self.order.id}/confirmation"),
                 ("post", f"/orders/{self.order.id}/cancel"), ("post", "/checkout")]
        visitor = self.app.test_client()
        for method, path in paths:
            response = getattr(visitor, method)(path)
            self.assertEqual(response.status_code, 302, path)
            self.assertIn("/login", response.location)
        for role in ("shopkeeper", "delivery_partner", "admin"):
            client = self.login_client(f"{role}@example.com", role)
            for method, path in paths:
                self.assertEqual(getattr(client, method)(path).status_code, 403, (role, path))
        self.assertEqual(self.all_orders()[0].status, "pending")


class OrderHistoryAndDashboardTests(OrderTestCase):
    def test_newest_first_with_status_and_totals(self):
        first = self.place()
        self.customer.post(f"/orders/{first.id}/cancel")
        self.add(self.customer, self.apple, 1)
        self.checkout()
        second = self.all_orders()[-1]
        page = self.page(self.customer, "/orders")
        self.assertLess(page.index(f"Order #{second.id}"), page.index(f"Order #{first.id}"))
        for text in ("Cancelled", "Pending", "₹35", "₹65.50", "1 × Apple"):
            self.assertIn(text, page)

    def test_dashboard_shows_real_numbers(self):
        page = self.page(self.customer, "/dashboard/customer")
        self.assertNotIn("Preview", page)
        first = self.place()
        self.add(self.customer, self.apple, 1)
        self.checkout()
        self.customer.post(f"/orders/{first.id}/cancel")
        page = self.page(self.customer, "/dashboard/customer")
        self.assertIn("is in progress", page)            # the second order is still active
        self.assertIn('stat-number">1<', page)          # 1 active order
        self.assertIn('stat-number">2<', page)          # 2 orders in total


class DemoOrdersStockTests(OrderTestCase):
    def test_seeded_demo_orders_reserve_stock_like_real_ones(self):
        self.apple.stock_quantity = 10
        self.pear.stock_quantity = 10
        db.session.commit()
        result = self.app.test_cli_runner().invoke(
            args=["seed-demo-orders", "--email", self.shop_a.owner.email])
        self.assertEqual(result.exit_code, 0, result.output)
        # Every demo order is pending / accepted / preparing / delivered (none rejected)
        self.assertEqual(self.stock(self.apple), 2)
        self.assertEqual(self.stock(self.pear), 2)


class OrderCsrfTests(OrderTestCase):
    base_config = CsrfEnabledConfig

    def test_order_posts_need_a_token(self):
        with self.customer.session_transaction() as session:
            session["_user_id"] = str(self.user().id)
            session["_fresh"] = True
        for path in ("/checkout", "/orders/1/cancel", "/cart/add"):
            self.assertEqual(self.customer.post(path, data=DELIVERY).status_code, 400, path)
        self.assertEqual(self.all_orders(), [])


if __name__ == "__main__":
    unittest.main()
