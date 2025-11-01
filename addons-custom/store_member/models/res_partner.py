from odoo import api, fields, models, _
from odoo.exceptions import UserError


class StoreMemberPreference(models.Model):
    _name = "store.member.preference"
    _description = "会员偏好标签"
    _order = "sequence, name"

    name = fields.Char(string="偏好名称", required=True, translate=True)
    sequence = fields.Integer(string="显示顺序", default=10)
    description = fields.Text(string="说明")
    active = fields.Boolean(default=True, string="启用")

    _sql_constraints = [
        ("name_unique", "unique(name)", "会员偏好标签名称已存在。"),
    ]


class ResPartner(models.Model):
    _inherit = "res.partner"

    is_store_member = fields.Boolean(
        string="门店会员",
        help="标识该联系人是否参与门店会员体系。",
    )
    member_level_id = fields.Many2one(
        "store.member.level",
        string="会员等级",
        tracking=True,
    )
    member_code = fields.Char(
        string="会员编号",
        copy=False,
        index=True,
        help="系统自动生成的唯一会员编号，用于对外接口。",
    )
    member_origin_company_id = fields.Many2one(
        "res.company",
        string="来源门店",
        help="记录首次成为会员的门店，公司管理员可见。",
    )
    member_preference_ids = fields.Many2many(
        "store.member.preference",
        "store_member_preference_rel",
        "partner_id",
        "preference_id",
        string="品味偏好",
        help="用于陈化推荐与众筹推送。",
    )
    member_taboo = fields.Char(
        string="禁忌说明",
        help="用于标注会员忌讳或特殊要求，展示时需要遮蔽。",
    )
    investor_profile = fields.Selection(
        [
            ("conservative", "保守型"),
            ("balanced", "平衡型"),
            ("aggressive", "进取型"),
        ],
        string="投资人画像",
        help="品牌方用于众筹推荐的画像标签。",
    )
    enable_crowdfunding = fields.Boolean(
        string="允许参与众筹",
        default=True,
    )
    member_wallet_ids = fields.One2many(
        "store.member.wallet",
        "partner_id",
        string="会员余额账户",
    )
    member_balance_log_ids = fields.One2many(
        "store.member.balance.log",
        "partner_id",
        string="余额日志",
        readonly=True,
    )
    member_cash_balance = fields.Monetary(
        string="储值余额",
        compute="_compute_member_balances",
        currency_field="member_currency_id",
        store=True,
    )
    member_crowdfunding_balance = fields.Monetary(
        string="众筹收益余额",
        compute="_compute_member_balances",
        currency_field="member_currency_id",
        store=True,
    )
    member_currency_id = fields.Many2one(
        "res.currency",
        string="余额币种",
        compute="_compute_member_currency",
        store=True,
    )
    member_total_spent = fields.Monetary(
        string="累计消费",
        currency_field="member_currency_id",
        help="用于等级升级的累计消费额，待 Team F 订单结账时更新。",
        tracking=True,
    )
    member_sensitive_mask = fields.Boolean(
        string="遮蔽敏感信息",
        default=True,
        help="开启时 Portal 仅展示敏感字段的部分内容。",
    )

    _sql_constraints = [
        ("member_code_unique", "unique(member_code)", "会员编号必须唯一。"),
    ]

    @api.depends("member_wallet_ids.balance", "member_wallet_ids.balance_type")
    def _compute_member_balances(self):
        for partner in self:
            cash = 0.0
            crowdfunding = 0.0
            for wallet in partner.member_wallet_ids:
                if wallet.balance_type == "cash":
                    cash += wallet.balance
                elif wallet.balance_type == "crowdfunding":
                    crowdfunding += wallet.balance
            partner.member_cash_balance = cash
            partner.member_crowdfunding_balance = crowdfunding

    @api.depends("company_id", "member_origin_company_id")
    def _compute_member_currency(self):
        for partner in self:
            company = partner.member_origin_company_id or self.env.company
            partner.member_currency_id = company.currency_id

    def _check_can_manage_member(self):
        user = self.env.user
        if user.has_group("store_member.group_store_member_admin"):
            return True
        if user.has_group("store_member.group_store_member_user"):
            # 限制为公司范围
            for partner in self:
                if partner.company_id and partner.company_id != user.company_id:
                    raise UserError(_("您无权操作其他公司的会员资料。"))
            return True
        raise UserError(_("您缺少会员管理权限。"))

    def action_member_recharge(self, amount, balance_type="cash", note=None, reference=None, trace_payload=None):
        self._check_can_manage_member()
        if amount <= 0:
            raise UserError(_("充值金额必须大于 0。"))
        wallet_model = self.env["store.member.wallet"]
        for partner in self:
            company = partner.member_origin_company_id or self.env.company
            wallet = wallet_model.with_company(company).get_or_create_wallet(partner, company, balance_type)
            wallet._apply_balance_change(amount, "recharge", note=note, reference=reference, trace_payload=trace_payload)
        return True

    def action_member_consume(self, amount, balance_type="cash", note=None, reference=None, allow_negative=False, trace_payload=None):
        self._check_can_manage_member()
        if amount <= 0:
            raise UserError(_("扣减金额必须大于 0。"))
        wallet_model = self.env["store.member.wallet"]
        for partner in self:
            company = partner.member_origin_company_id or self.env.company
            wallet = wallet_model.with_company(company).get_or_create_wallet(partner, company, balance_type)
            if allow_negative:
                wallet.allow_negative = True
            wallet._apply_balance_change(-amount, "consume", note=note, reference=reference, trace_payload=trace_payload)
        return True

    def action_member_refund(self, amount, balance_type="cash", note=None, reference=None, trace_payload=None):
        self._check_can_manage_member()
        if amount <= 0:
            raise UserError(_("退款金额必须大于 0。"))
        wallet_model = self.env["store.member.wallet"]
        for partner in self:
            company = partner.member_origin_company_id or self.env.company
            wallet = wallet_model.with_company(company).get_or_create_wallet(partner, company, balance_type)
            wallet._apply_balance_change(amount, "refund", note=note, reference=reference, trace_payload=trace_payload)
        return True

    def toggle_member_flag(self):
        self._check_can_manage_member()
        for partner in self:
            new_state = not partner.is_store_member
            updates = {"is_store_member": new_state}
            if new_state and not partner.member_code:
                updates["member_code"] = partner._get_next_member_code()
            if new_state and not partner.member_origin_company_id:
                updates["member_origin_company_id"] = self.env.company.id
            partner.write(updates)
        return True

    def _get_next_member_code(self):
        return self.env["ir.sequence"].next_by_code("store.member.code")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("is_store_member") and not vals.get("member_code"):
                vals["member_code"] = self.env["ir.sequence"].next_by_code("store.member.code")
            if vals.get("is_store_member") and not vals.get("member_origin_company_id"):
                vals["member_origin_company_id"] = self.env.company.id
        partners = super().create(vals_list)
        return partners

    def write(self, vals):
        result = super().write(vals)
        if vals.get("is_store_member"):
            for partner in self:
                if partner.is_store_member and not partner.member_code:
                    partner.member_code = partner._get_next_member_code()
                if partner.is_store_member and not partner.member_origin_company_id:
                    partner.member_origin_company_id = self.env.company.id
        return result
