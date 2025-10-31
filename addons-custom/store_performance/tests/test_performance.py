from odoo import Command, fields
from odoo.tests import common, tagged


@tagged('post_install', '-at_install', 'store_performance')
class TestStorePerformance(common.TransactionCase):
    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.partner = self.env["res.partner"].create({"name": "业绩测试客户"})
        self.product = self.env["product.product"].create(
            {
                "name": "业绩测试商品",
                "list_price": 300.0,
                "standard_price": 100.0,
                "type": "consu",
            }
        )
        self.employee = self.env["hr.employee"].create(
            {
                "name": "业绩员工",
                "company_id": self.company.id,
            }
        )
        self.rule = self.env["store.commission.rule"].create(
            {
                "name": "业绩测试规则",
                "company_id": self.company.id,
                "rule_type": "product",
                "rate_type": "percent",
                "rate_value": 5.0,
                "scope_type": "employee",
                "employee_ids": [Command.set(self.employee.ids)],
                "product_ids": [Command.set(self.product.ids)],
                "state": "active",
                "start_date": fields.Date.today(),
            }
        )
        self.rule.action_activate()

    def test_performance_update_from_commission(self):
        order = self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "responsible_employee_id": self.employee.id,
                "order_line": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": 1.0,
                            "price_unit": 300.0,
                            "participant_employee_ids": [Command.set(self.employee.ids)],
                        }
                    )
                ],
            }
        )
        order.action_confirm()
        log = order.commission_log_ids
        log.action_confirm()

        record = self.env["store.performance.record"].search([
            ("employee_id", "=", self.employee.id),
            ("period_type", "=", "month"),
        ], limit=1)
        self.assertTrue(record, "确认提成后应生成业绩记录。")
        self.assertAlmostEqual(record.commission_amount, log.commission_amount, 2)

        log.action_refund(reason="测试退款")
        record.invalidate_recordset(["commission_amount", "sales_amount"])
        self.assertAlmostEqual(record.commission_amount, 0.0, 2, "回滚后提成应归零。")
        self.assertAlmostEqual(record.sales_amount, 0.0, 2, "回滚后销售额应归零。")
