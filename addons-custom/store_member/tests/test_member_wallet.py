from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "store_member")
class TestStoreMemberWallet(TransactionCase):
    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.env.user.groups_id |= self.env.ref("store_member.group_store_member_admin")
        self.partner = self.env["res.partner"].create(
            {
                "name": "测试会员",
                "phone": "13700000003",
                "is_store_member": True,
                "member_origin_company_id": self.company.id,
            }
        )

    def test_toggle_assigns_member_code(self):
        partner = self.env["res.partner"].create({"name": "潜在会员"})
        partner.toggle_member_flag()
        self.assertTrue(partner.is_store_member, "切换后应成为会员")
        self.assertTrue(partner.member_code, "设为会员后必须生成会员编号")
        self.assertEqual(
            partner.member_origin_company_id,
            self.env.company,
            "设为会员时应记录来源门店",
        )

    def test_recharge_and_consume_flow(self):
        self.partner.action_member_recharge(500, note="测试充值")
        wallet = self.partner.member_wallet_ids.filtered(lambda w: w.balance_type == "cash")
        self.assertEqual(len(wallet), 1, "充值时应自动创建现金余额账户")
        wallet = wallet[0]
        self.assertEqual(wallet.balance, 500)
        logs = wallet.log_ids.sorted(key=lambda r: (r.create_date, r.id))
        last_log = logs[-1]
        self.assertEqual(last_log.transaction_type, "recharge")

        self.partner.action_member_consume(200, note="测试扣减")
        wallet = wallet.with_env(self.env).browse(wallet.id)
        self.assertEqual(wallet.balance, 300)
        logs = wallet.log_ids.sorted(key=lambda r: (r.create_date, r.id))
        last_log = logs[-1]
        self.assertEqual(last_log.transaction_type, "consume")

    def test_consume_without_balance_raise(self):
        with self.assertRaises(UserError):
            self.partner.action_member_consume(100, note="余额不足扣减")
