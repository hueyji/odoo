from odoo import api, fields, models


class StoreInventoryBatch(models.Model):
    _inherit = "store.inventory.batch"

    supplier_record_id = fields.Many2one(
        "store.supplier",
        string="供应商档案",
        domain="[('company_id', '=', company_id)]",
        tracking=True,
        help="与门店供应商档案建立关联，便于统计采购表现。",
    )

    @api.onchange("supplier_record_id")
    def _onchange_supplier_record_id(self):
        for record in self:
            if record.supplier_record_id:
                record.supplier_id = record.supplier_record_id.partner_id

    def write(self, vals):
        res = super().write(vals)
        if "supplier_record_id" in vals:
            for record in self:
                if record.supplier_record_id and record.supplier_record_id.partner_id:
                    record.supplier_id = record.supplier_record_id.partner_id
        return res
