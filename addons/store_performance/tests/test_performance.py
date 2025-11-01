from odoo import Command
from odoo.tests.common import TransactionCase


class TestStorePerformance(TransactionCase):
    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.partner = self.env["res.partner"].create(
            {
                "name": "业绩客户",
                "company_id": self.company.id,
            }
        )
        self.employee = self.env["hr.employee"].create(
            {
                "name": "业绩员工",
                "company_id": self.company.id,
                "user_id": self.env.user.id,
            }
        )
        self.product = self.env["product.product"].create(
            {
                "name": "业绩测试雪茄",
                "type": "consu",
                "list_price": 300,
                "categ_id": self.env.ref("product.product_category_all").id,
            }
        )
        self.rule = self.env["store.commission.rule"].create(
            {
                "name": "业绩提成规则",
                "code": "PERF-RULE",
                "rule_type": "product",
                "rate_type": "percent",
                "rate_value": 10.0,
                "state": "active",
                "applicable_employee_ids": [Command.link(self.employee.id)],
                "target_product_ids": [Command.link(self.product.id)],
            }
        )

    def _create_sale_order(self):
        order = self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "company_id": self.company.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": 4,
                            "price_unit": 280,
                        },
                    )
                ],
            }
        )
        return order

    def test_performance_updates_with_commission_log(self):
        order = self._create_sale_order()
        order.action_confirm()

        log = self.env["store.commission.log"].search(
            [
                ("sale_order_id", "=", order.id),
                ("rule_id", "=", self.rule.id),
            ],
            limit=1,
        )
        self.assertTrue(log)

        period_start = log.trigger_datetime.date().replace(day=1)
        record = self.env["store.performance.record"].search(
            [
                ("employee_id", "=", self.employee.id),
                ("period_type", "=", "monthly"),
                ("period_start", "=", period_start),
            ],
            limit=1,
        )
        self.assertTrue(record, "确认后应生成业绩记录")
        self.assertAlmostEqual(record.pending_commission_amount, log.amount, places=2)
        self.assertAlmostEqual(record.pending_sales_amount, log.base_amount, places=2)

        log.action_confirm()
        record.invalidate_cache()
        self.assertAlmostEqual(record.confirmed_commission_amount, log.amount, places=2)
        self.assertAlmostEqual(record.confirmed_sales_amount, log.base_amount, places=2)
        self.assertEqual(record.pending_commission_amount, 0.0)

        target = self.env["store.performance.target"].create(
            {
                "employee_id": self.employee.id,
                "company_id": self.company.id,
                "period_type": "monthly",
                "period_start": record.period_start,
                "target_amount": 5000,
            }
        )
        record.invalidate_cache()
        self.assertEqual(record.target_amount, target.target_amount)
