from odoo.exceptions import UserError
from odoo.tests import TransactionCase


class TestBrandCoreAccess(TransactionCase):
    def setUp(self):
        super().setUp()
        self.brand_company = self.env["res.company"].create(
            {
                "name": "测试品牌总部",
                "company_role": "brand",
                "is_brand_template": True,
            }
        )
        self.store_company_1 = self.env["res.company"].create(
            {
                "name": "测试门店一号",
                "company_role": "store",
                "parent_id": self.brand_company.id,
            }
        )
        self.store_company_2 = self.env["res.company"].create(
            {
                "name": "测试门店二号",
                "company_role": "store",
                "parent_id": self.brand_company.id,
            }
        )

        no_mail_ctx = dict(self.env.context, no_reset_password=True)
        self.brand_admin = self.env["res.users"].with_context(no_mail_ctx).create(
            {
                "name": "品牌管理员",
                "login": "brand_admin_test",
                "email": "brand_admin@test.com",
                "groups_id": [
                    (6, 0, [self.env.ref("brand_core.group_brand_admin").id])
                ],
                "company_id": self.brand_company.id,
                "company_ids": [(6, 0, [self.brand_company.id])],
            }
        )
        self.store_manager = self.env["res.users"].with_context(no_mail_ctx).create(
            {
                "name": "门店负责人",
                "login": "store_manager_test",
                "email": "store_manager@test.com",
                "groups_id": [
                    (6, 0, [self.env.ref("brand_core.group_store_manager").id])
                ],
                "company_id": self.store_company_1.id,
                "company_ids": [(6, 0, [self.store_company_1.id])],
            }
        )

        self.group_visible = self.env["store.link.group"].create(
            {
                "name": "可见互通组",
                "brand_company_id": self.brand_company.id,
                "member_company_ids": [(6, 0, [self.store_company_1.id])],
                "owner_id": self.store_manager.partner_id.id,
            }
        )
        self.group_hidden = self.env["store.link.group"].create(
            {
                "name": "隐藏互通组",
                "brand_company_id": self.brand_company.id,
                "member_company_ids": [(6, 0, [self.store_company_2.id])],
            }
        )

    def test_store_manager_visibility(self):
        groups = self.env["store.link.group"].with_user(self.store_manager).search([])
        self.assertIn(
            self.group_visible,
            groups,
            "门店负责人应看到所属互通组",
        )
        self.assertNotIn(
            self.group_hidden,
            groups,
            "门店负责人不应看到其他互通组",
        )

    def test_application_flow_permissions(self):
        Application = self.env["store.link.group.application"]
        application = Application.with_user(self.store_manager).create(
            {
                "group_id": self.group_visible.id,
                "requested_member_ids": [(6, 0, [self.store_company_1.id])],
                "description": "申请说明",
                "share_inventory": True,
                "share_member": True,
                "share_finance": False,
            }
        )
        application.with_user(self.store_manager).action_submit()
        self.assertEqual(
            application.state,
            "submitted",
            "提交后状态应为待审批",
        )
        with self.assertRaises(UserError):
            application.with_user(self.store_manager).action_approve()

        application.with_user(self.brand_admin).action_approve()
        self.assertEqual(
            application.state,
            "approved",
            "品牌管理员审批后状态应为已通过",
        )
        self.assertEqual(
            application.group_id.state,
            "active",
            "审批通过后互通组应处于激活状态",
        )
