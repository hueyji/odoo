from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class StoreFinanceClearing(models.Model):
    _name = "store.finance.clearing"
    _description = "互通清算单"
    _order = "date DESC, id DESC"

    name = fields.Char(string="清算编号", default="/", readonly=True, copy=False)
    date = fields.Date(string="清算日期", default=fields.Date.context_today, required=True)
    company_id = fields.Many2one(
        "res.company",
        string="公司",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    state = fields.Selection(
        [
            ("draft", "草稿"),
            ("confirmed", "待审核"),
            ("approved", "已审核"),
            ("cancelled", "已取消"),
        ],
        string="状态",
        default="draft",
        required=True,
        index=True,
    )
    note = fields.Text(string="说明")
    line_ids = fields.One2many(
        "store.finance.clearing.line",
        "clearing_id",
        string="清算明细",
    )
    approved_by = fields.Many2one(
        "res.users",
        string="审核人",
        readonly=True,
    )
    approved_date = fields.Datetime(
        string="审核时间",
        readonly=True,
    )
    total_amount_company_currency = fields.Monetary(
        string="本币合计",
        currency_field="company_currency_id",
        compute="_compute_totals",
        store=True,
    )
    company_currency_id = fields.Many2one(
        "res.currency",
        related="company_id.currency_id",
        readonly=True,
        store=True,
    )
    total_transaction_count = fields.Integer(
        string="流水笔数",
        compute="_compute_totals",
        store=True,
    )

    _sql_constraints = [
        ("clearing_name_company_unique", "unique(name, company_id)", "清算编号已存在。"),
    ]

    @api.depends("line_ids.amount_company_currency")
    def _compute_totals(self):
        for record in self:
            total = sum(record.line_ids.mapped("amount_company_currency"))
            record.total_amount_company_currency = total
            record.total_transaction_count = len(record.line_ids)

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env.ref(
            "store_finance.sequence_store_finance_clearing", raise_if_not_found=False
        )
        for vals in vals_list:
            if vals.get("name", "/") == "/" and sequence:
                vals["name"] = sequence.next_by_id()
        return super().create(vals_list)

    def action_confirm(self):
        for record in self:
            if record.state != "draft":
                continue
            if not record.line_ids:
                raise ValidationError(_("请至少添加一条清算明细。"))
            record._ensure_lines_ready()
            record.line_ids.mapped("transaction_id").write({"clearing_id": record.id})
            record.approved_by = False
            record.approved_date = False
            record.state = "confirmed"
        return True

    def action_approve(self):
        for record in self:
            if record.state != "confirmed":
                continue
            record.approved_by = self.env.user
            record.approved_date = fields.Datetime.now()
            record.state = "approved"
        return True

    def action_cancel(self):
        for record in self:
            if record.state not in ("confirmed", "approved"):
                continue
            record.line_ids.mapped("transaction_id").write({"clearing_id": False})
            record.approved_by = False
            record.approved_date = False
            record.state = "cancelled"
        return True

    def action_reset_to_draft(self):
        for record in self:
            if record.state != "cancelled":
                continue
            record.state = "draft"
        return True

    def _ensure_lines_ready(self):
        for line in self.line_ids:
            if line.transaction_id.state != "confirmed":
                raise ValidationError(
                    _("仅可清算已确认的流水：%s") % line.transaction_id.display_name
                )
            if line.transaction_id.clearing_id and line.transaction_id.clearing_id != self:
                raise ValidationError(
                    _("流水 %s 已关联其他清算单。") % line.transaction_id.display_name
                )


class StoreFinanceClearingLine(models.Model):
    _name = "store.finance.clearing.line"
    _description = "互通清算明细"
    _order = "transaction_id"

    clearing_id = fields.Many2one(
        "store.finance.clearing",
        string="清算单",
        required=True,
        ondelete="cascade",
    )
    transaction_id = fields.Many2one(
        "store.account.transaction",
        string="财务流水",
        required=True,
        domain="[('state', '=', 'confirmed'), ('company_id', '=', parent.company_id)]",
    )
    company_id = fields.Many2one(
        related="clearing_id.company_id",
        comodel_name="res.company",
        store=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        related="transaction_id.currency_id",
        comodel_name="res.currency",
        store=True,
        readonly=True,
    )
    amount_currency = fields.Monetary(
        string="原币金额",
        currency_field="currency_id",
        compute="_compute_amounts",
        store=True,
    )
    amount_company_currency = fields.Monetary(
        string="本币金额",
        currency_field="company_currency_id",
        compute="_compute_amounts",
        store=True,
    )
    company_currency_id = fields.Many2one(
        related="clearing_id.company_currency_id",
        comodel_name="res.currency",
        store=True,
        readonly=True,
    )

    _sql_constraints = [
        (
            "transaction_unique_per_clearing",
            "unique(clearing_id, transaction_id)",
            "同一流水不能重复添加至清算单。",
        )
    ]

    @api.depends("transaction_id", "transaction_id.amount", "transaction_id.amount_company_currency")
    def _compute_amounts(self):
        for record in self:
            transaction = record.transaction_id
            record.amount_currency = transaction.amount
            record.amount_company_currency = transaction.amount_company_currency
