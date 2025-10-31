from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import common


class TestInventoryBatch(common.TransactionCase):
    def setUp(self):
        super().setUp()
        template = self.env["product.template"].create(
            {
                "name": "测试雪茄",
                "uom_id": self.env.ref("uom.product_uom_unit").id,
                "uom_po_id": self.env.ref("uom.product_uom_unit").id,
            }
        )
        self.product = template.product_variant_id
        self.supplier = self.env["res.partner"].create(
            {
                "name": "示例供应商",
                "is_company": True,
            }
        )

    def test_batch_sequence_and_defaults(self):
        """创建批次时应自动带出编号与默认库存。"""
        start_date = date.today() - relativedelta(days=10)
        batch = self.env["store.inventory.batch"].create(
            {
                "product_id": self.product.id,
                "supplier_id": self.supplier.id,
                "qty_initial": 10,
                "aging_start_date": start_date,
                "purchase_price": 120,
            }
        )
        self.assertTrue(batch.name.startswith("BATCH"))
        self.assertEqual(batch.qty_available, 10)
        self.assertEqual(batch.state, "in_stock")
        self.assertEqual(batch.aging_stage, "lt_30")

    def test_batch_aging_stage_progression(self):
        """陈化天数应根据开始日期正确分层。"""
        start_date = date.today() - relativedelta(days=95)
        batch = self.env["store.inventory.batch"].create(
            {
                "product_id": self.product.id,
                "qty_initial": 5,
                "aging_start_date": start_date,
                "purchase_price": 200,
            }
        )
        self.assertGreaterEqual(batch.aging_days, 95)
        self.assertEqual(batch.aging_stage, "91_180")

    def test_batch_qty_validation(self):
        """初始数量必须大于 0。"""
        with self.assertRaises(ValidationError):
            self.env["store.inventory.batch"].create(
                {
                    "product_id": self.product.id,
                    "qty_initial": 0,
                    "aging_start_date": fields.Date.today(),
                    "purchase_price": 50,
                }
            )

    def test_batch_attention_toggle_and_metrics(self):
        batch = self.env["store.inventory.batch"].create(
            {
                "product_id": self.product.id,
                "qty_initial": 3,
                "aging_start_date": fields.Date.today(),
                "purchase_price": 80,
            }
        )
        self.assertFalse(batch.attention_flag)
        batch.action_toggle_attention()
        self.assertTrue(batch.attention_flag)

        metrics = self.env["store.inventory.batch"].action_get_aging_metrics()
        stages = {item["stage"]: item for item in metrics["metrics"]}
        self.assertIn(batch.aging_stage, stages)
        self.assertGreaterEqual(stages[batch.aging_stage]["count"], 1)

    def test_cron_updates_aging(self):
        batch = self.env["store.inventory.batch"].create(
            {
                "product_id": self.product.id,
                "qty_initial": 2,
                "aging_start_date": fields.Date.today(),
                "purchase_price": 60,
            }
        )
        batch.aging_start_date = fields.Date.today() - relativedelta(days=40)
        self.env["store.inventory.batch"].cron_update_aging()
        batch.refresh()
        self.assertEqual(batch.aging_stage, "31_90")
