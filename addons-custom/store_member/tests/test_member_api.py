import json

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install", "store_member")
class TestStoreMemberApi(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        member_group = cls.env.ref("store_member.group_store_member_user")
        user_group = cls.env.ref("base.group_user")
        cls.api_user = cls.env["res.users"].create(
            {
                "name": "会员接口账号",
                "login": "member_api_user",
                "password": "member_api_user",
                "email": "member.api@example.com",
                "company_id": cls.company.id,
                "company_ids": [(6, 0, [cls.company.id])],
                "groups_id": [(6, 0, [member_group.id, user_group.id])],
            }
        )

    def _json_headers(self):
        return {"Content-Type": "application/json"}

    def test_member_bind_recharge_and_balance(self):
        self.authenticate("member_api_user", "member_api_user")
        bind_payload = {
            "phone": "13911112222",
            "name": "接口会员",
            "email": "api.member@example.com",
            "note": "API 测试绑定",
        }
        response = self.url_open(
            "/api/v1/members/bind",
            headers=self._json_headers(),
            data=json.dumps(bind_payload),
        )
        self.assertEqual(response.status_code, 200, response.text)
        member_data = response.json()["data"]["member"]
        self.assertTrue(member_data["id"])
        self.assertEqual(member_data["name"], "接口会员")
        member_id = member_data["id"]

        recharge_payload = {
            "member_id": member_id,
            "amount": 200,
            "reference": "RECHARGE-TEST",
            "note": "接口充值",
        }
        recharge_res = self.url_open(
            "/api/v1/members/recharge",
            headers=self._json_headers(),
            data=json.dumps(recharge_payload),
        )
        self.assertEqual(recharge_res.status_code, 200, recharge_res.text)
        recharge_member = recharge_res.json()["data"]["member"]
        self.assertEqual(recharge_member["member_cash_balance"], 200.0)

        balance_res = self.url_open(f"/api/v1/members/balance?member_id={member_id}")
        self.assertEqual(balance_res.status_code, 200, balance_res.text)
        balance_info = balance_res.json()["data"]["member"]
        self.assertEqual(balance_info["member_cash_balance"], 200.0)

        list_res = self.url_open("/api/v1/members?limit=1")
        self.assertEqual(list_res.status_code, 200, list_res.text)
        payload = list_res.json()["data"]
        self.assertGreaterEqual(payload["count"], 1)


@tagged("post_install", "-at_install", "store_member")
class TestStoreMemberPortal(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "门户会员",
                "phone": "13933334444",
                "email": "portal.member@example.com",
                "is_store_member": True,
                "member_origin_company_id": cls.company.id,
            }
        )
        cls.env["store.member.wallet"].sudo().create(
            {
                "partner_id": cls.partner.id,
                "company_id": cls.company.id,
                "balance_type": "cash",
                "balance": 1200,
                "sharing_scope": "link_group",
            }
        )
        cls.portal_user = cls.env["res.users"].create(
            {
                "name": "Portal Member",
                "login": "portal_member_user",
                "password": "portal_member_user",
                "email": "portal.member@example.com",
                "company_id": cls.company.id,
                "company_ids": [(6, 0, [cls.company.id])],
                "partner_id": cls.partner.id,
                "groups_id": [(6, 0, [cls.env.ref("base.group_portal").id])],
            }
        )

    def test_membership_portal_page(self):
        self.authenticate("portal_member_user", "portal_member_user")
        response = self.url_open("/my/membership")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("会员中心", response.text)
