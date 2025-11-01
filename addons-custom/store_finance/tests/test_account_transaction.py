import json

from odoo import fields
from odoo.tests import HttpCase, tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestStoreAccountTransaction(TransactionCase):
    def setUp(self):
        super().setUp()
        self.company = self.env.ref("base.main_company")
        self.channel_cash = self.env.ref("store_finance.finance_channel_cash")

    def test_sequence_and_mapping(self):
        transaction = self.env["store.account.transaction"].create(
            {
                "transaction_type": "sale",
                "amount": 500.0,
                "payment_channel_id": self.channel_cash.id,
                "company_id": self.company.id,
            }
        )
        self.assertNotEqual(transaction.name, "/")
        self.assertEqual(transaction.account_map_id.transaction_type, "sale")
        self.assertEqual(transaction.account_id, transaction.account_map_id.account_id)
        self.assertEqual(transaction.state, "draft")

        transaction.action_confirm()
        self.assertEqual(transaction.state, "confirmed")

        transaction.action_cancel()
        self.assertEqual(transaction.state, "cancelled")

    def test_multi_currency_conversion_and_clearing(self):
        usd = self.env.ref("base.USD")
        rate_model = self.env["res.currency.rate"]
        rate_model.search(
            [("currency_id", "=", usd.id)]
        ).unlink()
        rate_model.create(
            {
                "name": fields.Date.today(),
                "currency_id": usd.id,
                "rate": 0.14,
            }
        )

        transaction = self.env["store.account.transaction"].create(
            {
                "transaction_type": "sale",
                "amount": 100.0,
                "currency_id": usd.id,
                "payment_channel_id": self.channel_cash.id,
                "company_id": self.company.id,
            }
        )
        transaction.action_confirm()
        expected_amount = usd._convert(
            100.0,
            self.company.currency_id,
            self.company,
            fields.Date.today(),
        )
        self.assertAlmostEqual(
            transaction.amount_company_currency,
            expected_amount,
            places=2,
        )

        clearing = self.env["store.finance.clearing"].create(
            {
                "company_id": self.company.id,
                "line_ids": [(0, 0, {"transaction_id": transaction.id})],
            }
        )
        clearing.action_confirm()
        self.assertEqual(clearing.state, "confirmed")
        self.assertEqual(transaction.clearing_id, clearing)
        clearing.action_cancel()
        self.assertEqual(transaction.clearing_id, False)


@tagged("post_install", "-at_install")
class TestFinanceApi(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")
        user_group = cls.env.ref("store_finance.group_store_finance_user")
        manager_group = cls.env.ref("store_finance.group_store_finance_manager")
        base_user_group = cls.env.ref("base.group_user")
        cls.channel_cash = cls.env.ref("store_finance.finance_channel_cash")

        cls.user_finance = cls.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "Finance User",
                "login": "finance_user",
                "password": "finance_pass",
                "email": "finance_user@example.com",
                "company_id": cls.company.id,
                "company_ids": [(6, 0, [cls.company.id])],
                "groups_id": [(6, 0, [base_user_group.id, user_group.id])],
            }
        )

        cls.user_manager = cls.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "Finance Manager",
                "login": "finance_manager",
                "password": "manager_pass",
                "email": "finance_manager@example.com",
                "company_id": cls.company.id,
                "company_ids": [(6, 0, [cls.company.id])],
                "groups_id": [(6, 0, [base_user_group.id, manager_group.id])],
            }
        )

        cls.user_no_access = cls.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "No Access",
                "login": "finance_guest",
                "password": "guest_pass",
                "email": "guest@example.com",
                "company_id": cls.company.id,
                "company_ids": [(6, 0, [cls.company.id])],
                "groups_id": [(6, 0, [base_user_group.id])],
            }
        )

    def _json_headers(self):
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def test_transaction_create_and_list(self):
        self.authenticate("finance_user", "finance_pass")
        payload = {
            "transaction_type": "sale",
            "amount": 888.8,
            "payment_channel_id": self.channel_cash.id,
            "description": "API 自动化测试",
            "auto_confirm": True,
        }
        response = self.url_open(
            "/api/v1/finance/transactions",
            data=json.dumps(payload),
            headers=self._json_headers(),
        )
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertIn("data", result)
        self.assertEqual(result["data"]["state"], "confirmed")
        self.assertEqual(result["data"]["payment_channel_id"], self.channel_cash.id)

        list_resp = self.url_open("/api/v1/finance/transactions?state=confirmed")
        self.assertEqual(list_resp.status_code, 200)
        list_result = list_resp.json()
        self.assertGreaterEqual(list_result["paging"]["total"], 1)

    def test_transaction_permission_denied(self):
        self.authenticate("finance_guest", "guest_pass")
        resp = self.url_open("/api/v1/finance/transactions")
        self.assertEqual(resp.status_code, 403)

    def test_clearing_create_and_export(self):
        transaction = self.env["store.account.transaction"].create(
            {
                "transaction_type": "sale",
                "amount": 188.0,
                "payment_channel_id": self.channel_cash.id,
                "company_id": self.company.id,
            }
        )
        transaction.action_confirm()
        self.authenticate("finance_manager", "manager_pass")
        payload = {
            "transaction_ids": [transaction.id],
            "note": "自动化清算",
            "auto_confirm": True,
        }
        response = self.url_open(
            "/api/v1/finance/clearing",
            data=json.dumps(payload),
            headers=self._json_headers(),
        )
        self.assertEqual(response.status_code, 200)
        result = response.json()
        clearing_id = result["data"]["id"]
        self.assertEqual(result["data"]["state"], "confirmed")
        self.assertEqual(result["data"]["total_transaction_count"], 1)

        export_resp = self.url_open(
            f"/api/v1/finance/clearing/{clearing_id}/export"
        )
        self.assertEqual(export_resp.status_code, 200)
        self.assertEqual(
            export_resp.headers["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertTrue(export_resp.content.startswith(b"PK"))

        approve_resp = self.url_open(
            f"/api/v1/finance/clearing/{clearing_id}/approve",
            data=json.dumps({}),
            headers=self._json_headers(),
        )
        self.assertEqual(approve_resp.status_code, 200)
        approve_result = approve_resp.json()
        self.assertEqual(approve_result["data"]["state"], "approved")
        self.assertEqual(
            approve_result["data"]["approved_by"],
            self.user_manager.id,
        )

    def test_clearing_create_permission_denied(self):
        transaction = self.env["store.account.transaction"].create(
            {
                "transaction_type": "sale",
                "amount": 120.0,
                "payment_channel_id": self.channel_cash.id,
                "company_id": self.company.id,
            }
        )
        transaction.action_confirm()
        self.authenticate("finance_user", "finance_pass")
        payload = {
            "transaction_ids": [transaction.id],
        }
        response = self.url_open(
            "/api/v1/finance/clearing",
            data=json.dumps(payload),
            headers=self._json_headers(),
        )
        self.assertEqual(response.status_code, 403)
