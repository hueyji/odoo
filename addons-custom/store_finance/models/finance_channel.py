from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class StoreFinanceChannel(models.Model):
    _name = "store.finance.channel"
    _description = "门店支付渠道"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "sequence, name"
    _check_company_auto = True

    CHANNEL_TYPE_SELECTION = [
        ("cash", "现金"),
        ("stored_value", "储值余额"),
        ("pos", "POS 机"),
        ("third_party", "第三方支付"),
        ("internal", "内部结算"),
    ]

    name = fields.Char(string="渠道名称", required=True, tracking=True)
    code = fields.Char(
        string="渠道编码",
        required=True,
        tracking=True,
        help="公司内部唯一编码，用于对账与接口映射。",
    )
    channel_type = fields.Selection(
        selection=CHANNEL_TYPE_SELECTION,
        string="渠道类型",
        required=True,
        default="cash",
        tracking=True,
    )
    sequence = fields.Integer(string="显示顺序", default=10)
    company_id = fields.Many2one(
        "res.company",
        string="所属公司",
        required=True,
        default=lambda self: self.env.company.id,
        tracking=True,
    )
    auto_reconcile = fields.Boolean(
        string="需要日结对账",
        default=True,
        tracking=True,
        help="勾选后系统会提示每日核对渠道流水，内部结算可取消。"
    )
    active = fields.Boolean(default=True)
    note = fields.Text(string="备注")
    transaction_count = fields.Integer(
        string="关联流水数量",
        compute="_compute_transaction_count",
    )

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env.ref(
            "store_finance.seq_store_finance_channel",
            raise_if_not_found=False,
        )
        for vals in vals_list:
            if (not vals.get("code")) and sequence:
                vals["code"] = sequence.next_by_id()
        return super().create(vals_list)

    _sql_constraints = [
        (
            "channel_code_company_unique",
            "unique(code, company_id)",
            "同一公司下渠道编码必须唯一。",
        ),
    ]

    @api.constrains("channel_type", "company_id")
    def _check_internal_unique(self):
        for channel in self:
            if channel.channel_type != "internal":
                continue
            existing = self.search_count(
                [
                    ("id", "!=", channel.id),
                    ("company_id", "=", channel.company_id.id),
                    ("channel_type", "=", "internal"),
                    ("active", "=", True),
                ]
            )
            if existing:
                raise ValidationError(_("同一公司仅允许存在一个启用的内部结算渠道。"))

    def _compute_transaction_count(self):
        grouped = self.env["store.account.transaction"].read_group(
            [("channel_id", "in", self.ids)],
            ["channel_id"],
            ["channel_id"],
        )
        count_map = {item["channel_id"][0]: item["channel_id_count"] for item in grouped}
        for channel in self:
            channel.transaction_count = count_map.get(channel.id, 0)

    def action_view_transactions(self):
        self.ensure_one()
        action = self.env.ref("store_finance.action_store_account_transaction").read()[0]
        action["domain"] = [("channel_id", "=", self.id)]
        action.setdefault("context", {})
        action["context"].update(
            {
                "default_channel_id": self.id,
                "search_default_channel_id": self.id,
            }
        )
        return action
