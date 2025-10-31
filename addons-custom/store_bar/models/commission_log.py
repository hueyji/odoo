from odoo import fields, models


class StoreCommissionLog(models.Model):
    _inherit = "store.commission.log"

    bar_order_id = fields.Many2one(
        "store.bar.order",
        string="吧台订单",
        index=True,
        ondelete="set null",
        copy=False,
    )
