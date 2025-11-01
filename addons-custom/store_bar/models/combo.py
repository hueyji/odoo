from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class StoreCombo(models.Model):
    _name = "store.combo"
    _description = "套餐组合"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name"

    name = fields.Char(string="套餐名称", required=True, tracking=True)
    company_id = fields.Many2one(
        "res.company",
        string="所属公司",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    list_price = fields.Monetary(
        string="套餐售价",
        currency_field="currency_id",
        required=True,
        default=0.0,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="币种",
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    item_ids = fields.One2many(
        "store.combo.line",
        "combo_id",
        string="套餐明细",
        copy=True,
    )
    active = fields.Boolean(default=True, string="启用")

    @api.constrains("item_ids")
    def _check_items(self):
        for combo in self:
            if not combo.item_ids:
                raise ValidationError(_("套餐至少需要包含一个商品。"))


class StoreComboLine(models.Model):
    _name = "store.combo.line"
    _description = "套餐商品"
    _order = "sequence, id"

    combo_id = fields.Many2one(
        "store.combo",
        string="套餐",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(default=10)
    product_id = fields.Many2one(
        "product.product",
        string="商品",
        required=True,
        domain=[("sale_ok", "=", True), ("type", "!=", "service")],
    )
    quantity = fields.Float(
        string="数量",
        default=1.0,
        required=True,
        digits="Product Unit of Measure",
    )
