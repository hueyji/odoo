from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestStoreFinance(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")
        cls.currency = cls.company.currency_id
        cls.channel_cash = cls.env.ref("store_finance.channel_cash_main_company")
        cls.channel_internal = cls.env.ref("store_finance.channel_internal_main_company")
        cls.other_company = cls.env["res.company"].create(
            {
                "name": "演示加盟店",
                "parent_id": cls.company.id,
            }
        )
        cls.link_group = cls.env["store.link.group"].create(
            {
                "name": "演示互通组",
                "member_company_ids": [
                    (6, 0, [cls.company.id, cls.other_company.id]),
                ],
                "share_finance": True,
            }
        )
        cls.env["store.finance.channel"].with_context(active_test=False).search(
            [
                ("company_id", "=", cls.other_company.id),
                ("channel_type", "=", "internal"),
            ]
        ).unlink()
        cls.env["store.account.transaction"]._find_default_channel(
            cls.other_company.id, preferred_type="internal", allow_create=True
        )

    def test_transaction_amount_non_zero(self):
        with self.assertRaises(ValidationError):
            self.env["store.account.transaction"].create(
                {
                    "company_id": self.company.id,
                    "currency_id": self.currency.id,
                    "transaction_type": "sale",
                    "channel_id": self.channel_cash.id,
                    "amount": 0.0,
                }
            )

    def test_recharge_confirmation(self):
        transaction = self.env["store.account.transaction"].create(
            {
                "company_id": self.company.id,
                "currency_id": self.currency.id,
                "transaction_type": "recharge",
                "channel_id": self.channel_cash.id,
                "amount": 850.0,
            }
        )
        transaction.action_set_pending()
        transaction.action_confirm()
        self.assertEqual(transaction.state, "confirmed")
        self.assertEqual(transaction.amount_in, 850.0)

    def test_refund_amount_sign_validation(self):
        transaction = self.env["store.account.transaction"].create(
            {
                "company_id": self.company.id,
                "currency_id": self.currency.id,
                "transaction_type": "refund",
                "channel_id": self.channel_cash.id,
                "amount": 90.0,
            }
        )
        with self.assertRaises(ValidationError):
            transaction.action_confirm()

    def test_internal_clearing_generates_dual_transactions(self):
        clearing = self.env["store.finance.clearing"].create(
            {
                "group_id": self.link_group.id,
                "source_company_id": self.company.id,
                "target_company_id": self.other_company.id,
                "currency_id": self.currency.id,
                "amount": 320.0,
                "channel_id": self.channel_internal.id,
                "memo": "互通余额对账",
            }
        )
        clearing.action_confirm()
        self.assertEqual(clearing.state, "confirmed")
        self.assertTrue(clearing.source_transaction_id)
        self.assertTrue(clearing.target_transaction_id)
        self.assertEqual(clearing.source_transaction_id.amount, -320.0)
        self.assertEqual(clearing.target_transaction_id.amount, 320.0)

    def test_internal_channel_unique_constraint(self):
        with self.assertRaises(ValidationError):
            self.env["store.finance.channel"].create(
                {
                    "name": "重复内部渠道",
                    "channel_type": "internal",
                    "company_id": self.company.id,
                }
            )
