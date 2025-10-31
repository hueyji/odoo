from odoo import fields
from odoo.tests import common


class TestInventoryMove(common.TransactionCase):
    def setUp(self):
        super().setUp()
        template = self.env["product.template"].create(
            {
                "name": "测试威士忌",
                "uom_id": self.env.ref("uom.product_uom_unit").id,
                "uom_po_id": self.env.ref("uom.product_uom_unit").id,
            }
        )
        self.product = template.product_variant_id
        self.batch = self.env["store.inventory.batch"].create(
            {
                "product_id": self.product.id,
                "qty_initial": 1,
                "aging_start_date": fields.Date.today(),
                "purchase_price": 200,
            }
        )

    def test_confirm_incoming_move_updates_inventory_and_finance(self):
        move = self.env["store.inventory.move"].create(
            {
                "batch_id": self.batch.id,
                "quantity": 5,
                "unit_price": 300,
                "move_type": "incoming",
                "note": "测试入库",
            }
        )
        move.action_submit()
        move.with_context(bypass_inventory_approval=True).action_approve()
        self.assertEqual(move.state, "done")
        self.assertEqual(self.batch.qty_available, 6)
        self.assertEqual(move.transaction_id.transaction_type, "purchase")
        self.assertEqual(move.transaction_id.state, "confirmed")
        self.assertEqual(move.transaction_id.amount, -1500)
        self.assertTrue(move.transaction_id.name.startswith("TRX"))
