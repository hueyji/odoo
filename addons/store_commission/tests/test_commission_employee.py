from odoo import Command
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestCommissionEmployee(TransactionCase):
    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.partner = self.env["res.partner"].create(
            {
                "name": "测试客户A",
                "company_id": self.company.id,
            }
        )
        self.employee = self.env["hr.employee"].create(
            {
                "name": "责任员工",
                "company_id": self.company.id,
                "user_id": self.env.user.id,
            }
        )

    def test_sale_order_default_employee(self):
        order = self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "company_id": self.company.id,
            }
        )
        self.assertEqual(order.commission_employee_id, self.employee, "应默认绑定当前用户的关联员工")
        self.assertEqual(order.user_id, self.employee.user_id, "责任员工变更后应同步销售人员")

    def test_sale_order_change_user_sync_employee(self):
        target_user = (
            self.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "提成员工",
                    "login": "commission.test@example.com",
                    "email": "commission.test@example.com",
                    "company_id": self.company.id,
                    "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
                }
            )
        )
        target_employee = self.env["hr.employee"].create(
            {
                "name": "提成员工",
                "company_id": self.company.id,
                "user_id": target_user.id,
            }
        )
        order = self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "company_id": self.company.id,
            }
        )
        order.write({"user_id": target_user.id})
        self.assertEqual(order.commission_employee_id, target_employee, "更换销售人员应同步到对应责任员工")

    def test_sale_order_without_employee_raise(self):
        user_without_employee = (
            self.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "临时用户",
                    "login": "temp.user@example.com",
                    "email": "temp.user@example.com",
                    "company_id": self.company.id,
                    "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
                }
            )
        )
        with self.assertRaises(UserError):
            self.env["sale.order"].create(
                {
                    "partner_id": self.partner.id,
                    "company_id": self.company.id,
                    "user_id": user_without_employee.id,
                }
            )

    def test_sale_order_commission_log_creation_and_cancel(self):
        product = self.env["product.product"].create(
            {
                "name": "测试雪茄",
                "type": "consu",
                "list_price": 200.0,
                "categ_id": self.env.ref("product.product_category_all").id,
            }
        )
        rule = self.env["store.commission.rule"].create(
            {
                "name": "雪茄提成 5%",
                "code": "RULE-001",
                "rule_type": "product",
                "rate_type": "percent",
                "rate_value": 5.0,
                "state": "active",
                "applicable_employee_ids": [Command.link(self.employee.id)],
                "target_product_ids": [Command.link(product.id)],
            }
        )
        order = self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "company_id": self.company.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": product.id,
                            "product_uom_qty": 10,
                            "price_unit": 180,
                        },
                    )
                ],
            }
        )
        order.action_confirm()
        log = self.env["store.commission.log"].search(
            [("sale_order_id", "=", order.id), ("rule_id", "=", rule.id)], limit=1
        )
        self.assertTrue(log, "确认后应生成提成日志")
        self.assertAlmostEqual(log.amount, 10 * 180 * 0.05, places=2)
        self.assertEqual(log.state, "pending")
        order.action_cancel()
        self.assertEqual(log.state, "cancelled", "取消订单应回滚提成日志")

    def test_order_amount_rule_percent(self):
        rule = self.env["store.commission.rule"].create(
            {
                "name": "整单提成 3%",
                "code": "RULE-ORD-01",
                "rule_type": "order_amount",
                "rate_type": "percent",
                "rate_value": 3.0,
                "state": "active",
                "applicable_employee_ids": [Command.link(self.employee.id)],
            }
        )
        order = self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "company_id": self.company.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "name": "整单提成商品",
                            "product_id": self.env.ref("product.product_product_3").id,
                            "product_uom_qty": 5,
                            "price_unit": 100,
                        },
                    )
                ],
            }
        )
        order.action_confirm()
        log = self.env["store.commission.log"].search(
            [("sale_order_id", "=", order.id), ("rule_id", "=", rule.id)], limit=1
        )
        self.assertTrue(log)
        self.assertAlmostEqual(log.amount, order.amount_total * 0.03, places=2)
