from odoo import api, fields, models


class StoreFinancePaymentChannel(models.Model):
    _name = "store.finance.payment.channel"
    _description = "支付渠道配置"
    _order = "name"

    name = fields.Char(string="渠道名称", required=True, translate=True)
    code = fields.Char(string="代码", required=True)
    company_id = fields.Many2one(
        "res.company",
        string="公司",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    active = fields.Boolean(string="启用", default=True)
    journal_id = fields.Many2one(
        "account.journal",
        string="默认日记账",
        help="用于记录该渠道流水的日记账。",
    )
    account_id = fields.Many2one(
        "account.account",
        string="默认科目",
        help="如未在科目映射中指定，将回退到此默认科目。",
    )
    description = fields.Text(string="说明")

    _sql_constraints = [
        (
            "channel_code_company_unique",
            "unique(code, company_id)",
            "同一公司内支付渠道代码必须唯一。",
        )
    ]

    @api.model
    def get_default_channel(self, company=None):
        company = company or self.env.company
        return self.search(
            [("company_id", "=", company.id), ("active", "=", True)], limit=1
        )

