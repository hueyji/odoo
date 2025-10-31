from odoo import fields, models


class StockMove(models.Model):
    _inherit = "stock.move"

    batch_id = fields.Many2one(
        "store.inventory.batch",
        string="库存批次",
        check_company=True,
        help="记录此移动关联的库存批次。",
    )


class StockQuant(models.Model):
    _inherit = "stock.quant"

    batch_id = fields.Many2one(
        "store.inventory.batch",
        string="库存批次",
        check_company=True,
        help="该库存数量对应的批次来源。",
    )
