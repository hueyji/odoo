# -*- coding: utf-8 -*-
import json

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestBrandCoreLinkGroupAPI(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.brand_company = cls.env.ref("base.main_company")
        cls.brand_company.write({"name": "测试品牌总部"})

        cls.store_company_a = cls.env["res.company"].create(
            {"name": "测试门店A", "parent_id": cls.brand_company.id}
        )

        cls.brand_admin = cls.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "品牌管理员 API",
                "login": "brand_admin_api",
                "password": "brand_admin_api",
                "company_id": cls.brand_company.id,
                "company_ids": [(6, 0, [cls.brand_company.id, cls.store_company_a.id])],
                "lang": "zh_CN",
                "groups_id": [(6, 0, [cls.env.ref("brand_core.group_brand_platform_admin").id])],
            }
        )

        cls.store_manager = cls.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "门店门户经理",
                "login": "store_manager_api",
                "password": "store_manager_api",
                "company_id": cls.store_company_a.id,
                "company_ids": [(6, 0, [cls.brand_company.id, cls.store_company_a.id])],
                "lang": "zh_CN",
                "groups_id": [(6, 0, [cls.env.ref("brand_core.group_brand_portal_manager").id])],
            }
        )

        cls.existing_group = (
            cls.env["store.link.group"]
            .with_context(mail_create_nolog=True)
            .create(
                {
                    "name": "现有互通组",
                    "company_id": cls.brand_company.id,
                    "owner_id": cls.brand_admin.id,
                    "share_inventory": True,
                    "member_company_ids": [
                        (6, 0, [cls.brand_company.id, cls.store_company_a.id])
                    ],
                }
            )
        )
        cls.existing_group.action_submit()

    def test_list_link_groups(self):
        self.authenticate(self.brand_admin.login, self.brand_admin.login)
        response = self.url_open("/api/v1/link-groups")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get("success"))
        self.assertGreaterEqual(data["data"]["total"], 1)
        self.assertIn("items", data["data"])

    def test_apply_and_approve_flow(self):
        self.authenticate(self.store_manager.login, self.store_manager.login)
        payload = {
            "name": "API 互通申请",
            "member_company_ids": [self.store_company_a.id],
            "share_inventory": True,
            "share_member": True,
        }
        response = self.url_open(
            "/api/v1/link-groups",
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertTrue(body.get("success"))
        new_group_id = body["data"]["id"]
        self.assertEqual(body["data"]["state"], "pending")

        # 门店用户无权审批
        unauthorized_resp = self.url_open(
            f"/api/v1/link-groups/{new_group_id}/approve",
            data=json.dumps({}),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(unauthorized_resp.status_code, 403)
        self.assertFalse(unauthorized_resp.json().get("success"))

        # 品牌管理员审批通过
        self.authenticate(self.brand_admin.login, self.brand_admin.login)
        approve_resp = self.url_open(
            f"/api/v1/link-groups/{new_group_id}/approve",
            data=json.dumps({}),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(approve_resp.status_code, 200)
        approve_body = approve_resp.json()
        self.assertTrue(approve_body.get("success"))
        self.assertEqual(approve_body["data"]["state"], "active")
