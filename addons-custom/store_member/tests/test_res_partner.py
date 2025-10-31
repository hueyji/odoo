from odoo.exceptions import UserError, ValidationError
from odoo.tests import common, tagged


@tagged("store_member", "post_install", "-at_install")
class TestResPartnerExtension(common.TransactionCase):
    def setUp(self):
        super().setUp()
        self.tag = self.env["res.partner.category"].create({"name": "雪茄偏好"})
        self.link_group = self.env["store.link.group"].create(
            {
                "name": "老板共享组",
                "member_company_ids": [(6, 0, self.env.company.ids)],
                "share_inventory": True,
                "share_member": True,
                "share_finance": False,
            }
        )
        self.other_company = self.env["res.company"].create({"name": "虹桥分店"})
        self.other_company_user = self.env["res.users"].with_context(
            no_reset_password=True
        ).create(
            {
                "name": "虹桥店长",
                "login": "store_manager_demo",
                "email": "store_manager_demo@example.com",
                "company_id": self.other_company.id,
                "company_ids": [(6, 0, [self.other_company.id])],
                "groups_id": [
                    (
                        6,
                        0,
                        [
                            self.env.ref("brand_core.group_store_manager").id,
                            self.env.ref("base.group_partner_manager").id,
                        ],
                    )
                ],
            }
        )

    def test_partner_membership_fields(self):
        partner = self.env["res.partner"].create(
            {
                "name": "测试会员",
                "member_level": "gold",
                "origin_store_id": self.env.company.id,
                "member_balance": 500,
                "preference_tag_ids": [(4, self.tag.id)],
                "enable_investment": True,
                "share_with_group_ids": [(4, self.link_group.id)],
            }
        )
        self.assertEqual(partner.member_level, "gold")
        self.assertEqual(partner.origin_store_id, self.env.company)
        self.assertEqual(partner.member_balance, 500)
        self.assertTrue(partner.enable_investment)
        self.assertIn(self.tag, partner.preference_tag_ids)
        self.assertIn(self.link_group, partner.share_with_group_ids)

    def test_member_balance_constraint(self):
        partner = self.env["res.partner"].create({"name": "余额校验会员"})
        with self.assertRaises(ValidationError):
            partner.write({"member_balance": -10})

    def test_member_recharge_creates_log(self):
        partner = self.env["res.partner"].create(
            {
                "name": "充值会员",
                "origin_store_id": self.env.company.id,
                "share_with_group_ids": [(4, self.link_group.id)],
            }
        )
        recharge = self.env["store.member.recharge"].create(
            {
                "partner_id": partner.id,
                "amount": 300,
                "payment_method": "wechat",
            }
        )
        recharge.action_confirm()
        self.assertEqual(partner.member_balance, 300)
        self.assertEqual(recharge.state, "confirmed")
        self.assertTrue(recharge.log_id)
        self.assertEqual(recharge.log_id.delta_amount, 300)

    def test_member_balance_requires_share_group(self):
        partner = self.env["res.partner"].create(
            {
                "name": "互通校验会员",
                "origin_store_id": self.env.company.id,
            }
        )
        with self.assertRaises(UserError):
            partner.with_user(self.other_company_user).action_member_recharge(
                100, company=self.other_company
            )

    def test_member_balance_allowed_for_shared_group(self):
        shared_group = self.env["store.link.group"].create(
            {
                "name": "共享余额组",
                "member_company_ids": [
                    (6, 0, [self.env.company.id, self.other_company.id])
                ],
                "share_member": True,
            }
        )
        partner = self.env["res.partner"].create(
            {
                "name": "共享会员",
                "origin_store_id": self.env.company.id,
                "share_with_group_ids": [(4, shared_group.id)],
            }
        )
        partner.with_user(self.other_company_user).action_member_recharge(
            120, company=self.other_company
        )
        self.assertEqual(partner.member_balance, 120)

    def test_phone_bind_wizard_sets_mobile_and_origin(self):
        partner = self.env["res.partner"].create({"name": "手机号会员"})
        wizard = self.env["store.member.phone.bind.wizard"].create(
            {
                "partner_id": partner.id,
                "mobile": "13800138000",
            }
        )
        wizard.action_confirm()
        self.assertEqual(partner.mobile, "13800138000")
        self.assertEqual(partner.origin_store_id, self.env.company)

    def test_phone_bind_duplicate_rejected(self):
        existing = self.env["res.partner"].create(
            {
                "name": "已有号码会员",
                "mobile": "13900139000",
            }
        )
        partner = self.env["res.partner"].create({"name": "待绑定会员"})
        wizard = self.env["store.member.phone.bind.wizard"].create(
            {
                "partner_id": partner.id,
                "mobile": "13900139000",
            }
        )
        with self.assertRaises(UserError):
            wizard.action_confirm()
