from odoo import fields, models


class StoreMemberLevel(models.Model):
    _name = "store.member.level"
    _description = "会员等级"
    _order = "sequence, threshold_amount desc"

    name = fields.Char(string="等级名称", required=True, translate=True)
    code = fields.Char(string="等级编码", required=True, help="用于接口传输的唯一编码。")
    sequence = fields.Integer(string="显示顺序", default=10)
    threshold_amount = fields.Monetary(
        string="累计消费阈值",
        currency_field="currency_id",
        help="达到该金额后自动升级为此等级。",
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="币种",
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    benefit_note = fields.Text(
        string="权益说明",
        help="用中文描述该等级对应的权益，门户端同步展示。",
    )
    active = fields.Boolean(string="启用", default=True)

    _sql_constraints = [
        ("code_unique", "unique(code)", "会员等级编码必须唯一。"),
    ]
