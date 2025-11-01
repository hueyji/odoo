from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class StoreAccountTransaction(models.Model):
    _name = "store.account.transaction"
    _description = "门店财务流水"
    _rec_name = "name"
    _order = "date DESC, id DESC"

    TRANSACTION_TYPES = [
        ("sale", "销售收款"),
        ("recharge", "储值充值"),
        ("refund", "退款"),
        ("transfer_adjust", "调拨补差"),
        ("crowdfunding_invest", "众筹投资"),
        ("crowdfunding_dividend", "众筹分红"),
        ("write_off", "报损"),
    ]

    name = fields.Char(string="流水编号", readonly=True, default="/", copy=False)
    date = fields.Datetime(string="记账时间", default=fields.Datetime.now, required=True)
    company_id = fields.Many2one(
        "res.company",
        string="公司",
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
    transaction_type = fields.Selection(
        selection=TRANSACTION_TYPES, string="类型", required=True, index=True
    )
    amount = fields.Monetary(string="金额", required=True)
    payment_channel_id = fields.Many2one(
        "store.finance.payment.channel",
        string="支付渠道",
    )
    account_map_id = fields.Many2one(
        "store.finance.account.map",
        string="科目映射",
        compute="_compute_account_map",
        store=True,
        readonly=True,
    )
    account_id = fields.Many2one(
        "account.account",
        string="会计科目",
        compute="_compute_account_map",
        store=True,
        readonly=True,
    )
    journal_id = fields.Many2one(
        "account.journal",
        string="关联日记账",
        compute="_compute_journal",
        store=True,
        readonly=True,
    )
    company_currency_id = fields.Many2one(
        "res.currency",
        string="公司本币",
        related="company_id.currency_id",
        store=True,
        readonly=True,
    )
    amount_company_currency = fields.Monetary(
        string="公司本币金额",
        currency_field="company_currency_id",
        compute="_compute_amount_company_currency",
        store=True,
    )
    reference = fields.Char(string="外部参照")
    description = fields.Text(string="备注")
    state = fields.Selection(
        [
            ("draft", "草稿"),
            ("confirmed", "已确认"),
            ("cancelled", "已取消"),
        ],
        string="状态",
        default="draft",
        required=True,
        index=True,
    )
    related_model = fields.Reference(
        selection="_selection_related_models",
        string="关联记录",
        help="关联订单、库存或众筹记录，便于追溯来源。",
    )
    clearing_id = fields.Many2one(
        "store.finance.clearing",
        string="互通清算单",
        readonly=True,
        index=True,
    )
    account_move_id = fields.Many2one(
        "account.move",
        string="关联凭证",
        help="如需同步正式会计凭证，可在此关联 account.move。",
    )

    _sql_constraints = [
        ("company_name_unique", "unique(name, company_id)", "同一公司内流水编号已存在。"),
    ]

    @api.onchange("company_id")
    def _onchange_company_id(self):
        """当公司改变时，返回支付渠道的 domain"""
        if self.company_id:
            return {
                'domain': {
                    'payment_channel_id': [('company_id', '=', self.company_id.id)]
                }
            }
        return {'domain': {'payment_channel_id': []}}

    @api.depends("transaction_type", "payment_channel_id", "company_id")
    def _compute_account_map(self):
        Map = self.env["store.finance.account.map"].sudo()
        for record in self:
            mapping = False
            if record.transaction_type and record.company_id:
                domain_base = [
                    ("company_id", "=", record.company_id.id),
                    ("transaction_type", "=", record.transaction_type),
                    ("active", "=", True),
                ]
                if record.payment_channel_id:
                    mapping = Map.search(
                        domain_base
                        + [("payment_channel_id", "=", record.payment_channel_id.id)],
                        limit=1,
                    )
                if not mapping:
                    mapping = Map.search(
                        domain_base + [("payment_channel_id", "=", False)],
                        limit=1,
                    )
            record.account_map_id = mapping or False
            record.account_id = mapping.account_id if mapping else False

    @api.depends("account_map_id", "payment_channel_id")
    def _compute_journal(self):
        for record in self:
            journal = record.account_map_id.journal_id or record.payment_channel_id.journal_id
            record.journal_id = journal or False

    @api.depends("amount", "currency_id", "date", "company_currency_id", "company_id")
    def _compute_amount_company_currency(self):
        for record in self:
            if (
                record.currency_id
                and record.company_currency_id
                and record.company_id
            ):
                record.amount_company_currency = record.currency_id._convert(
                    record.amount,
                    record.company_currency_id,
                    record.company_id,
                    record.date or fields.Date.context_today(record),
                )
            else:
                record.amount_company_currency = record.amount

    @api.constrains("transaction_type", "account_map_id")
    def _check_account_map(self):
        for record in self:
            if record.state != "cancelled" and not record.account_map_id:
                raise ValidationError(
                    _(
                        "公司 %(company)s 的类型 %(type)s 尚未配置会计科目映射，请在“财务配置 > 科目映射”中完成设置。"
                    )
                    % {
                        "company": record.company_id.display_name,
                        "type": dict(self.TRANSACTION_TYPES).get(
                            record.transaction_type, record.transaction_type
                        ),
                    }
                )

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env.ref(
            "store_finance.sequence_store_account_transaction", raise_if_not_found=False
        )
        for vals in vals_list:
            if vals.get("name", "/") == "/" and sequence:
                vals["name"] = sequence.next_by_id()
        return super().create(vals_list)

    def action_confirm(self):
        for record in self:
            if record.state == "draft":
                record.state = "confirmed"
        return True

    def action_cancel(self):
        for record in self:
            if record.state == "confirmed":
                record.state = "cancelled"
        return True

    def action_reset_to_draft(self):
        for record in self:
            if record.state == "cancelled":
                record.state = "draft"
        return True

    @api.model
    def _selection_related_models(self):
        registry = self.env.registry
        candidates = [
            ("sale.order", "销售订单"),
            ("stock.picking", "库存调拨"),
            ("store.inventory.batch", "库存批次"),
            ("store.bar.order", "吧台订单"),
            ("store.crowdfunding.project", "众筹项目"),
            ("store.crowdfunding.investment", "众筹投资"),
        ]
        return [(model, label) for model, label in candidates if model in registry]
