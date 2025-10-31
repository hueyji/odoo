from odoo import fields
from odoo.tests import common


class TestSupplierMetrics(common.TransactionCase):
    def setUp(self):
        super().setUp()
        self.supplier_partner = self.env["res.partner"].create(
            {
                "name": "阿尔法酒业",
                "is_company": True,
                "supplier_rank": 5,
            }
        )
        self.supplier = self.env["store.supplier"].create(
            {
                "name": "阿尔法酒业",
                "partner_id": self.supplier_partner.id,
                "rating": "good",
                "delivery_lead_days": 6,
            }
        )
        template = self.env["product.template"].create(
            {
                "name": "波本威士忌",
                "uom_id": self.env.ref("uom.product_uom_unit").id,
                "uom_po_id": self.env.ref("uom.product_uom_unit").id,
            }
        )
        self.product = template.product_variant_id
        self.batch = self.env["store.inventory.batch"].create(
            {
                "product_id": self.product.id,
                "qty_initial": 0,
                "qty_available": 0,
                "aging_start_date": fields.Date.today(),
                "purchase_price": 180,
                "supplier_id": self.supplier_partner.id,
                "supplier_record_id": self.supplier.id,
            }
        )

    def _create_incoming_move(self, quantity, price):
        move = self.env["store.inventory.move"].create(
            {
                "batch_id": self.batch.id,
                "move_type": "incoming",
                "quantity": quantity,
                "unit_price": price,
            }
        )
        move.with_context(skip_approval_activity=True).action_submit()
        move.with_context(bypass_inventory_approval=True).action_approve()
        return move

    def test_purchase_metrics_aggregation(self):
        self._create_incoming_move(5, 200)
        self._create_incoming_move(3, 220)
        self.assertEqual(self.supplier.total_purchase_qty, 8)
        self.assertAlmostEqual(self.supplier.total_purchase_amount, 5 * 200 + 3 * 220)
        self.assertAlmostEqual(self.supplier.average_purchase_price, (5 * 200 + 3 * 220) / 8)
        self.assertEqual(self.supplier.purchase_order_count, 2)

    def test_kpi_score_considers_rating_and_lead_time(self):
        self._create_incoming_move(4, 190)
        _ = self.supplier.total_purchase_qty
        self.supplier.delivery_lead_days = 5
        self.supplier.rating = "excellent"
        self.supplier._compute_kpi_score()
        self.assertGreaterEqual(self.supplier.kpi_score, 90)
        self.supplier.is_blacklisted = True
        self.supplier._compute_kpi_score()
        self.assertEqual(self.supplier.kpi_score, 0)
