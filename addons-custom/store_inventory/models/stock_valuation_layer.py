from odoo import fields, models


class StockValuationLayer(models.Model):
    _inherit = "stock.valuation.layer"

    store_batch_id = fields.Many2one(
        "store.inventory.batch",
        string="陈化批次",
        index=True,
        help="用于财务补差与库存批次追溯的互通字段。",
    )
    store_reservation_token = fields.Char(
        string="库存锁定令牌",
        help="用于 Team D 清算接口的调拨/批次对应关系。",
    )
    store_unit_cost = fields.Monetary(
        string="批次成本单价",
        currency_field="currency_id",
        help="记录批次在生成估值时的成本单价，用于补差和审计。",
    )
