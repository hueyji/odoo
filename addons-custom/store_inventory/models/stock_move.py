from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class StockMove(models.Model):
    _inherit = "stock.move"

    store_batch_id = fields.Many2one(
        "store.inventory.batch",
        string="陈化批次",
        check_company=True,
        help="指向本次库存移动对应的陈化批次，确保库存扣减与陈化追踪一致。",
    )
    store_reservation_token = fields.Char(
        string="库存锁定令牌",
        help="用于互通调拨与 Team D 结算的锁定标识。",
    )
    store_unit_cost = fields.Monetary(
        string="批次成本单价",
        currency_field="store_cost_currency_id",
        help="记录批次对应的成本单价，供财务补差接口使用。",
    )
    store_cost_currency_id = fields.Many2one(
        "res.currency",
        string="批次币种",
        related="company_id.currency_id",
        store=True,
        readonly=True,
    )

    @api.constrains("store_batch_id", "product_id", "company_id")
    def _check_store_batch_constraints(self):
        for move in self:
            batch = move.store_batch_id
            if not batch:
                continue
            if move.product_id and batch.product_id != move.product_id:
                raise ValidationError(_("陈化批次与库存移动的商品不一致。"))
            if move.company_id and batch.company_id != move.company_id:
                raise ValidationError(_("陈化批次与库存移动的公司不一致。"))

    def action_confirm(self):
        res = super().action_confirm()
        for move in self:
            if move.store_batch_id and not move.store_unit_cost:
                move.store_unit_cost = move.store_batch_id.purchase_price
            if move.store_reservation_token:
                continue
            move.store_reservation_token = move.origin or move.reference or move.store_batch_id.name
        return res
