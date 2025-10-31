from odoo import fields
from odoo.tests import common


class TestInventoryTransfer(common.TransactionCase):
    def setUp(self):
        super().setUp()
        template = self.env["product.template"].create(
            {
                "name": "陈化雪茄",
                "uom_id": self.env.ref("uom.product_uom_unit").id,
                "uom_po_id": self.env.ref("uom.product_uom_unit").id,
            }
        )
        self.product = template.product_variant_id
        self.source_batch = self.env["store.inventory.batch"].create(
            {
                "product_id": self.product.id,
                "qty_initial": 10,
                "aging_start_date": fields.Date.today(),
                "purchase_price": 120,
            }
        )
        self.target_company = self.env["res.company"].create(
            {
                "name": "测试门店 B",
                "currency_id": self.env.company.currency_id.id,
            }
        )
        self.env.user.company_ids |= self.target_company
        self.link_group = self.env["store.link.group"].create(
            {
                "name": "测试互通组",
                "member_company_ids": [(6, 0, [self.env.company.id, self.target_company.id])],
                "share_inventory": True,
                "state": "active",
            }
        )

    def test_transfer_creates_moves_and_batch(self):
        Transfer = self.env["store.inventory.transfer"].with_user(self.env.user)
        transfer = Transfer.create(
            {
                "batch_id": self.source_batch.id,
                "target_company_id": self.target_company.id,
                "qty": 4,
                "unit_price": 130,
                "reason": "互通补货",
            }
        )
        transfer.action_submit()
        transfer.with_context(bypass_inventory_approval=True, skip_approval_activity=True).action_approve()

        self.assertEqual(transfer.state, "done")
        self.assertTrue(transfer.out_move_id)
        self.assertTrue(transfer.in_move_id)
        self.assertTrue(transfer.new_batch_id)
        self.assertEqual(transfer.out_move_id.move_type, "transfer_out")
        self.assertEqual(transfer.in_move_id.move_type, "transfer_in")
        self.assertEqual(transfer.new_batch_id.company_id, self.target_company)
        self.assertEqual(transfer.new_batch_id.qty_available, 4)
