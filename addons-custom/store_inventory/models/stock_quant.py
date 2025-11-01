from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class StockQuant(models.Model):
    _inherit = "stock.quant"

    store_batch_id = fields.Many2one(
        "store.inventory.batch",
        string="陈化批次",
        check_company=True,
        help="标记该库存明细归属的陈化批次，用于批次库存与陈化看板统计。",
    )

    @api.constrains("store_batch_id", "product_id", "company_id")
    def _check_store_batch_consistency(self):
        for quant in self:
            batch = quant.store_batch_id
            if not batch:
                continue
            if quant.product_id and batch.product_id != quant.product_id:
                raise ValidationError(_("陈化批次与库存量的商品不一致。"))
            if quant.company_id and batch.company_id != quant.company_id:
                raise ValidationError(_("陈化批次与库存量的公司不一致。"))

    @api.model
    def _update_available_quantity(
        self,
        product_id,
        location_id,
        quantity,
        lot_id=None,
        package_id=None,
        owner_id=None,
        strict=False,
    ):
        res = super()._update_available_quantity(
            product_id,
            location_id,
            quantity,
            lot_id=lot_id,
            package_id=package_id,
            owner_id=owner_id,
            strict=strict,
        )
        batch_id = self.env.context.get("store_inventory_batch_id")
        if batch_id:
            quants = self._gather(
                product=product_id,
                location=location_id,
                lot_id=lot_id,
                package_id=package_id,
                owner_id=owner_id,
                strict=False,
            )
            if quants:
                quants.sudo().write({"store_batch_id": batch_id})
        return res
