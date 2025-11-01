# -*- coding: utf-8 -*-
import base64

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestCrowdfundingFlow(TransactionCase):
    def setUp(self):
        super().setUp()
        self.project_model = self.env["store.crowdfunding.project"]
        self.investment_model = self.env["store.crowdfunding.investment"]
        self.dividend_model = self.env["store.crowdfunding.dividend"]
        self.partner_model = self.env["res.partner"]
        self.attachment_model = self.env["ir.attachment"]

        self.project = self.project_model.create(
            {
                "name": "测试众筹项目",
                "goal_amount": 100.0,
                "minimum_amount": 80.0,
                "summary": "测试项目概述",
                "fundraising_start_date": fields.Date.today(),
                "fundraising_deadline": fields.Date.today(),
            }
        )

        attachment = self.attachment_model.create(
            {
                "name": "测试合同.txt",
                "datas": base64.b64encode("测试合同".encode("utf-8")),
                "res_model": self.project._name,
                "res_id": self.project.id,
                "mimetype": "text/plain",
            }
        )
        attachment.write(
            {
                "crowdfunding_watermarked": True,
                "crowdfunding_watermark_method": "manual",
            }
        )
        self.project.write(
            {
                "contract_attachment_ids": [(4, attachment.id)],
                "contract_watermark_status": "ready",
            }
        )
        self.partner = self.partner_model.create(
            {
                "name": "测试投资人",
                "enable_investment": True,
            }
        )
        self.partner2 = self.partner_model.create(
            {
                "name": "第二投资人",
                "enable_investment": True,
            }
        )

    def test_full_project_flow(self):
        self.project.action_submit_for_approval()
        self.assertEqual(self.project.state, "to_approve")

        self.project.action_approve()
        self.assertEqual(self.project.state, "fundraising")

        investment = self.investment_model.create(
            {
                "project_id": self.project.id,
                "partner_id": self.partner.id,
                "amount": 120.0,
            }
        )
        investment.action_confirm()
        self.assertEqual(investment.state, "confirmed")
        self.assertTrue(investment.account_transaction_id)
        self.assertEqual(self.partner.crowdfunding_total_amount, investment.amount)
        self.assertEqual(self.partner.crowdfunding_investment_count, 1)

        self.project.action_start_execution()
        self.assertEqual(self.project.state, "in_progress")

        dividend = self.dividend_model.create(
            {
                "project_id": self.project.id,
                "planned_date": fields.Date.today(),
                "amount": 30.0,
            }
        )
        dividend.action_execute()
        self.assertEqual(dividend.state, "paid")
        self.assertTrue(dividend.account_transaction_id)
        self.assertEqual(len(dividend.payout_ids), 1)
        self.assertEqual(self.partner.crowdfunding_dividend_total, dividend.amount)
        self.assertEqual(self.project.total_dividend_amount, dividend.amount)
        self.assertEqual(self.project.dividend_paid_count, 1)

        self.project.action_close()
        self.assertEqual(self.project.state, "closed")
        summary = self.partner.get_crowdfunding_summary()
        self.assertEqual(summary["stored_amount"], investment.amount)
        self.assertEqual(summary["dividend_amount"], dividend.amount)
        self.assertFalse(self.partner.check_crowdfunding_consistency())

    def test_close_requires_dividend_done(self):
        self.project.action_submit_for_approval()
        self.project.action_approve()
        self.investment_model.create(
            {
                "project_id": self.project.id,
                "partner_id": self.partner.id,
                "amount": 100.0,
            }
        ).action_confirm()
        self.project.action_start_execution()
        self.dividend_model.create(
            {
                "project_id": self.project.id,
                "planned_date": fields.Date.today(),
                "amount": 10.0,
                "state": "pending",
            }
        )
        with self.assertRaises(ValidationError):
            self.project.action_close()

    def test_dividend_payout_split(self):
        self.project.action_submit_for_approval()
        self.project.action_approve()
        inv1 = self.investment_model.create(
            {
                "project_id": self.project.id,
                "partner_id": self.partner.id,
                "amount": 120.0,
            }
        )
        inv1.action_confirm()
        inv2 = self.investment_model.create(
            {
                "project_id": self.project.id,
                "partner_id": self.partner2.id,
                "amount": 80.0,
            }
        )
        inv2.action_confirm()
        self.project.action_start_execution()
        dividend = self.dividend_model.create(
            {
                "project_id": self.project.id,
                "planned_date": fields.Date.today(),
                "amount": 100.0,
            }
        )
        dividend.action_execute()
        payouts = dividend.payout_ids.sorted(key=lambda rec: rec.partner_id.id)
        self.assertEqual(len(payouts), 2)
        self.assertAlmostEqual(payouts[0].amount + payouts[1].amount, dividend.amount)
        # 第一位投资 60%，第二位 40%
        self.assertAlmostEqual(payouts[0].amount, 60.0)
        self.assertAlmostEqual(payouts[1].amount, 40.0)
        self.assertEqual(self.partner.crowdfunding_dividend_total, payouts[0].amount)
        self.assertEqual(self.partner2.crowdfunding_dividend_total, payouts[1].amount)
        self.assertFalse(self.partner.check_crowdfunding_consistency())
        self.assertFalse(self.partner2.check_crowdfunding_consistency())

    def test_auto_watermark_generation(self):
        self.project.write({
            "contract_watermark_status": "pending",
            "watermark_method": "auto",
        })
        self.project.action_generate_watermark()
        self.assertEqual(self.project.contract_watermark_status, "ready")
        self.assertTrue(all(self.project.contract_attachment_ids.mapped("crowdfunding_watermarked")))
        self.assertEqual(self.project.watermark_method, "auto")
