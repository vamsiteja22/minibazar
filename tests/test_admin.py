"""Admin: access, statistics, users, shop approval, categories, orders and assigning partners."""
import unittest
from decimal import Decimal

from app.extensions import db
from app.models.category import Category
from app.models.delivery import Delivery
from app.models.shop import Shop
from app.models.user import User
from app.services import admin_service, delivery_service
from tests.staff_base import StaffTestCase
from tests.test_auth import CsrfEnabledConfig, PASSWORD


class AdminAccessTests(StaffTestCase):
    def setUp(self):
        super().setUp()
        self.order = self.ready_order()
        self.pages = ["/dashboard/admin", "/admin/users", "/admin/shops", "/admin/categories",
                      "/admin/orders", f"/admin/orders/{self.order.id}", "/admin/delivery-partners"]
        self.posts = [f"/admin/users/{self.customer_id()}/deactivate", f"/admin/shops/{self.shop_a.id}/approve",
                      f"/admin/shops/{self.shop_a.id}/reject", "/admin/categories",
                      f"/admin/categories/{self.veg.id}/delete", f"/admin/orders/{self.order.id}/assign"]

    def customer_id(self):
        return User.query.filter_by(email="cathy@example.com").one().id

    def test_admin_can_open_every_page(self):
        for path in self.pages:
            self.assertEqual(self.admin.get(path).status_code, 200, path)

    def test_visitors_are_sent_to_login(self):
        visitor = self.app.test_client()
        for path in self.pages:
            response = visitor.get(path)
            self.assertEqual(response.status_code, 302, path)
            self.assertIn("/login", response.location)
        for path in self.posts:
            self.assertEqual(visitor.post(path).status_code, 302, path)

    def test_no_other_role_gets_in(self):
        for client in (self.customer, self.seller_a, self.rider):
            for path in self.pages:
                self.assertEqual(client.get(path).status_code, 403, path)
            for path in self.posts:
                self.assertEqual(client.post(path, data={"name": "Hacked", "reason": "no reason",
                                                         "partner_id": self.partner.id}).status_code, 403, path)
        # nothing changed
        db.session.expire_all()
        self.assertTrue(self.shop_a.is_approved)
        self.assertEqual(Category.query.filter_by(name="Hacked").count(), 0)
        self.assertTrue(User.query.filter_by(email="cathy@example.com").one().is_active)
        self.assertIsNone(self.delivery())

    def test_admin_pages_are_not_reachable_through_customer_routes(self):
        self.assertEqual(self.admin.get("/cart").status_code, 403)
        self.assertEqual(self.admin.get("/shopkeeper/products").status_code, 403)
        self.assertEqual(self.admin.get("/delivery/history").status_code, 403)


class DashboardStatsTests(StaffTestCase):
    def test_numbers(self):
        order = self.ready_order()
        self.assign(order)
        task = self.delivery()
        for action in ("accept", "pickup", "out", "deliver"):
            self.step(task, action)
        self.add(self.customer, self.bread, 1)   # cart only, so no second order
        pending_shop = self.make_shop("New Shop", approved=False, owner_email="new@example.com")
        self.make_product(pending_shop, "Tea", available=False)

        stats = admin_service.platform_stats()
        self.assertEqual(stats["customers"], 1)
        self.assertEqual(stats["partners"], 1)
        self.assertEqual(stats["shopkeepers"], 3)                  # Shop A, Shop B, New Shop
        self.assertEqual(stats["admins"], 1)
        self.assertEqual(stats["users_total"], 6)
        self.assertEqual((stats["shops_total"], stats["shops_approved"], stats["shops_pending"]), (3, 2, 1))
        self.assertEqual((stats["products_total"], stats["products_available"]), (4, 3))
        self.assertEqual(stats["orders_total"], 1)
        self.assertEqual(stats["orders_by_status"]["delivered"], 1)
        self.assertEqual(stats["delivered_sales"], Decimal("40.50"))   # goods only, not the 25 delivery
        self.assertEqual((stats["needs_partner"], stats["deliveries_active"]), (0, 0))

    def test_dashboard_page_shows_the_headline_numbers(self):
        self.ready_order()
        page = self.page(self.admin, "/dashboard/admin")
        for text in ("Total users", "Total shops", "Total products", "Total orders",
                     "Needs your attention", "Orders by status", "Ready for pickup"):
            self.assertIn(text, page)
        self.assertIn('cart-badge">1<', page)   # one order needs a partner


class UserManagementTests(StaffTestCase):
    def user(self, email):
        db.session.expire_all()
        return User.query.filter_by(email=email).one()

    def test_list_filters_and_search_and_hides_admins(self):
        page = self.page(self.admin, "/admin/users")
        for text in ("cathy@example.com", "Ravi Rider", "owner-shopa@example.com"):
            self.assertIn(text, page)
        self.assertNotIn("admin@example.com", page)
        only = self.page(self.admin, "/admin/users?role=delivery_partner")
        self.assertIn("Ravi Rider", only)
        self.assertNotIn("cathy@example.com", only)
        found = self.page(self.admin, "/admin/users?q=CATHY")
        self.assertIn("cathy@example.com", found)
        self.assertNotIn("rider@example.com", found)
        self.assertIn("No users found", self.page(self.admin, "/admin/users?q=zzzz"))

    def test_deactivated_customer_cannot_log_in_and_is_logged_out(self):
        cathy = self.user("cathy@example.com")
        self.assertEqual(self.customer.get("/cart").status_code, 200)
        self.admin.post(f"/admin/users/{cathy.id}/deactivate")
        self.assertFalse(self.user("cathy@example.com").is_active)

        response = self.customer.get("/cart")                       # already signed in: ended at once
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.location)

        fresh = self.app.test_client()
        page = fresh.post("/login", data={"email": "cathy@example.com", "password": PASSWORD},
                          follow_redirects=True).get_data(as_text=True)
        self.assertIn("has been deactivated", page)
        self.assertEqual(fresh.get("/cart").status_code, 302)
        wrong = fresh.post("/login", data={"email": "cathy@example.com", "password": "wrong-pass"},
                           follow_redirects=True).get_data(as_text=True)
        self.assertIn("Invalid email or password", wrong)   # a wrong password does not reveal the status

    def test_reactivate_restores_login(self):
        cathy = self.user("cathy@example.com")
        self.admin.post(f"/admin/users/{cathy.id}/deactivate")
        self.admin.post(f"/admin/users/{cathy.id}/reactivate")
        client = self.app.test_client()
        client.post("/login", data={"email": "cathy@example.com", "password": PASSWORD})
        self.assertEqual(client.get("/cart").status_code, 200)

    def test_deactivating_a_shopkeeper_takes_the_shop_off_the_site(self):
        self.assertIn("Apple", self.page(self.app.test_client(), "/products"))
        owner = self.shop_a.owner
        self.admin.post(f"/admin/users/{owner.id}/deactivate")
        db.session.expire_all()
        shop = db.session.get(Shop, self.shop_a.id)
        self.assertEqual((shop.is_approved, shop.rejection_reason), (False, "Owner account deactivated."))
        self.assertNotIn("Apple", self.page(self.app.test_client(), "/products"))

        self.admin.post(f"/admin/users/{owner.id}/reactivate")
        self.assertFalse(db.session.get(Shop, self.shop_a.id).is_approved)   # must be approved again
        self.admin.post(f"/admin/shops/{self.shop_a.id}/approve")
        self.assertTrue(db.session.get(Shop, self.shop_a.id).is_approved)

    def test_partner_with_active_delivery_cannot_be_deactivated(self):
        order = self.ready_order()
        self.assign(order)
        page = self.admin.post(f"/admin/users/{self.partner.id}/deactivate",
                               follow_redirects=True).get_data(as_text=True)
        self.assertIn("deliveries in progress", page)
        self.assertTrue(self.user("rider@example.com").is_active)
        for action in ("accept", "pickup", "out", "deliver"):
            self.step(self.delivery(), action)
        self.admin.post(f"/admin/users/{self.partner.id}/deactivate")
        self.assertFalse(self.user("rider@example.com").is_active)

    def test_admins_cannot_be_managed_from_the_web(self):
        admin_id = self.user("admin@example.com").id
        self.assertEqual(self.admin.post(f"/admin/users/{admin_id}/deactivate").status_code, 404)
        self.assertEqual(self.admin.post("/admin/users/9999/deactivate").status_code, 404)
        self.assertTrue(self.user("admin@example.com").is_active)

    def test_double_actions_are_reported(self):
        cathy = self.user("cathy@example.com")
        self.assertIn("already active", self.admin.post(f"/admin/users/{cathy.id}/reactivate",
                                                        follow_redirects=True).get_data(as_text=True))
        self.admin.post(f"/admin/users/{cathy.id}/deactivate")
        self.assertIn("already deactivated", self.admin.post(f"/admin/users/{cathy.id}/deactivate",
                                                              follow_redirects=True).get_data(as_text=True))


class ShopApprovalTests(StaffTestCase):
    def setUp(self):
        super().setUp()
        self.new_shop = self.make_shop("New Shop", approved=False, owner_email="new@example.com")
        self.make_product(self.new_shop, "Tea")
        self.public = self.app.test_client()
        self.owner = self.login_client("new@example.com", "shopkeeper")

    def shop(self):
        db.session.expire_all()
        return db.session.get(Shop, self.new_shop.id)

    def test_shops_are_hidden_until_approved(self):
        self.assertEqual(self.public.get(f"/shops/{self.new_shop.id}").status_code, 404)
        self.assertNotIn("Tea", self.page(self.public, "/products"))
        self.assertEqual(self.shop().approval_state, "pending")
        self.assertIn("New Shop", self.page(self.admin, "/admin/shops?state=pending"))

        page = self.admin.post(f"/admin/shops/{self.new_shop.id}/approve",
                               follow_redirects=True).get_data(as_text=True)
        self.assertIn("is approved and now visible", page)
        self.assertEqual(self.shop().approval_state, "approved")
        self.assertEqual(self.public.get(f"/shops/{self.new_shop.id}").status_code, 200)
        self.assertIn("Tea", self.page(self.public, "/products"))

    def test_reject_needs_a_reason_and_the_shopkeeper_sees_it(self):
        for reason in ("", "no", "   ", "x" * 256):
            self.admin.post(f"/admin/shops/{self.new_shop.id}/reject", data={"reason": reason})
            self.assertEqual(self.shop().approval_state, "pending", repr(reason))

        self.admin.post(f"/admin/shops/{self.new_shop.id}/reject", data={"reason": "Address looks incomplete"})
        shop = self.shop()
        self.assertEqual((shop.approval_state, shop.rejection_reason), ("rejected", "Address looks incomplete"))
        self.assertEqual(self.public.get(f"/shops/{self.new_shop.id}").status_code, 404)
        page = self.page(self.owner, "/dashboard/shopkeeper")
        self.assertIn("not visible to customers", page)
        self.assertIn("Address looks incomplete", page)
        self.assertIn("Rejected", page)
        self.assertIn("Address looks incomplete", self.page(self.admin, "/admin/shops?state=rejected"))

    def test_editing_a_rejected_shop_sends_it_back_for_review(self):
        self.admin.post(f"/admin/shops/{self.new_shop.id}/reject", data={"reason": "Address looks incomplete"})
        self.owner.post("/shopkeeper/shop/edit", data={"name": "New Shop", "address": "5 Full Address Road, Town"})
        self.assertEqual(self.shop().approval_state, "pending")
        self.assertIn("New Shop", self.page(self.admin, "/admin/shops?state=pending"))

    def test_an_approved_shop_can_be_suspended_and_approved_again(self):
        self.admin.post(f"/admin/shops/{self.shop_a.id}/reject", data={"reason": "Complaints received"})
        db.session.expire_all()
        self.assertFalse(db.session.get(Shop, self.shop_a.id).is_approved)
        self.assertNotIn("Apple", self.page(self.public, "/products"))
        self.admin.post(f"/admin/shops/{self.shop_a.id}/approve")
        db.session.expire_all()
        shop = db.session.get(Shop, self.shop_a.id)
        self.assertEqual((shop.is_approved, shop.rejection_reason), (True, None))

    def test_a_shop_with_a_deactivated_owner_cannot_be_approved(self):
        self.new_shop.owner.is_active = False
        db.session.commit()
        page = self.admin.post(f"/admin/shops/{self.new_shop.id}/approve",
                               follow_redirects=True).get_data(as_text=True)
        self.assertIn("Reactivate it first", page)
        self.assertEqual(self.shop().approval_state, "pending")

    def test_a_suspended_shop_cannot_be_ordered_from_but_orders_in_progress_continue(self):
        order = self.place()
        self.admin.post(f"/admin/shops/{self.shop_a.id}/reject", data={"reason": "Under review"})
        self.assertEqual(self.public.get(f"/shops/{self.shop_a.id}").status_code, 404)
        self.order_for(self.seller_a, order, "accept")                # existing order still works
        self.assertEqual(self.all_orders()[0].status, "confirmed")
        self.assertIn("not available", self.add(self.customer, self.apple).get_data(as_text=True))

    def test_filters_and_unknown_shop(self):
        for state in ("all", "pending", "approved", "rejected", "bogus"):
            self.assertEqual(self.admin.get(f"/admin/shops?state={state}").status_code, 200)
        self.assertEqual(self.admin.post("/admin/shops/9999/approve").status_code, 404)


class CategoryTests(StaffTestCase):
    def names(self):
        db.session.expire_all()
        return {c.name for c in Category.query.all()}

    def test_create_and_validate(self):
        self.admin.post("/admin/categories", data={"name": "  Pet   Supplies "})
        self.assertIn("Pet Supplies", self.names())
        for bad in ("", "x", "y" * 81, "pet supplies", "BAKERY"):
            before = self.names()
            page = self.admin.post("/admin/categories", data={"name": bad},
                                   follow_redirects=True).get_data(as_text=True)
            self.assertEqual(self.names(), before, repr(bad))
            self.assertTrue("must be 2 to 80" in page or "already exists" in page, repr(bad))

    def test_rename(self):
        extra = Category(name="Sweets")
        db.session.add(extra)
        db.session.commit()
        self.admin.post(f"/admin/categories/{extra.id}/rename", data={"name": "Mithai"})
        self.assertIn("Mithai", self.names())
        self.assertIn("already exists", self.admin.post(f"/admin/categories/{extra.id}/rename",
                                                        data={"name": "bakery"},
                                                        follow_redirects=True).get_data(as_text=True))
        self.admin.post(f"/admin/categories/{extra.id}/rename", data={"name": "MITHAI"})  # same name, new case
        self.assertIn("MITHAI", self.names())

    def test_delete_only_when_unused(self):
        unused = Category(name="Unused")
        db.session.add(unused)
        db.session.commit()
        self.admin.post(f"/admin/categories/{unused.id}/delete")
        self.assertNotIn("Unused", self.names())

        page = self.admin.post(f"/admin/categories/{self.veg.id}/delete",
                               follow_redirects=True).get_data(as_text=True)   # Apple and Pear use it
        self.assertIn("cannot be deleted", page)
        self.assertIn("Fruits & Vegetables", self.names())
        self.assertEqual(self.admin.post("/admin/categories/9999/delete").status_code, 404)

    def test_page_shows_product_counts_and_new_category_reaches_shopkeepers(self):
        page = self.page(self.admin, "/admin/categories")
        self.assertIn("Fruits &amp; Vegetables", page)
        self.admin.post("/admin/categories", data={"name": "Pet Supplies"})
        self.assertIn("Pet Supplies", self.page(self.seller_a, "/shopkeeper/products/new"))


class OrderViewAndAssignTests(StaffTestCase):
    def test_all_orders_and_filters(self):
        first = self.ready_order()
        self.add(self.customer, self.apple, 1)
        self.checkout()
        second = self.all_orders()[-1]               # still pending
        page = self.page(self.admin, "/admin/orders")
        self.assertIn(f"#{first.id}", page)
        self.assertIn(f"#{second.id}", page)
        needs = self.page(self.admin, "/admin/orders?status=needs_partner")
        self.assertIn(f"#{first.id}", needs)
        self.assertNotIn(f"#{second.id}", needs)
        pending_tab = self.page(self.admin, "/admin/orders?status=pending")
        self.assertIn(f"#{second.id}", pending_tab)
        self.assertNotIn(f"#{first.id}", pending_tab)
        for key in admin_service.ORDER_FILTERS:
            self.assertEqual(self.admin.get(f"/admin/orders?status={key}").status_code, 200, key)
        self.assertEqual(self.admin.get("/admin/orders?status=bogus").status_code, 200)
        self.assertEqual(self.admin.get("/admin/orders/9999").status_code, 404)

    def test_order_detail_page(self):
        order = self.ready_order()
        page = self.page(self.admin, f"/admin/orders/{order.id}")
        for text in ("Cathy Customer · 9876543210", "Shop A", "₹65.50", "Ravi Rider", "Assign delivery partner",
                     "needs a delivery partner"):
            self.assertIn(text, page)

    def test_only_ready_unassigned_orders_can_be_assigned(self):
        order = self.place()                                           # still pending
        page = self.assign(order).get_data(as_text=True)
        self.assertIn("can be assigned", page)
        self.assertIsNone(self.delivery())
        self.assertNotIn("Assign delivery partner", self.page(self.admin, f"/admin/orders/{order.id}"))

        for action in ("accept", "preparing", "ready"):
            self.order_for(self.seller_a, order, action)
        self.assign(order)
        self.assertEqual(Delivery.query.count(), 1)
        self.assign(order, self.new_partner("dev@example.com", "Dev Dasher")[0])
        self.assertEqual(Delivery.query.count(), 1)   # not a second delivery
        self.assertIn("Ravi Rider", self.page(self.admin, f"/admin/orders/{order.id}"))

    def test_only_active_delivery_partners_can_be_chosen(self):
        order = self.ready_order()
        customer_user = User.query.filter_by(email="cathy@example.com").one()
        self.assertIn("Please choose a delivery partner", self.assign(order, customer_user).get_data(as_text=True))
        for bad in ("", "abc", "9999"):
            page = self.admin.post(f"/admin/orders/{order.id}/assign", data={"partner_id": bad},
                                   follow_redirects=True).get_data(as_text=True)
            self.assertIn("Please choose a delivery partner", page, bad)
        self.partner.is_active = False
        db.session.commit()
        self.assertIn("deactivated", self.assign(order).get_data(as_text=True))
        self.assertIsNone(self.delivery())

    def test_a_partner_can_hold_only_a_few_active_deliveries(self):
        limit = delivery_service.MAX_ACTIVE_DELIVERIES
        # give the partner `limit` deliveries that are already in progress
        from app.models.order import Order, OrderItem
        for n in range(limit):
            o = Order(customer_id=User.query.filter_by(email="cathy@example.com").one().id,
                      shop_id=self.shop_a.id, delivery_address="Home, Town",
                      total_amount=Decimal("10.00"), status="ready_for_pickup")
            o.items.append(OrderItem(product_id=self.apple.id, quantity=1, price_at_purchase=Decimal("10.00")))
            db.session.add(o)
            db.session.commit()
            db.session.add(Delivery(order_id=o.id, delivery_partner_id=self.partner.id, status="accepted"))
            db.session.commit()
        extra = self.ready_order()
        page = self.assign(extra).get_data(as_text=True)
        self.assertIn(f"already has {limit} active deliveries", page)
        self.assertEqual(delivery_service.active_count(self.partner.id), limit)
        other, _client = self.new_partner("dev@example.com", "Dev Dasher")
        self.assign(extra, other)                                       # someone free can take it
        self.assertEqual(self.delivery().delivery_partner_id, other.id)

    def test_reassign_only_until_the_partner_accepts(self):
        order = self.ready_order()
        self.assign(order)
        other, other_client = self.new_partner("dev@example.com", "Dev Dasher")
        self.assertIn("Change delivery partner", self.page(self.admin, f"/admin/orders/{order.id}"))
        self.assertIn("already assigned", self.assign(order, self.partner).get_data(as_text=True))

        self.assertIn("is assigned to Dev Dasher", self.assign(order, other).get_data(as_text=True))
        self.assertEqual(self.delivery().delivery_partner_id, other.id)
        self.assertEqual(self.rider.get(f"/delivery/tasks/{self.delivery().id}").status_code, 404)  # old partner is out
        self.assertEqual(other_client.get(f"/delivery/tasks/{self.delivery().id}").status_code, 200)

        self.step(self.delivery(), "accept", client=other_client)
        page = self.assign(order, self.partner).get_data(as_text=True)
        self.assertIn("already accepted", page)
        self.assertEqual(self.delivery().delivery_partner_id, other.id)
        self.assertIn("assignment is locked", self.page(self.admin, f"/admin/orders/{order.id}"))

    def test_partners_page_shows_workload(self):
        order = self.ready_order()
        self.assign(order)
        page = self.page(self.admin, "/admin/delivery-partners")
        self.assertIn("Ravi Rider", page)
        self.assertIn(f"1 / {delivery_service.MAX_ACTIVE_DELIVERIES}", page)
        rows = admin_service.partner_rows()
        self.assertEqual((rows[0]["active"], rows[0]["delivered"]), (1, 0))


class AdminCsrfTests(StaffTestCase):
    base_config = CsrfEnabledConfig

    def test_admin_posts_need_a_token(self):
        with self.admin.session_transaction() as session:
            session["_user_id"] = str(User.query.filter_by(email="admin@example.com").one().id)
            session["_fresh"] = True
        for path in ("/admin/categories", f"/admin/shops/{self.shop_a.id}/reject",
                     f"/admin/users/{self.partner.id}/deactivate", "/admin/orders/1/assign"):
            self.assertEqual(self.admin.post(path, data={"name": "X", "reason": "no reason"}).status_code, 400, path)
        self.assertTrue(User.query.filter_by(email="rider@example.com").one().is_active)


if __name__ == "__main__":
    unittest.main()
