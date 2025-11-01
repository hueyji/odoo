# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class BrandCoreCompanyInitWizard(models.TransientModel):
    """向导：快速生成品牌总部、加盟门店与投资人虚拟公司结构。"""

    _name = "brand.core.company.init.wizard"
    _description = "品牌多公司初始化向导"

    brand_name = fields.Char(
        string="品牌总部名称",
        required=True,
        default="雪茄威士忌品牌总部",
        help="将创建/更新为所有加盟门店的父公司。",
    )
    store_names = fields.Text(
        string="加盟门店名称列表",
        required=True,
        default="上海外滩旗舰门店\n上海新天地体验店",
        help="每行一个门店名称，向导会为每个名称创建公司并设置父公司为品牌总部。",
    )
    create_investor_company = fields.Boolean(
        string="包含投资人虚拟公司",
        default=True,
        help="勾选后，会自动创建品牌投资人虚拟公司用于门户互通。",
    )
    investor_company_name = fields.Char(
        string="投资人虚拟公司名称",
        default="品牌投资人虚拟公司",
    )
    assign_current_user = fields.Boolean(
        string="将当前用户加入新公司",
        default=True,
        help="将当前用户的可访问公司更新为包含品牌总部与新门店，并把默认公司设置为品牌总部。",
    )

    @api.constrains("store_names")
    def _check_store_names(self):
        for wizard in self:
            lines = wizard._normalized_store_names()
            if not lines:
                raise ValidationError(_("请至少填写一个加盟门店名称。"))

    @api.constrains("create_investor_company", "investor_company_name")
    def _check_investor_company_name(self):
        for wizard in self:
            if wizard.create_investor_company and not wizard.investor_company_name:
                raise ValidationError(_("请填写投资人虚拟公司名称。"))

    def _normalized_store_names(self):
        """规范化门店名称列表，过滤空行。"""
        self.ensure_one()
        return [line.strip() for line in (self.store_names or "").splitlines() if line.strip()]

    def _prepare_company_vals(self, name, parent):
        """构造公司创建字段，保留父子结构。"""
        return {
            "name": name,
            "parent_id": parent.id if parent else False,
        }

    def _get_or_create_company(self, name, parent=None):
        """按名称查找或创建公司，保持父公司一致。"""
        Company = self.env["res.company"].sudo()
        company = Company.search([("name", "=", name)], limit=1)
        if company:
            if parent and company.parent_id != parent:
                company.parent_id = parent
            return company
        vals = self._prepare_company_vals(name, parent)
        return Company.create(vals)

    def action_initialize(self):
        """执行初始化流程，返回公司列表视图。"""
        self.ensure_one()
        companies = self.env["res.company"].sudo()

        brand_company = self._get_or_create_company(self.brand_name)
        created_companies = companies.browse()

        for store_name in self._normalized_store_names():
            store_company = self._get_or_create_company(store_name, parent=brand_company)
            created_companies |= store_company

        investor_company = companies.browse()
        if self.create_investor_company:
            investor_company = self._get_or_create_company(
                self.investor_company_name, parent=brand_company
            )
            created_companies |= investor_company

        if self.assign_current_user:
            self._assign_user_companies(brand_company, created_companies)

        all_company_ids = (brand_company | created_companies).ids
        message = self._build_feedback_message(brand_company, created_companies, investor_company)
        self.env.user.notify_success(message_body=message)

        return {
            "type": "ir.actions.act_window",
            "name": _("新建公司"),
            "res_model": "res.company",
            "view_mode": "tree,form",
            "domain": [("id", "in", all_company_ids)],
            "target": "current",
        }

    def _assign_user_companies(self, brand_company, extra_companies):
        """将当前用户加入新公司集合，并将默认公司设置为品牌总部。"""
        user = self.env.user.sudo()
        allowed_companies = (user.company_ids | brand_company | extra_companies).sorted()
        user.write(
            {
                "company_id": brand_company.id,
                "company_ids": [(6, 0, allowed_companies.ids)],
            }
        )

    def _build_feedback_message(self, brand_company, created_companies, investor_company):
        """生成操作完成后的提示消息。"""
        store_list = ", ".join(created_companies.filtered(lambda c: c != investor_company).mapped("name"))
        parts = [
            _("品牌总部：%s") % brand_company.name,
            _("加盟门店：%s") % (store_list or _("无新增门店")),
        ]
        if investor_company:
            parts.append(_("投资人虚拟公司：%s") % investor_company.name)
        return "<br/>".join(parts)
