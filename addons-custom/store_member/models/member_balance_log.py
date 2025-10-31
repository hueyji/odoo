from odoo import api, fields, models


class StoreMemberBalanceLog(models.Model):
    _name = "store.member.balance.log"
    _description = "会员余额变动日志"
    _order = "create_date desc"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    CHANGE_TYPES = [
        ("recharge", "充值增加"),
        ("consumption", "消费扣减"),
        ("adjustment", "手工调整"),
        ("transfer_in", "转入"),
        ("transfer_out", "转出"),
    ]

    partner_id = fields.Many2one(
        "res.partner",
        string="会员",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="操作门店",
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )
    operator_id = fields.Many2one(
        "res.users",
        string="操作人",
        default=lambda self: self.env.user,
    )
    change_type = fields.Selection(
        selection=CHANGE_TYPES,
        string="变动类型",
        required=True,
        default="recharge",
    )
    delta_amount = fields.Monetary(
        string="变动金额",
        currency_field="currency_id",
        help="正数表示增加，负数表示扣减。",
    )
    balance_before = fields.Monetary(
        string="变动前余额",
        currency_field="currency_id",
        readonly=True,
    )
    balance_after = fields.Monetary(
        string="变动后余额",
        currency_field="currency_id",
        readonly=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="币种",
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    reference = fields.Char(string="关联记录", index=True)
    note = fields.Char(string="备注")
    link_group_id = fields.Many2one(
        "store.link.group",
        string="互通组",
        help="记录此次变动关联的互通组，用于审计。",
    )
    portal_visible = fields.Boolean(
        string="Portal 可见",
        default=True,
        help="标记是否在会员 Portal 端展示该条记录。",
    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._populate_link_group()
        return records

    def write(self, vals):
        res = super().write(vals)
        if "company_id" in vals or "partner_id" in vals:
            self._populate_link_group()
        return res

    def _populate_link_group(self):
        for record in self:
            if record.link_group_id:
                continue
            partner = record.partner_id
            if not partner:
                continue
            group = partner.share_with_group_ids.filtered(
                lambda g: record.company_id in g.member_company_ids
                and g.share_member
            )[:1]
            if group:
                record.sudo().write({"link_group_id": group.id})
