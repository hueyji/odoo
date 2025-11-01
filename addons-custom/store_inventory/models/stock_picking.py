from odoo import api, fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    store_batch_ids = fields.Many2many(
        "store.inventory.batch",
        string="陈化批次",
        compute="_compute_store_batch_ids",
        compute_sudo=True,
        help="拣货单涉及的陈化批次集合，来源于拣货行上的批次选择。",
    )
    store_batch_count = fields.Integer(
        string="批次数量",
        compute="_compute_store_batch_ids",
        compute_sudo=True,
    )

    @api.depends("move_ids.store_batch_id")
    def _compute_store_batch_ids(self):
        for picking in self:
            batches = picking.move_ids.mapped("store_batch_id")
            picking.store_batch_ids = batches
            picking.store_batch_count = len(batches)
