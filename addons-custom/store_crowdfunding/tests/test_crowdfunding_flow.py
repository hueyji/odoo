from odoo import fields
from odoo.tests import common


class TestCrowdfundingFlow(common.TransactionCase):
    def setUp(self):
        super().setUp()
        user = self.env.user
        user.groups_id |= self.env.ref("brand_core.group_brand_admin")
        user.groups_id |= self.env.ref("brand_core.group_brand_operator")
        user.groups_id |= self.env.ref("brand_core.group_store_manager")

        self.brand_company = self.env.ref("base.main_company")
        self.store_company = self.env["res.company"].create(
            {
                "name": "测试门店-众筹",
                "parent_id": self.brand_company.id,
                "partner_id": self.brand_company.partner_id.id,
            }
        )
        self.store_contact = self.env["res.partner"].create(
            {
                "name": "测试门店负责人",
                "company_id": self.store_company.id,
                "mobile": "13911112222",
            }
        )
        self.investor = self.env["res.partner"].create(
            {
                "name": "测试投资人",
                "mobile": "13900009999",
                "company_id": self.store_company.id,
            }
        )
        self.project = self.env["store.crowdfunding.project"].create(
            {
                "name": "测试众筹项目",
                "company_id": self.store_company.id,
                "brand_company_id": self.brand_company.id,
                "company_contact_id": self.store_contact.id,
                "target_amount": 40000,
                "funding_start_date": fields.Date.today(),
                "funding_end_date": fields.Date.today(),
            }
        )

    def test_project_lifecycle_and_finance(self):
        """门店提交项目→品牌审核→投资确认→分红执行，应完成资金流水联动。"""
        self.project.action_submit_review()
        self.assertEqual(self.project.state, "review")
        todo_activity = self.project.activity_ids.filtered(
            lambda act: act.activity_type_id == self.env.ref("mail.mail_activity_data_todo")
            and act.user_id == self.env.user
        )
        self.assertTrue(todo_activity, "提交审核后应为品牌方创建待办提醒")

        self.project.action_approve()
        self.assertEqual(self.project.state, "funding")

        investment = self.env["store.crowdfunding.investment"].create(
            {
                "project_id": self.project.id,
                "partner_id": self.investor.id,
                "amount": 50000,
            }
        )
        investment.action_confirm()
        self.assertEqual(investment.state, "confirmed")
        self.assertTrue(investment.transaction_id)
        self.assertEqual(investment.transaction_id.transaction_type, "crowdfunding")
        self.assertGreater(investment.amount_confirmed, 0)
        self.investor.invalidate_cache()
        self.assertEqual(self.investor.crowdfunding_investment_count, 1)
        self.assertEqual(self.investor.crowdfunding_investment_total, 50000)

        self.project.invalidate_cache()
        self.assertEqual(self.project.amount_confirmed, 50000)

        self.project.action_start_execution()
        self.assertEqual(self.project.state, "executing")

        dividend_plan = self.env["store.crowdfunding.dividend"].create(
            {
                "project_id": self.project.id,
                "plan_date": fields.Date.today(),
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "investment_id": investment.id,
                            "amount": 6000,
                        },
                    )
                ],
            }
        )
        dividend_plan.action_confirm()
        self.assertEqual(dividend_plan.state, "scheduled")

        dividend_plan.action_execute()
        self.assertEqual(dividend_plan.state, "done")
        line = dividend_plan.line_ids[:1]
        self.assertTrue(line.payout_transaction_id)
        self.assertEqual(line.payout_transaction_id.transaction_type, "crowdfunding_dividend")
        self.assertLess(line.payout_transaction_id.amount, 0)
        self.assertTrue(line.is_paid)
