from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare


class StoreBarOrder(models.Model):
    _name = "store.bar.order"
    _description = "吧台点单"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc, id desc"
    _check_company_auto = True

    name = fields.Char(string="订单编号", required=True, default="/", copy=False, tracking=True)
    company_id = fields.Many2one(
        "res.company",
        string="所属公司",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="币种",
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    table_id = fields.Many2one(
        "store.bar.table",
        string="桌台",
        required=True,
        tracking=True,
        domain="[('company_id', '=', company_id)]",
    )
    employee_id = fields.Many2one(
        "hr.employee",
        string="责任员工",
        tracking=True,
        domain="[('company_id', '=', company_id)]",
    )
    member_id = fields.Many2one(
        "res.partner",
        string="会员",
        help="如顾客为品牌会员，可在此关联以便同步权益和余额扣减。",
    )
    state = fields.Selection(
        [
            ("draft", "草稿"),
            ("locked", "已锁定"),
            ("serving", "出品中"),
            ("billing", "结账中"),
            ("billed", "已结账"),
            ("cancelled", "已取消"),
        ],
        string="状态",
        default="draft",
        tracking=True,
        index=True,
    )
    order_line_ids = fields.One2many(
        "store.bar.order.line",
        "order_id",
        string="订单明细",
        copy=True,
    )
    amount_subtotal = fields.Monetary(
        string="小计金额",
        currency_field="currency_id",
        compute="_compute_amounts",
        store=True,
    )
    amount_total = fields.Monetary(
        string="合计金额",
        currency_field="currency_id",
        compute="_compute_amounts",
        store=True,
    )
    locked_at = fields.Datetime(string="锁定时间", readonly=True)
    billed_at = fields.Datetime(string="结账时间", readonly=True)
    note = fields.Text(string="备注")

    @api.depends("order_line_ids.price_subtotal")
    def _compute_amounts(self):
        for order in self:
            subtotal = sum(order.order_line_ids.mapped("price_subtotal"))
            order.amount_subtotal = subtotal
            order.amount_total = order.amount_subtotal

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env.ref("store_bar.sequence_store_bar_order", raise_if_not_found=False)
        for vals in vals_list:
            if vals.get("name", "/") == "/" and sequence:
                vals["name"] = sequence.next_by_id()
        orders = super().create(vals_list)
        return orders

    def write(self, vals):
        if "table_id" in vals:
            disallowed = self.filtered(lambda o: o.state not in ("draft", "cancelled"))
            if disallowed:
                raise ValidationError(_("订单已进入出品或结账流程，禁止更换桌台。"))
        return super().write(vals)

    def unlink(self):
        for order in self:
            if order.state not in ("draft", "cancelled"):
                raise ValidationError(_("仅可删除草稿或已取消的订单。"))
        return super().unlink()

    def action_lock(self):
        for order in self:
            if order.state != "draft":
                raise ValidationError(_("仅草稿订单可以锁定。"))
            order._ensure_table_available()
            order._ensure_has_lines()
            order._ensure_employee_assigned()
            order._check_line_batches()
            order._check_inventory_levels()
            if order.name == "/":
                sequence = self.env.ref("store_bar.sequence_store_bar_order", raise_if_not_found=False)
                if sequence:
                    order.name = sequence.next_by_id()
            order.write(
                {
                    "state": "locked",
                    "locked_at": fields.Datetime.now(),
                }
            )
            order.table_id.action_attach_order(order)
        return True

    def action_start_serving(self):
        for order in self:
            if order.state != "locked":
                raise ValidationError(_("仅已锁定的订单可以进入出品。"))
            order.write({"state": "serving"})
        return True

    def action_request_billing(self):
        for order in self:
            if order.state not in ("locked", "serving"):
                raise ValidationError(_("订单尚未开始或已完成，无法进入结账。"))
            order.write({"state": "billing"})
            order.table_id.write({"state": "billing"})
        return True

    def action_set_billed(self):
        for order in self:
            if order.state not in ("serving", "billing", "locked"):
                raise ValidationError(_("仅进行中的订单可以结账。"))
            order.write(
                {
                    "state": "billed",
                    "billed_at": fields.Datetime.now(),
                }
            )
            order.table_id.action_detach_order(order)
        return True

    def action_cancel(self):
        for order in self:
            if order.state in ("billed",):
                raise ValidationError(_("订单已结账，不可取消。"))
            order.write({"state": "cancelled"})
            if order.table_id.current_order_id == order:
                order.table_id.action_detach_order(order)
        return True

    def _ensure_table_available(self):
        self.ensure_one()
        table = self.table_id
        if table.current_order_id and table.current_order_id != self:
            raise ValidationError(_("桌台正在处理订单 %(name)s，无法重复分配。", name=table.current_order_id.name))
        if table.state in ("occupied", "billing") and table.current_order_id and table.current_order_id != self:
            raise ValidationError(_("桌台状态为 %(state)s，无法创建新的订单。", state=dict(table._fields["state"].selection).get(table.state)))

    def _ensure_has_lines(self):
        self.ensure_one()
        lines = self.order_line_ids.filtered(lambda l: not l.is_combo_component)
        if not lines:
            raise ValidationError(_("订单必须至少包含一条商品或套餐明细。"))

    def _ensure_employee_assigned(self):
        self.ensure_one()
        if not self.employee_id:
            raise ValidationError(_("请先选择责任员工，再锁定订单。"))

    def _check_line_batches(self):
        self.ensure_one()
        for line in self.order_line_ids.filtered(lambda l: not l.is_combo_component):
            if not line.batch_id:
                raise ValidationError(_("商品 %s 尚未选择对应批次，无法锁定订单。") % line.product_id.display_name)

    def _check_inventory_levels(self):
        self.ensure_one()
        relevant_lines = self.order_line_ids.filtered(lambda l: l.batch_id and not l.is_combo_component)
        if not relevant_lines:
            return True
        batch_ids = relevant_lines.mapped("batch_id")
        reserved_map = self._get_reserved_quantity_map(batch_ids)
        for line in relevant_lines:
            batch = line.batch_id
            reserved_qty = reserved_map.get(batch.id, 0.0)
            # 若 map 中包含自身批次，已排除当前订单，无需减去自身数量
            available_qty = batch.qty_available - reserved_qty
            precision = line.product_uom_id.rounding or 0.0001
            if float_compare(available_qty, line.quantity, precision_rounding=precision) < 0:
                raise ValidationError(
                    _(
                        "批次 %(batch)s 可用数量不足（剩余 %(available)s），无法支持商品 %(product)s 的下单数量 %(needed)s。",
                        batch=batch.display_name,
                        available=available_qty,
                        product=line.product_id.display_name,
                        needed=line.quantity,
                    )
                )
        return True

    def _get_reserved_quantity_map(self, batches):
        if not batches:
            return {}
        domain = [
            ("order_id.state", "in", ["locked", "serving", "billing"]),
            ("batch_id", "in", batches.ids),
        ]
        data = self.env["store.bar.order.line"].read_group(domain, ["quantity:sum"], ["batch_id"])
        reserved = defaultdict(float)
        for entry in data:
            batch_id = entry["batch_id"][0]
            reserved[batch_id] += entry["quantity"]
        return reserved

    @api.constrains("employee_id", "company_id")
    def _check_employee_company(self):
        for order in self:
            if order.employee_id and order.employee_id.company_id and order.employee_id.company_id != order.company_id:
                raise ValidationError(_("责任员工必须隶属于当前公司。"))

    @api.constrains("member_id", "company_id")
    def _check_member_company(self):
        # 品牌会员可能跨公司共享，此处不强制校验，仅保留接口
        return True
