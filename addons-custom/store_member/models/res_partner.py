from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ResPartner(models.Model):
    _inherit = "res.partner"

    MEMBER_LEVEL_SELECTION = [
        ("standard", "标准会员"),
        ("silver", "银卡会员"),
        ("gold", "金卡会员"),
        ("diamond", "钻石会员"),
        ("vip", "尊享会员"),
    ]

    member_level = fields.Selection(
        selection=MEMBER_LEVEL_SELECTION,
        string="会员等级",
        default="standard",
        tracking=True,
    )
    preference_tag_ids = fields.Many2many(
        "res.partner.category",
        "res_partner_pref_tag_rel",
        "partner_id",
        "category_id",
        string="偏好标签",
        help="可复用 Odoo 的标签，用于标记口味、偏好等信息。",
    )
    origin_store_id = fields.Many2one(
        "res.company",
        string="首访门店",
        tracking=True,
        help="记录会员首次消费的门店公司，品牌侧用于统计来源。",
    )
    member_balance = fields.Monetary(
        string="储值余额",
        currency_field="member_balance_currency_id",
        tracking=True,
        help="门店或互通组可使用的储值金额。",
        groups="store_member.group_member_sensitive",
    )
    member_balance_currency_id = fields.Many2one(
        "res.currency",
        string="储值币种",
        default=lambda self: self.env.company.currency_id.id,
        groups="store_member.group_member_sensitive",
    )
    investor_profile = fields.Html(
        string="投资人画像",
        sanitize=True,
        help="记录投资偏好、风险等级、沟通记录等信息。",
        groups="store_member.group_member_sensitive",
    )
    enable_investment = fields.Boolean(
        string="允许参与众筹",
        tracking=True,
        default=True,
        help="门店可控制该会员是否能在互通组内参与众筹项目。",
    )
    share_with_group_ids = fields.Many2many(
        "store.link.group",
        "store_link_group_partner_rel",
        "partner_id",
        "group_id",
        string="互通组",
        help="标记该会员可见的互通组，用于跨门店共享余额或消费记录。",
        groups="store_member.group_member_sensitive",
    )
    portal_privacy_opt_out = fields.Boolean(
        string="拒绝跨店共享建议",
        help="会员在 Portal 端关闭共享后，门店无法通过互通组读取偏好信息。",
        tracking=True,
    )

    @api.constrains("member_balance")
    def _check_member_balance(self):
        for partner in self:
            if partner.member_balance and partner.member_balance < 0:
                raise ValidationError(_("会员储值余额不能为负数。"))

    # ------ 余额操作接口 ------

    def _check_member_company_access(self, company):
        self.ensure_one()
        if not company:
            raise UserError(_("缺少执行操作的门店公司。"))
        if self.env.is_superuser() or self.env.user.has_group("base.group_system"):
            return True
        brand_admin = self.env.user.has_group("brand_core.group_brand_admin")
        store_manager = self.env.user.has_group("brand_core.group_store_manager")
        if brand_admin:
            return True
        if not store_manager and self.env.user.company_id != company:
            raise UserError(_("只有所属门店或品牌授权人员可以操作会员余额。"))
        origin_company = self.origin_store_id
        if not origin_company:
            return True
        if origin_company:
            if origin_company == company:
                return True
            if origin_company.parent_id and origin_company.parent_id == company:
                return True
            if (
                company.parent_id
                and origin_company.parent_id
                and company.parent_id == origin_company.parent_id
            ):
                return True
        shared_groups = self.share_with_group_ids.filtered(
            lambda g: g.share_member and company in g.member_company_ids
        )
        if shared_groups:
            return True
        raise UserError(_("当前门店不在会员互通授权范围内，无法操作余额。"))

    def _change_member_balance(
        self,
        delta_amount,
        change_type,
        company=None,
        note=None,
        reference=None,
        extra_vals=None,
    ):
        self.ensure_one()
        company = company or self.env.company
        currency = self.member_balance_currency_id or company.currency_id
        self._check_member_company_access(company)
        if not currency:
            raise UserError(_("缺少储值币种配置。"))
        delta_amount = currency.round(delta_amount)
        if not delta_amount:
            raise UserError(_("余额变动金额不能为零。"))
        previous_balance = currency.round(self.member_balance or 0.0)
        new_balance = currency.round(previous_balance + delta_amount)
        if new_balance < 0:
            raise ValidationError(_("余额不足，无法完成扣减。"))
        with self.env.cr.savepoint():
            self.with_context(skip_balance_constrains=True).write(
                {
                    "member_balance": new_balance,
                    "member_balance_currency_id": currency.id,
                }
            )
            log_values = {
                "partner_id": self.id,
                "company_id": company.id,
                "operator_id": self.env.user.id,
                "change_type": change_type,
                "delta_amount": delta_amount,
                "balance_before": previous_balance,
                "balance_after": new_balance,
                "note": note,
                "reference": reference and f"{reference._name},{reference.id}"
                if reference
                else False,
                "currency_id": currency.id,
            }
            if extra_vals:
                log_values.update(extra_vals)
            log = self.env["store.member.balance.log"].create(log_values)
            return log

    def action_member_recharge(self, amount, company=None, note=None, reference=None):
        return self._change_member_balance(
            abs(amount), "recharge", company=company, note=note, reference=reference
        )

    def action_member_consume(self, amount, company=None, note=None, reference=None):
        return self._change_member_balance(
            -abs(amount), "consumption", company=company, note=note, reference=reference
        )

    def action_member_adjust(self, amount, company=None, note=None, reference=None):
        delta = amount if amount else 0.0
        change_type = "adjustment" if delta >= 0 else "adjustment"
        return self._change_member_balance(
            delta, change_type, company=company, note=note, reference=reference
        )

    def action_open_member_balance_log(self):
        self.ensure_one()
        return {
            "name": _("余额日志"),
            "type": "ir.actions.act_window",
            "res_model": "store.member.balance.log",
            "view_mode": "tree,form",
            "domain": [("partner_id", "=", self.id)],
            "context": {"default_partner_id": self.id},
        }

    def action_open_member_recharge(self):
        self.ensure_one()
        return {
            "name": _("会员充值单"),
            "type": "ir.actions.act_window",
            "res_model": "store.member.recharge",
            "view_mode": "tree,form",
            "domain": [("partner_id", "=", self.id)],
            "context": {
                "default_partner_id": self.id,
                "default_company_id": self.env.company.id,
            },
        }

    def action_open_phone_bind_wizard(self):
        self.ensure_one()
        return {
            "name": _("快速绑定手机号"),
            "type": "ir.actions.act_window",
            "res_model": "store.member.phone.bind.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_partner_id": self.id,
                "default_phone": self.phone,
                "default_mobile": self.mobile,
            },
        }
