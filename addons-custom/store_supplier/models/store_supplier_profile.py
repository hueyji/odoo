from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class StoreSupplier(models.Model):
    _name = "store.supplier"
    _description = "门店供应商档案"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name"

    name = fields.Char(string="供应商名称", required=True, tracking=True)
    partner_id = fields.Many2one(
        "res.partner",
        string="关联联系人",
        domain="[('supplier_rank', '>', 0)]",
        tracking=True,
        required=True,
    )
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
        related="company_id.currency_id",
        store=True,
        readonly=True,
    )
    category_ids = fields.Many2many(
        "res.partner.category",
        string="标签",
        help="用于对供应商进行快速分类与筛选。",
    )
    product_category_ids = fields.Many2many(
        "product.category",
        string="主要商品分类",
        help="供应商常供货的商品分类。",
    )
    contact_user_id = fields.Many2one(
        "res.users",
        string="对接人",
        tracking=True,
        help="负责该供应商沟通与维护的内部人员。",
    )
    phone = fields.Char(string="联系电话", related="partner_id.phone", readonly=False)
    email = fields.Char(string="电子邮箱", related="partner_id.email", readonly=False)
    website = fields.Char(string="官网", related="partner_id.website", readonly=False)
    address = fields.Text(string="地址", compute="_compute_address")

    score_delivery = fields.Float(string="交付评分", digits=(16, 2), tracking=True, default=3.0)
    score_quality = fields.Float(string="质量评分", digits=(16, 2), tracking=True, default=3.0)
    score_service = fields.Float(string="服务评分", digits=(16, 2), tracking=True, default=3.0)
    rating_overall = fields.Float(string="综合评分", compute="_compute_rating", store=True, digits=(16, 2))
    risk_level = fields.Selection(
        [
            ("low", "低风险"),
            ("medium", "中风险"),
            ("high", "高风险"),
        ],
        string="风险等级",
        default="low",
        tracking=True,
    )

    is_blacklisted = fields.Boolean(string="黑名单", tracking=True)
    blacklist_reason = fields.Text(string="拉黑原因")
    blacklist_date = fields.Date(string="拉黑日期")
    blacklist_user_id = fields.Many2one("res.users", string="操作人", readonly=True)

    purchase_order_ids = fields.One2many(
        "purchase.order",
        "store_supplier_id",
        string="采购订单",
        readonly=True,
    )
    purchase_order_count = fields.Integer(string="采购订单数", compute="_compute_purchase_metrics", store=True)
    purchase_amount_total = fields.Monetary(string="采购金额", compute="_compute_purchase_metrics", store=True)
    last_purchase_date = fields.Date(string="最近采购日期", compute="_compute_purchase_metrics", store=True)

    delivery_cycle_avg = fields.Float(string="平均交付周期（天）", digits=(16, 2), compute="_compute_purchase_metrics", store=True)
    on_time_rate = fields.Float(string="准时率（%）", digits=(16, 2), compute="_compute_purchase_metrics", store=True)

    active = fields.Boolean(default=True, string="启用")
    note = fields.Text(string="备注")

    _sql_constraints = [
        ("partner_company_unique", "unique(partner_id, company_id)", "同一公司内供应商档案已存在。"),
    ]

    @api.depends("partner_id")
    def _compute_address(self):
        for rec in self:
            rec.address = rec.partner_id._display_address() if rec.partner_id else False

    @api.depends("score_delivery", "score_quality", "score_service")
    def _compute_rating(self):
        for rec in self:
            scores = [rec.score_delivery, rec.score_quality, rec.score_service]
            values = [score for score in scores if score]
            rec.rating_overall = round(sum(values) / len(values), 2) if values else 0.0

    @api.depends("purchase_order_ids.state", "purchase_order_ids.amount_total")
    def _compute_purchase_metrics(self):
        for rec in self:
            confirmed_orders = rec.purchase_order_ids.filtered(lambda o: o.state in ("purchase", "done"))
            rec.purchase_order_count = len(confirmed_orders)
            rec.purchase_amount_total = sum(confirmed_orders.mapped("amount_total"))
            rec.last_purchase_date = confirmed_orders and max(confirmed_orders.mapped("date_order")) or False

            # 统计交付周期与准时率
            delivered_orders = confirmed_orders.filtered(lambda o: o.picking_ids)
            durations = []
            on_time = 0
            for order in delivered_orders:
                finished_pickings = order.picking_ids.filtered(lambda p: p.state == "done")
                if not finished_pickings:
                    continue
                delivery_dates = finished_pickings.mapped("date_done")
                if not delivery_dates:
                    continue
                delivery_day = max(delivery_dates).date()
                order_day = fields.Date.to_date(order.date_order)
                duration = (delivery_day - order_day).days if order_day and delivery_day else 0
                durations.append(duration)
                planned_dates = order.order_line.mapped("date_planned")
                planned_deadline = max(planned_dates).date() if planned_dates else False
                if planned_deadline and delivery_day <= planned_deadline:
                    on_time += 1
            rec.delivery_cycle_avg = round(sum(durations) / len(durations), 2) if durations else 0.0
            rec.on_time_rate = round((on_time / len(durations)) * 100, 2) if durations else 0.0

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if not rec.name and rec.partner_id:
                rec.name = rec.partner_id.name
            if rec.partner_id:
                rec.partner_id.supplier_rank = max(rec.partner_id.supplier_rank, 1)
            if rec.is_blacklisted:
                if not rec.blacklist_reason:
                    raise ValidationError(_("请填写拉黑原因。"))
                if not rec.blacklist_date:
                    rec.blacklist_date = fields.Date.context_today(self)
                if not rec.blacklist_user_id:
                    rec.blacklist_user_id = self.env.user
        return records

    def write(self, vals):
        if vals.get("is_blacklisted") and vals.get("is_blacklisted") is True:
            if not vals.get("blacklist_reason") and not any(rec.blacklist_reason for rec in self):
                raise ValidationError(_("请填写拉黑原因。"))
        res = super().write(vals)
        if "is_blacklisted" in vals:
            for rec in self:
                if rec.is_blacklisted:
                    if not rec.blacklist_reason:
                        raise ValidationError(_("请填写拉黑原因。"))
                    rec.blacklist_date = fields.Date.context_today(self)
                    rec.blacklist_user_id = self.env.user
                else:
                    rec.blacklist_date = False
                    rec.blacklist_user_id = False
        return res

    def action_mark_blacklist(self):
        for rec in self:
            if rec.is_blacklisted:
                raise UserError(_("该供应商已在黑名单中。"))
            if not rec.blacklist_reason:
                raise ValidationError(_("请先填写拉黑原因。"))
            rec.write(
                {
                    "is_blacklisted": True,
                    "blacklist_date": fields.Date.context_today(self),
                    "blacklist_user_id": self.env.user.id,
                }
            )
            rec.message_post(body=_("供应商已加入黑名单。"))
        return True

    def action_remove_blacklist(self):
        for rec in self:
            if not rec.is_blacklisted:
                raise UserError(_("该供应商未在黑名单中。"))
            rec.write({"is_blacklisted": False})
            rec.message_post(body=_("已移除供应商黑名单状态。"))
        return True

    def action_open_purchase_orders(self):
        self.ensure_one()
        action = self.env.ref("purchase.purchase_rfq").read()[0]
        action["domain"] = [("store_supplier_id", "=", self.id)]
        action.setdefault("context", {})
        action["context"].update({
            "search_default_store_supplier_id": self.id,
            "default_store_supplier_id": self.id,
            "default_partner_id": self.partner_id.id,
            "default_company_id": self.company_id.id,
        })
        return action


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    store_supplier_id = fields.Many2one(
        "store.supplier",
        string="供应商档案",
        domain="[('company_id', '=', company_id)]",
        help="选定关联的供应商档案，用于统计绩效。",
    )

    def write(self, vals):
        res = super().write(vals)
        if any(key in vals for key in ("partner_id", "company_id")):
            for order in self:
                order._assign_store_supplier()
        return res

    @api.model
    def create(self, vals):
        order = super().create(vals)
        order._assign_store_supplier()
        return order

    def _assign_store_supplier(self):
        for order in self:
            if order.store_supplier_id:
                continue
            if not order.partner_id or not order.company_id:
                continue
            supplier = self.env["store.supplier"].search(
                [
                    ("partner_id", "=", order.partner_id.id),
                    ("company_id", "=", order.company_id.id),
                ],
                limit=1,
            )
            if supplier:
                order.store_supplier_id = supplier.id
            else:
                # 自动创建档案以保持数据完整
                supplier = self.env["store.supplier"].create(
                    {
                        "partner_id": order.partner_id.id,
                        "company_id": order.company_id.id,
                        "name": order.partner_id.name,
                    }
                )
                order.store_supplier_id = supplier.id
