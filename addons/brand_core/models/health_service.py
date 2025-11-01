# -*- coding: utf-8 -*-
from odoo import _, models
from odoo.exceptions import UserError
from odoo.fields import Command


class BrandCoreHealthService(models.AbstractModel):
    """健康检查服务：确保品牌平台演示基础配置齐备。"""

    _name = "brand.core.health.service"
    _description = "品牌平台健康检查服务"

    def run_health_check(self):
        env = self.env
        actions = []
        imd_sudo = env["ir.model.data"].sudo()

        def attach_xmlid(model, xmlid):
            module, name = xmlid.split(".")
            if not imd_sudo.search([("module", "=", module), ("name", "=", name)]):
                imd_sudo.create(
                    {
                        "module": module,
                        "name": name,
                        "model": model._name,
                        "res_id": model.id,
                        "noupdate": True,
                    }
                )

        brand_company = env.ref("brand_core.company_brand_hq", raise_if_not_found=False)
        if not brand_company:
            brand_company = env.ref("base.main_company", raise_if_not_found=False) or env.company
            attach_xmlid(brand_company, "brand_core.company_brand_hq")
            actions.append(_("绑定品牌总部到当前主公司。"))

        def ensure_child_company(xmlid, name, street, phone):
            company = env.ref(xmlid, raise_if_not_found=False)
            if company:
                return company
            company = env["res.company"].search(
                [("name", "=", name), ("parent_id", "=", brand_company.id)], limit=1
            )
            if not company:
                company = env["res.company"].create(
                    {
                        "name": name,
                        "parent_id": brand_company.id,
                        "street": street,
                        "phone": phone,
                    }
                )
                company.partner_id.write({"street": street, "phone": phone})
                actions.append(_("创建 %s 公司。") % name)
            attach_xmlid(company, xmlid)
            return company

        store_company = ensure_child_company(
            "brand_core.company_store_bund",
            "上海外滩旗舰门店",
            "上海市黄浦区中山东一路 99 号",
            "021-50009999",
        )
        store_company_jingan = ensure_child_company(
            "brand_core.company_store_jingan",
            "上海静安庭院门店",
            "上海市静安区延平路 66 号",
            "021-50007777",
        )

        Users = env["res.users"].with_context(no_reset_password=True)
        admin_user = env.ref("brand_core.user_brand_admin", raise_if_not_found=False)
        if not admin_user:
            admin_user = env.ref("base.user_admin", raise_if_not_found=False)
            if admin_user:
                attach_xmlid(admin_user, "brand_core.user_brand_admin")
                actions.append(_("将系统管理员映射为品牌管理员。"))
        if admin_user:
            admin_user.write(
                {
                    "company_id": brand_company.id,
                    "company_ids": [
                        Command.set([brand_company.id, store_company.id, store_company_jingan.id])
                    ],
                }
            )
            admin_user.write(
                {
                    "groups_id": [
                        (4, env.ref("brand_core.group_brand_platform_admin").id)
                    ]
                }
            )

        portal_user = env.ref("brand_core.user_portal_manager", raise_if_not_found=False)
        if not portal_user:
            portal_user = Users.search([("login", "=", "portal_manager")], limit=1)
        if not portal_user:
            partner = env["res.partner"].create(
                {
                    "name": "互通门户经理",
                    "email": "portal@brand-suite.cn",
                    "phone": "021-50008802",
                    "company_id": brand_company.id,
                }
            )
            portal_user = Users.create(
                {
                    "name": "互通门户经理",
                    "login": "portal_manager",
                    "password": "portal_manager",
                    "lang": "zh_CN",
                    "email": "portal@brand-suite.cn",
                    "partner_id": partner.id,
                    "company_id": brand_company.id,
                    "company_ids": [Command.set([brand_company.id])],
                    "groups_id": [
                        Command.set(
                            [
                                env.ref("brand_core.group_brand_portal_manager").id,
                                env.ref("base.group_portal").id,
                            ]
                        )
                    ],
                }
            )
            actions.append(_("创建互通门户经理账号。"))
            attach_xmlid(portal_user, "brand_core.user_portal_manager")

        # 陈化仓示例
        cellar_model = env["brand.core.cellar"].with_context(tracking_disable=True)
        if not cellar_model.search_count([]):
            cellar_model.create(
                {
                    "name": "品牌总部陈化仓",
                    "company_id": brand_company.id,
                    "manager_id": admin_user.id,
                    "temperature_target": 18.0,
                    "humidity_target": 68.0,
                    "note": "品牌总部样品存储仓，演示互通配置。",
                }
            )
            cellar_model.create(
                {
                    "name": "静安门店地下陈化仓",
                    "company_id": store_company_jingan.id,
                    "manager_id": portal_user.id,
                    "temperature_target": 19.5,
                    "humidity_target": 70.0,
                    "note": "静安门店陈化仓，展示跨店互通示例。",
                }
            )
            actions.append(_("补充陈化仓示例数据。"))

        link_group = env.ref("brand_core.link_group_demo", raise_if_not_found=False)
        if not link_group:
            link_group = env["store.link.group"].search(
                [("name", "=", "品牌示例互通组")], limit=1
            )
        if not link_group:
            link_group = env["store.link.group"].create(
                {
                    "name": "品牌示例互通组",
                    "company_id": brand_company.id,
                    "owner_id": admin_user.id,
                    "share_inventory": True,
                    "share_member": True,
                    "share_finance": True,
                    "member_company_ids": [
                        Command.set(
                            [brand_company.id, store_company.id, store_company_jingan.id]
                        )
                    ],
                }
            )
            actions.append(_("创建品牌示例互通组。"))
            attach_xmlid(link_group, "brand_core.link_group_demo")
        if link_group.state != "active":
            if link_group.state == "draft":
                link_group.action_submit()
            if link_group.state == "pending":
                link_group.action_approve()
            if link_group.state != "active":
                raise UserError(_("互通组审批流程未能自动完成，请检查记录。"))

        if actions:
            message = "\n".join(f"- {item}" for item in actions)
        else:
            message = _("所有关键配置均已就绪。")

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("品牌互通健康检查"),
                "message": message,
                "type": "success",
                "sticky": False,
            },
        }
