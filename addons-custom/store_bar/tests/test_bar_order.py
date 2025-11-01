from datetime import date

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestStoreBarOrder(TransactionCase):
    def setUp(self):
        super().setUp()
        self.company = self.env.ref("base.main_company")
        self.product_cigar = self.env["product.product"].create(
            {
                "name": "测试雪茄",
                "type": "product",
                "list_price": 120.0,
                "standard_price": 60.0,
            }
        )
        self.product_whisky = self.env["product.product"].create(
            {
                "name": "测试威士忌",
                "type": "product",
                "list_price": 90.0,
                "standard_price": 40.0,
            }
        )

        self.batch_cigar = self.env["store.inventory.batch"].create(
            {
                "name": "TEST-CIGAR",
                "company_id": self.company.id,
                "product_id": self.product_cigar.id,
                "product_uom_id": self.product_cigar.uom_id.id,
                "qty_initial": 40,
                "aging_start_date": date(2025, 1, 1),
                "purchase_price": 55.0,
            }
        )
        self.batch_whisky = self.env["store.inventory.batch"].create(
            {
                "name": "TEST-WHISKY",
                "company_id": self.company.id,
                "product_id": self.product_whisky.id,
                "product_uom_id": self.product_whisky.uom_id.id,
                "qty_initial": 60,
                "aging_start_date": date(2025, 3, 1),
                "purchase_price": 35.0,
            }
        )

        stock_location = self.env.ref("stock.stock_location_stock")
        self.env["stock.quant"].create(
            {
                "company_id": self.company.id,
                "product_id": self.product_cigar.id,
                "location_id": stock_location.id,
                "quantity": 40,
                "store_batch_id": self.batch_cigar.id,
            }
        )
        self.env["stock.quant"].create(
            {
                "company_id": self.company.id,
                "product_id": self.product_whisky.id,
                "location_id": stock_location.id,
                "quantity": 60,
                "store_batch_id": self.batch_whisky.id,
            }
        )

        self.table = self.env["store.bar.table"].create(
            {
                "name": "测试桌台",
                "company_id": self.company.id,
                "capacity": 2,
            }
        )
        self.employee = self.env["hr.employee"].create(
            {
                "name": "测试调酒师",
                "company_id": self.company.id,
            }
        )
        self.member = self.env["res.partner"].create(
            {
                "name": "测试会员",
                "phone": "13900009999",
                "company_id": self.company.id,
            }
        )

    def _create_order(self, qty_cigar=2, qty_whisky=2):
        order = self.env["store.bar.order"].create(
            {
                "table_id": self.table.id,
                "employee_id": self.employee.id,
                "member_id": self.member.id,
                "order_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product_cigar.id,
                            "batch_id": self.batch_cigar.id,
                            "quantity": qty_cigar,
                            "price_unit": 110.0,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "product_id": self.product_whisky.id,
                            "batch_id": self.batch_whisky.id,
                            "quantity": qty_whisky,
                            "price_unit": 80.0,
                            "is_combo_component": True,
                        },
                    ),
                ],
            }
        )
        return order

    def test_order_lock_and_release(self):
        order = self._create_order()
        order.action_lock()
        self.assertEqual(order.state, "locked")
        self.assertEqual(order.table_id.state, "occupied")
        self.assertEqual(order.table_id.current_order_id, order)

        order.action_request_billing()
        self.assertEqual(order.state, "billing")
        self.assertEqual(order.table_id.state, "billing")

        order.action_set_billed()
        self.assertEqual(order.state, "billed")
        self.assertEqual(order.table_id.state, "free")
        self.assertFalse(order.table_id.current_order_id)

    def test_inventory_reservation_blocks_over_order(self):
        first_order = self._create_order(qty_cigar=2, qty_whisky=2)
        first_order.action_lock()

        second_order = self._create_order(qty_cigar=39, qty_whisky=1)
        with self.assertRaises(ValidationError):
            second_order.action_lock()

        # 减少数量后可成功锁单
        second_order.order_line_ids.filtered(lambda l: l.product_id == self.product_cigar)[0].write(
            {"quantity": 10}
        )
        second_order.action_lock()
        self.assertEqual(second_order.state, "locked")
