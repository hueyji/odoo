from odoo.tests import TransactionCase


class TestStoreBar(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.currency = cls.company.currency_id

        cls.employee = cls.env["hr.employee"].create(
            {
                "name": "示例调酒师",
                "company_id": cls.company.id,
            }
        )

        cls.table = cls.env["store.bar.table"].create(
            {
                "name": "测试桌台",
                "company_id": cls.company.id,
                "capacity": 4,
            }
        )

        cls.product_template = cls.env["product.template"].create(
            {
                "name": "单杯威士忌",
                "type": "product",
                "list_price": 120.0,
                "standard_price": 80.0,
                "uom_id": cls.env.ref("uom.product_uom_unit").id,
                "uom_po_id": cls.env.ref("uom.product_uom_unit").id,
                "company_id": cls.company.id,
            }
        )
        cls.product = cls.product_template.product_variant_id

        cls.batch = cls.env["store.inventory.batch"].create(
            {
                "product_id": cls.product.id,
                "qty_initial": 100,
                "qty_available": 100,
                "purchase_price": 80,
                "currency_id": cls.currency.id,
                "aging_start_date": "2024-01-01",
                "state": "in_stock",
                "company_id": cls.company.id,
            }
        )

        cls.member = cls.env["res.partner"].create(
            {
                "name": "测试会员",
                "member_balance": 1000,
                "member_balance_currency_id": cls.currency.id,
            }
        )

        cls.channel_stored = cls.env["store.finance.channel"].create(
            {
                "name": "储值支付",
                "code": "BAR-STORED",
                "channel_type": "stored_value",
                "company_id": cls.company.id,
                "sequence": 1,
            }
        )

        cls.rule = cls.env["store.commission.rule"].create(
            {
                "name": "单品10%提成",
                "rule_type": "product",
                "rate_type": "percent",
                "rate_value": 10,
                "scope_type": "all",
                "company_id": cls.company.id,
                "state": "draft",
                "active": True,
                "product_ids": [(6, 0, [cls.product.id])],
            }
        )
        cls.rule.action_activate()

    def test_order_full_flow(self):
        order = self.env["store.bar.order"].create(
            {
                "table_id": self.table.id,
                "company_id": self.company.id,
                "responsible_employee_id": self.employee.id,
                "assistant_employee_ids": [(6, 0, [self.employee.id])],
                "member_id": self.member.id,
                "payment_channel_id": self.channel_stored.id,
                "amount_service": 20,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "batch_id": self.batch.id,
                            "quantity": 2,
                            "price_unit": 150,
                            "requires_preparation": True,
                            "participant_employee_ids": [(6, 0, [self.employee.id])],
                        },
                    )
                ],
            }
        )

        order.action_confirm()
        self.assertEqual(order.state, "preparing")
        self.assertEqual(order.table_id.current_order_id, order)
        self.assertTrue(order.task_ids)
        self.assertGreater(order.task_ids[0].expected_commission_amount, 0)

        order.task_ids.action_done()
        order.action_set_serving()
        order.action_request_bill()
        self.assertEqual(order.state, "billing")

        initial_balance = self.member.member_balance
        initial_qty = self.batch.qty_available
        order.action_close()

        self.assertEqual(order.state, "done")
        self.assertTrue(order.inventory_move_ids)
        self.assertEqual(self.batch.qty_available, initial_qty - 2)
        self.assertTrue(order.transaction_id)
        self.assertEqual(order.transaction_id.state, "confirmed")

        expected_total = self.currency.round(order.amount_total)
        self.assertEqual(self.member.member_balance, self.currency.round(initial_balance - expected_total))

        self.assertTrue(order.commission_log_ids)
        commission_amount = sum(order.commission_log_ids.mapped("commission_amount"))
        self.assertAlmostEqual(commission_amount, order.amount_subtotal * 0.1, places=2)

        self.assertEqual(order.table_id.state, "available")
