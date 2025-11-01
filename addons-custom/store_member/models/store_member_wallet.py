from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class StoreMemberWallet(models.Model):
    _name = "store.member.wallet"
    _description = "会员余额账户"
    _order = "partner_id, balance_type, company_id"
    _rec_name = "display_name"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    partner_id = fields.Many2one(
        "res.partner",
        string="会员",
        required=True,
        index=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        "res.company",
        string="所属公司",
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )
    balance_type = fields.Selection(
        [
            ("cash", "储值余额"),
            ("crowdfunding", "众筹收益"),
        ],
        string="余额类型",
        required=True,
        default="cash",
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="币种",
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    balance = fields.Monetary(
        string="当前余额",
        currency_field="currency_id",
        default=0.0,
        help="最新的可用余额数值。",
        tracking=True,
    )
    sharing_scope = fields.Selection(
        [
            ("store_only", "仅本门店"),
            ("link_group", "互通组共享"),
            ("brand", "品牌共享"),
        ],
        string="共享范围",
        default="store_only",
        help="指示余额可在哪些范围内消费，便于联动 Team A 互通模块。",
    )
    allow_negative = fields.Boolean(
        string="允许透支",
        default=False,
        help="开启后门店可在互通清算前先消费。",
    )
    last_transaction_date = fields.Datetime(
        string="最近变动时间",
        readonly=True,
    )
    log_ids = fields.One2many(
        "store.member.balance.log",
        "wallet_id",
        string="余额变动日志",
    )
    display_name = fields.Char(
        string="名称",
        compute="_compute_display_name",
        store=True,
    )

    _sql_constraints = [
        (
            "wallet_unique",
            "unique(partner_id, company_id, balance_type)",
            "同一会员在同一公司下的余额类型只能存在一个账户。",
        )
    ]

    @api.depends("partner_id", "balance_type", "company_id")
    def _compute_display_name(self):
        for wallet in self:
            wallet.display_name = "%s/%s/%s" % (
                wallet.partner_id.name or _("未命名会员"),
                dict(self._fields["balance_type"].selection).get(wallet.balance_type, ""),
                wallet.company_id.name or _("未知公司"),
            )

    def _apply_balance_change(self, amount, transaction_type, note=None, reference=None, trace_payload=None):
        """Update balance and append log with sanity checks."""
        self.ensure_one()
        if not amount:
            raise UserError(_("余额变动金额不能为空。"))
        if amount < 0 and not self.allow_negative and self.balance + amount < -1e-6:
            raise UserError(_("余额不足：当前余额 %.2f，无法扣减 %.2f。") % (self.balance, -amount))

        new_balance = self.balance + amount
        log_vals = {
            "wallet_id": self.id,
            "change_amount": amount,
            "balance_after": new_balance,
            "transaction_type": transaction_type,
            "note": note or "",
            "reference": reference,
            "company_id": self.company_id.id,
            "actor_id": self.env.user.id,
        }
        if trace_payload:
            log_vals["trace_payload"] = trace_payload
        self.write(
            {
                "balance": new_balance,
                "last_transaction_date": fields.Datetime.now(),
            }
        )
        self.env["store.member.balance.log"].create(log_vals)
        return new_balance

    @api.model
    def get_or_create_wallet(self, partner, company, balance_type="cash"):
        if not partner:
            raise ValidationError(_("必须指定会员。"))
        if not company:
            company = self.env.company
        wallet = self.search(
            [
                ("partner_id", "=", partner.id),
                ("company_id", "=", company.id),
                ("balance_type", "=", balance_type),
            ],
            limit=1,
        )
        if wallet:
            return wallet
        return self.create(
            {
                "partner_id": partner.id,
                "company_id": company.id,
                "balance_type": balance_type,
                "currency_id": company.currency_id.id,
            }
        )


class StoreMemberBalanceLog(models.Model):
    _name = "store.member.balance.log"
    _description = "会员余额变动日志"
    _order = "create_date desc"

    wallet_id = fields.Many2one(
        "store.member.wallet",
        string="余额账户",
        required=True,
        ondelete="cascade",
    )
    partner_id = fields.Many2one(
        related="wallet_id.partner_id",
        store=True,
        string="会员",
    )
    company_id = fields.Many2one(
        "res.company",
        string="所属公司",
        required=True,
        default=lambda self: self.env.company,
    )
    change_amount = fields.Monetary(
        string="变动金额",
        currency_field="currency_id",
        required=True,
    )
    balance_after = fields.Monetary(
        string="变动后余额",
        currency_field="currency_id",
        required=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="币种",
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    transaction_type = fields.Selection(
        [
            ("recharge", "充值"),
            ("consume", "消费"),
            ("refund", "退款"),
            ("crowdfunding_in", "众筹入账"),
            ("crowdfunding_out", "众筹支出"),
            ("adjust", "手工调整"),
        ],
        string="交易类型",
        required=True,
    )
    reference = fields.Char(
        string="关联编号",
        help="关联订单或财务流水编号，用于追踪。",
    )
    note = fields.Text(string="备注")
    actor_id = fields.Many2one(
        "res.users",
        string="操作人",
        required=True,
        default=lambda self: self.env.user,
    )
    trace_payload = fields.Text(
        string="追踪信息",
        help="记录接口调用参数、Trace ID 等调试信息（JSON 字符串）。",
    )

    _sql_constraints = [
        ("change_amount_non_zero", "CHECK (change_amount <> 0)", "余额变动金额不能为 0。"),
    ]
