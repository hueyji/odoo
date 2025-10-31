from odoo import Command, fields
from odoo.tests import common, tagged


@tagged('post_install', '-at_install', 'store_commission')
class TestStoreCommission(common.TransactionCase):
    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.partner = self.env["res.partner"].create(
            {"name": "提成测试客户", "company_type": "person"}
        )
        self.product = self.env["product.product"].create(
            {
                "name": "提成测试商品",
                "list_price": 500.0,
                "standard_price": 200.0,
                "type": "consu",
            }
        )
        self.job = self.env["hr.job"].create({"name": "测试调酒师"})
        self.employee = self.env["hr.employee"].create(
            {
                "name": "测试员工",
                "company_id": self.company.id,
                "job_id": self.job.id,
            }
        )
        self.rule = self.env["store.commission.rule"].create(
            {
                "name": "测试提成规则",
                "company_id": self.company.id,
                "rule_type": "product",
                "rate_type": "percent",
                "rate_value": 10.0,
                "scope_type": "job",
                "job_ids": [Command.set(self.job.ids)],
                "product_ids": [Command.set(self.product.ids)],
                "state": "active",
                "start_date": fields.Date.today(),
            }
        )
        self.rule.action_activate()

    def test_commission_generation_and_refund(self):
        order = self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "responsible_employee_id": self.employee.id,
                "order_line": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": 2.0,
                            "price_unit": 500.0,
                            "participant_employee_ids": [Command.set(self.employee.ids)],
                        }
                    )
                ],
            }
        )
        order.action_confirm()
        logs = order.commission_log_ids
        self.assertEqual(len(logs), 1, "确认订单后应生成一条提成日志。")
        expected_amount = logs.base_amount * 0.10
        self.assertAlmostEqual(logs.commission_amount, expected_amount, 2, "提成金额应为销售额的 10%。")

        logs.action_confirm()
        invoice = order._create_invoices()
        invoice.action_post()
        refund_moves = invoice._reverse_moves(
            default_values_list=[{"move_type": "out_refund"}],
            cancel=False,
        )
        refund_moves.action_post()

        order.invalidate_recordset(["commission_log_ids"])
        logs_after_refund = order.commission_log_ids
        self.assertTrue(any(log.state == "refunded" for log in logs_after_refund), "退款后原提成应标记为已回滚。")
        negative_logs = logs_after_refund.filtered(lambda l: l.is_refund)
        self.assertTrue(negative_logs, "退款后应产生冲减提成日志。")
        self.assertLess(negative_logs[0].commission_amount, 0, "冲减提成金额应为负数。")
