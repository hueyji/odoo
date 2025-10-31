from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class StoreAccountTransaction(models.Model):
    _name = "store.account.transaction"
    _description = "门店财务流水"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"
    _check_company_auto = True

    TRANSACTION_TYPE_SELECTION = [
        ("sale", "销售收款"),
        ("recharge", "会员充值"),
        ("refund", "退款支出"),
        ("inventory_loss", "报损冲减"),
        ("transfer", "内部调拨补差"),
        ("purchase", "采购付款"),
        ("commission", "提成发放"),
        ("crowdfunding", "众筹认购"),
        ("crowdfunding_dividend", "众筹分红"),
        ("other", "其他"),
    ]

    STATE_SELECTION = [
        ("draft", "草稿"),
        ("pending", "待确认"),
        ("confirmed", "已确认"),
        ("cancelled", "已取消"),
    ]

    REFERENCE_SELECTION = [
        ("store.inventory.move", "库存动作"),
        ("store.finance.clearing", "内部清算"),
        ("store.member.balance.move", "会员余额变动"),
        ("store.bar.order", "吧台订单"),
        ("store.commission.log", "提成结算"),
        ("store.crowdfunding.investment", "众筹投资"),
        ("store.crowdfunding.dividend.line", "众筹分红明细"),
    ]

    name = fields.Char(
        string="流水编号",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _("新流水"),
        tracking=True,
    )
    date = fields.Datetime(
        string="流水时间",
        default=fields.Datetime.now,
        required=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="公司",
        required=True,
        default=lambda self: self.env.company.id,
    )
    transaction_type = fields.Selection(
        selection=TRANSACTION_TYPE_SELECTION,
        string="流水类型",
        required=True,
        tracking=True,
        default="sale",
    )
    channel_id = fields.Many2one(
        "store.finance.channel",
        string="支付渠道",
        tracking=True,
        domain="[('company_id', '=', company_id)]",
    )
    channel_type = fields.Selection(
        related="channel_id.channel_type",
        string="渠道类型",
        store=True,
    )
    amount = fields.Monetary(
        string="金额",
        required=True,
        tracking=True,
    )
    amount_in = fields.Monetary(
        string="收入",
        compute="_compute_amount_direction",
        store=True,
        currency_field="currency_id",
    )
    amount_out = fields.Monetary(
        string="支出",
        compute="_compute_amount_direction",
        store=True,
        currency_field="currency_id",
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="币种",
        required=True,
        default=lambda self: self.env.company.currency_id.id,
    )
    balance_direction = fields.Selection(
        [
            ("in", "收入"),
            ("out", "支出"),
            ("neutral", "不影响"),
        ],
        string="方向",
        compute="_compute_amount_direction",
        store=True,
    )
    state = fields.Selection(
        selection=STATE_SELECTION,
        string="状态",
        default="draft",
        tracking=True,
    )
    member_id = fields.Many2one(
        "res.partner",
        string="关联会员",
        domain="[('company_id', 'in', [company_id, False])]",
        tracking=True,
    )
    user_id = fields.Many2one(
        "res.users",
        string="责任用户",
        tracking=True,
        default=lambda self: self.env.user.id,
    )
    link_group_id = fields.Many2one(
        "store.link.group",
        string="互通组",
        tracking=True,
    )
    clearing_id = fields.Many2one(
        "store.finance.clearing",
        string="内部清算单",
        index=True,
        copy=False,
    )
    reference = fields.Reference(
        string="关联对象",
        selection=REFERENCE_SELECTION,
        help="记录关联的业务对象，便于追溯来源。",
    )
    description = fields.Char(string="说明")

    _sql_constraints = [
        (
            "name_company_unique",
            "unique(name, company_id)",
            "同一公司下流水编号必须唯一。",
        ),
    ]

    @api.model
    def create(self, vals):
        if not vals.get("name") or vals.get("name") == _("新流水"):
            vals["name"] = (
                self.env["ir.sequence"].next_by_code("store.account.transaction")
                or _("新流水")
            )
        if not vals.get("channel_id"):
            channel = self._find_default_channel(vals.get("company_id"))
            if channel:
                vals["channel_id"] = channel.id
        return super().create(vals)

    def write(self, vals):
        res = super().write(vals)
        if {"amount"}.intersection(vals):
            for record in self:
                if record.state == "confirmed" and record.amount == 0:
                    raise ValidationError(_("已确认的流水金额不可改为 0。"))
        return res

    def _find_default_channel(self, company_id=None, preferred_type=None, allow_create=False):
        company = self.env["res.company"].browse(company_id) if company_id else self.env.company
        channel_domain = [
            ("company_id", "=", company.id),
            ("active", "=", True),
        ]
        if preferred_type:
            channel_domain.append(("channel_type", "=", preferred_type))
        else:
            channel_domain.append(("channel_type", "!=", "internal"))
            if company_id is None:
                channel_domain.append(("channel_type", "=", "cash"))
        channel = self.env["store.finance.channel"].search(
            channel_domain,
            limit=1,
            order="sequence asc, id asc",
        )
        if not channel:
            fallback_domain = [
                ("company_id", "=", company.id),
                ("active", "=", True),
            ]
            if preferred_type == "internal":
                fallback_domain.append(("channel_type", "=", "internal"))
            channel = self.env["store.finance.channel"].search(
                fallback_domain,
                limit=1,
                order="sequence asc, id asc",
            )
        if not channel and allow_create and preferred_type == "internal":
            channel = self.env["store.finance.channel"].create(
                {
                    "name": _("内部结算"),
                    "channel_type": "internal",
                    "company_id": company.id,
                    "auto_reconcile": False,
                }
            )
        if not channel and preferred_type:
            channel = self.env["store.finance.channel"].search(
                [
                    ("company_id", "=", company.id),
                    ("active", "=", True),
                ],
                limit=1,
                order="sequence asc, id asc",
            )
        return channel

    @api.constrains("amount")
    def _check_amount(self):
        for record in self:
            if record.state != "cancelled" and fields.Float.is_zero(
                record.amount, precision_rounding=record.currency_id.rounding
            ):
                raise ValidationError(_("流水金额不能为 0。"))

    @api.constrains("channel_id", "company_id")
    def _check_channel_company(self):
        for record in self:
            if record.channel_id and record.channel_id.company_id != record.company_id:
                raise ValidationError(_("支付渠道必须属于同一公司。"))

    @api.depends("amount")
    def _compute_amount_direction(self):
        for record in self:
            amount = record.amount or 0.0
            if fields.Float.is_zero(amount, precision_rounding=record.currency_id.rounding if record.currency_id else 0.01):
                record.amount_in = 0.0
                record.amount_out = 0.0
                record.balance_direction = "neutral"
                continue
            if amount > 0:
                record.amount_in = amount
                record.amount_out = 0.0
                record.balance_direction = "in"
            else:
                record.amount_in = 0.0
                record.amount_out = abs(amount)
                record.balance_direction = "out"

    def action_set_pending(self):
        for record in self.filtered(lambda r: r.state == "draft"):
            record.state = "pending"
            record.message_post(body=_("流水已提交待确认。"))

    def action_confirm(self):
        for record in self.filtered(lambda r: r.state in ("draft", "pending")):
            record._validate_before_confirm()
            record.write({"state": "confirmed"})
            record.message_post(
                body=_(
                    "流水已确认，方向：%(direction)s，金额：%(amount)s。",
                    direction=dict(self._fields["balance_direction"].selection).get(record.balance_direction, ""),
                    amount=record.amount,
                )
            )
        return True

    def action_cancel(self):
        for record in self:
            if record.state == "cancelled":
                continue
            if record.clearing_id:
                raise UserError(_("内部清算生成的流水需通过清算单作废。"))
            record.state = "cancelled"
            record.message_post(body=_("流水已取消，无需参与报表统计。"))
        return True

    def action_reset_to_draft(self):
        for record in self:
            if record.state != "cancelled":
                raise ValidationError(_("仅取消状态的流水可重置为草稿。"))
            record.state = "draft"
            record.message_post(body=_("流水已恢复为草稿，请重新确认。"))
        return True

    def group_by_channel(self):
        data = defaultdict(lambda: {"amount": 0.0, "count": 0})
        for record in self.filtered(lambda r: r.state == "confirmed"):
            key = record.channel_id.display_name if record.channel_id else _("未指定渠道")
            data[key]["amount"] += record.amount
            data[key]["count"] += 1
        return data

    def _validate_before_confirm(self):
        self.ensure_one()
        if not self.company_id:
            raise ValidationError(_("必须指定公司。"))
        if self.channel_id and not self.channel_id.active:
            raise ValidationError(_("支付渠道已停用，请选择其他渠道。"))
        if self.transaction_type in {"recharge", "crowdfunding"} and self.amount <= 0:
            raise ValidationError(_("充值或众筹认购金额必须大于 0。"))
        if self.transaction_type in {"refund", "inventory_loss", "purchase", "commission", "crowdfunding_dividend"} and self.amount >= 0:
            raise ValidationError(_("退款、报损、采购、提成或众筹分红流水金额必须小于 0。"))

    def name_get(self):
        result = []
        for record in self:
            display = record.name
            if record.transaction_type:
                display = f"[{dict(self._fields['transaction_type'].selection).get(record.transaction_type)}] {display}"
            result.append((record.id, display))
        return result
