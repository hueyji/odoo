from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_is_zero


class StoreBarOrderLine(models.Model):
    _name = "store.bar.order.line"
    _description = "吧台订单明细"
    _order = "sequence, id"

    order_id = fields.Many2one(
        "store.bar.order",
        string="订单",
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
    product_uom_id = fields.Many2one(
        "uom.uom",
        string="计量单位",
        required=True,
    )
    quantity = fields.Float(
        string="数量",
        required=True,
        default=1.0,
        digits="Product Unit of Measure",
    )
    price_unit = fields.Monetary(
        string="单价",
        required=True,
        currency_field="currency_id",
    )
    currency_id = fields.Many2one(
        related="order_id.currency_id",
        store=True,
        string="币种",
        readonly=True,
    )
    company_id = fields.Many2one(
        related="order_id.company_id",
        store=True,
        string="所属公司",
        readonly=True,
    )
    batch_id = fields.Many2one(
        "store.inventory.batch",
        string="库存批次",
        domain="[('product_id', '=', product_id), ('company_id', '=', company_id)]",
        help="点单对应扣减的库存批次，需确保可用数量充足。",
    )
    combo_id = fields.Many2one(
        "store.combo",
        string="所属套餐",
        help="当行来源于套餐展开或套餐本身时记录对应套餐，便于统计。",
    )
    note = fields.Char(string="备注")
    is_combo_component = fields.Boolean(
        string="套餐组成",
        help="标记为套餐展开的组成行，避免重复计费。",
    )
    price_subtotal = fields.Monetary(
        string="小计",
        currency_field="currency_id",
        compute="_compute_amount",
        store=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            product = False
            if vals.get("product_id") and not vals.get("product_uom_id"):
                product = self.env["product.product"].browse(vals["product_id"])
                vals["product_uom_id"] = product.uom_id.id
            if vals.get("product_id") and "price_unit" not in vals:
                product = product or self.env["product.product"].browse(vals["product_id"])
                vals["price_unit"] = product.lst_price
        return super().create(vals_list)

    def write(self, vals):
        if "product_id" in vals and not vals.get("product_uom_id"):
            product = self.env["product.product"].browse(vals["product_id"])
            vals.setdefault("product_uom_id", product.uom_id.id)
        return super().write(vals)

    @api.depends("quantity", "price_unit", "currency_id")
    def _compute_amount(self):
        for line in self:
            line.price_subtotal = line.quantity * line.price_unit

    @api.onchange("product_id")
    def _onchange_product_id(self):
        for line in self:
            if line.product_id:
                line.product_uom_id = line.product_id.uom_id
                line.price_unit = line.product_id.lst_price

    @api.constrains("quantity")
    def _check_quantity_positive(self):
        for line in self:
            if line.quantity <= 0 and not float_is_zero(
                line.quantity, precision_rounding=line.product_uom_id.rounding
            ):
                raise ValidationError(_("数量必须大于 0。"))

    @api.constrains("batch_id", "product_id")
    def _check_batch_product(self):
        for line in self:
            if line.batch_id and line.batch_id.product_id != line.product_id:
                raise ValidationError(_("选择的批次与商品不一致，请重新选择符合的批次。"))
