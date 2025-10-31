from odoo import _, api, fields, models
from odoo.exceptions import UserError


class StoreMemberRecharge(models.Model):
    _name = "store.member.recharge"
    _description = "会员充值单"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"

    PAYMENT_METHODS = [
        ("cash", "现金"),
        ("pos", "POS 刷卡"),
        ("wechat", "微信支付"),
        ("alipay", "支付宝"),
        ("bank", "银行转账"),
        ("other", "其他渠道"),
    ]

    name = fields.Char(
        string="充值单号",
        required=True,
        copy=False,
        readonly=True,
        default="新建",
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="会员",
        required=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="充值门店",
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
    )
    amount = fields.Monetary(
        string="充值金额",
        currency_field="currency_id",
        required=True,
        tracking=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="币种",
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    payment_method = fields.Selection(
        selection=PAYMENT_METHODS,
        string="支付渠道",
        required=True,
        default="cash",
        tracking=True,
    )
    state = fields.Selection(
        selection=[
            ("draft", "草稿"),
            ("confirmed", "已确认"),
            ("cancelled", "已作废"),
        ],
        string="状态",
        required=True,
        default="draft",
        tracking=True,
    )
    log_id = fields.Many2one(
        "store.member.balance.log",
        string="余额日志",
        readonly=True,
    )
    note = fields.Text(string="备注")
    operator_id = fields.Many2one(
        "res.users",
        string="经办人",
        default=lambda self: self.env.user,
        readonly=True,
    )
    link_group_id = fields.Many2one(
        "store.link.group",
        string="互通组",
        readonly=True,
        help="若由互通门店发起，记录所属互通组。",
    )

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env.ref(
            "store_member.sequence_member_recharge", raise_if_not_found=False
        )
        for vals in vals_list:
            if vals.get("name", "新建") in (False, "/", "新建"):
                vals["name"] = sequence.next_by_id() if sequence else _("充值单草稿")
        return super().create(vals_list)

    def _ensure_draft(self):
        for record in self:
            if record.state != "draft":
                raise UserError(_("只有草稿状态才能执行此操作。"))

    def action_confirm(self):
        for record in self:
            record._ensure_draft()
            if record.amount <= 0:
                raise UserError(_("充值金额必须大于 0。"))
            company = record.company_id or self.env.company
            log = record.partner_id.action_member_recharge(
                record.amount,
                company=company,
                note=record.note,
                reference=record,
            )
            record.write(
                {
                    "state": "confirmed",
                    "log_id": log.id,
                    "link_group_id": log.link_group_id.id,
                }
            )
        return True

    def action_cancel(self):
        for record in self:
            if record.state == "confirmed":
                raise UserError(_("已确认的充值单不可直接作废，请执行余额冲销。"))
            record.write({"state": "cancelled"})
        return True
