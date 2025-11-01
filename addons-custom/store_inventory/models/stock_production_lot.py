from odoo import fields, models


class StockProductionLot(models.Model):
    _inherit = "stock.lot"

    store_batch_id = fields.Many2one(
        "store.inventory.batch",
        string="陈化批次",
        check_company=True,
        help="与陈化批次建立委派关系，便于追溯批次库存。",
    )
