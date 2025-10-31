from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    company_role = fields.Selection(
        selection=[
            ("brand", "品牌总部"),
            ("store", "加盟门店"),
            ("investor", "投资人虚拟公司"),
        ],
        string="公司角色",
        default="store",
        help="用于区分品牌总部、加盟门店及投资人虚拟实体，以便控制默认配置与互通范围。",
    )
    is_brand_template = fields.Boolean(
        string="品牌模板公司",
        help="若勾选，表示该公司作为品牌总部模板来源，为后续门店自动配置提供参考。",
    )
    store_owner_partner_id = fields.Many2one(
        "res.partner",
        string="门店老板",
        help="标记门店主要负责人或投资人，用于互通审批与联系方式展示。",
    )
    default_link_group_id = fields.Many2one(
        "store.link.group",
        string="默认互通组",
        help="设置该门店默认加入的互通组，用于库存与会员共享判定。",
    )
    aging_area_note = fields.Char(
        string="陈化仓配置",
        help="记录门店陈化仓位置或编号，供库存检查与互通组校验使用。",
    )

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        companies._ensure_partner_locale()
        companies._ensure_link_group_membership()
        return companies

    def write(self, vals):
        res = super().write(vals)
        keys = set(vals.keys())
        if {"company_role", "is_brand_template"} & keys:
            self._ensure_partner_locale()
        if "default_link_group_id" in keys:
            self._ensure_link_group_membership()
        return res

    def _ensure_partner_locale(self):
        """确保公司关联伙伴的语言与时区为中文与上海，便于初始化一致。"""
        for company in self:
            partner = company.partner_id
            if not partner:
                continue
            updates = {}
            if partner.lang != "zh_CN":
                updates["lang"] = "zh_CN"
            if partner.tz != "Asia/Shanghai":
                updates["tz"] = "Asia/Shanghai"
            if updates:
                partner.write(updates)

    def _ensure_link_group_membership(self):
        for company in self:
            group = company.default_link_group_id
            if group and company not in group.member_company_ids:
                group.sudo().write({"member_company_ids": [(4, company.id)]})
