from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class StoreFinanceAccountMap(models.Model):
    _name = "store.finance.account.map"
    _description = "财务科目映射"
    _order = "transaction_type, payment_channel_id"

    transaction_type = fields.Selection(
        selection=lambda self: self.env["store.account.transaction"].TRANSACTION_TYPES,
        string="流水类型",
        required=True,
    )
    payment_channel_id = fields.Many2one(
        "store.finance.payment.channel",
        string="支付渠道",
        domain="[('company_id', '=', company_id)]",
    )
    company_id = fields.Many2one(
        "res.company",
        string="公司",
        required=True,
        default=lambda self: self.env.company,
    )
    account_id = fields.Many2one(
        "account.account",
        string="会计科目",
        required=True,
        domain="[('company_id', '=', company_id)]",
    )
    journal_id = fields.Many2one(
        "account.journal",
        string="默认日记账",
        domain="[('company_id', '=', company_id)]",
    )
    active = fields.Boolean(string="启用", default=True)
    note = fields.Text(string="备注")
    name = fields.Char(string="名称", compute="_compute_name", store=True)

    @api.depends("transaction_type", "payment_channel_id")
    def _compute_name(self):
        type_dict = dict(
            self.env["store.account.transaction"].TRANSACTION_TYPES
        )
        for record in self:
            pieces = [type_dict.get(record.transaction_type, record.transaction_type)]
            if record.payment_channel_id:
                pieces.append(record.payment_channel_id.display_name)
            record.name = " - ".join(pieces)

    @api.constrains("transaction_type", "payment_channel_id", "company_id", "active")
    def _check_unique_combination(self):
        for record in self:
            domain = [
                ("company_id", "=", record.company_id.id),
                ("transaction_type", "=", record.transaction_type),
                ("id", "!=", record.id),
                ("active", "=", True),
            ]
            if record.payment_channel_id:
                domain.append(("payment_channel_id", "=", record.payment_channel_id.id))
            else:
                domain.append(("payment_channel_id", "=", False))
            if self.search_count(domain):
                raise ValidationError(
                    _("%(company)s 已存在相同类型与渠道的科目映射，请勿重复创建。")
                    % {"company": record.company_id.display_name}
                )
