# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    enable_investment = fields.Boolean(
        string="允许参与众筹",
        help="开启后，该会员可在门户参与众筹投资。",
    )
    crowdfunding_investment_ids = fields.One2many(
        "store.crowdfunding.investment",
        "partner_id",
        string="众筹投资记录",
    )
    crowdfunding_total_amount = fields.Monetary(
        string="众筹累计投资",
        currency_field="crowdfunding_currency_id",
        compute="_compute_crowdfunding_statistics",
        store=True,
        compute_sudo=True,
    )
    crowdfunding_investment_count = fields.Integer(
        string="投资笔数",
        compute="_compute_crowdfunding_statistics",
        store=True,
        compute_sudo=True,
    )
    crowdfunding_last_invest_date = fields.Datetime(
        string="最近投资时间",
        compute="_compute_crowdfunding_statistics",
        store=True,
        compute_sudo=True,
    )
    crowdfunding_dividend_total = fields.Monetary(
        string="累计分红收益",
        currency_field="crowdfunding_currency_id",
        compute="_compute_crowdfunding_statistics",
        store=True,
        compute_sudo=True,
    )
    crowdfunding_dividend_count = fields.Integer(
        string="分红次数",
        compute="_compute_crowdfunding_statistics",
        store=True,
        compute_sudo=True,
    )
    crowdfunding_currency_id = fields.Many2one(
        "res.currency",
        string="众筹统计币种",
        compute="_compute_crowdfunding_currency",
        store=True,
        compute_sudo=True,
    )

    @api.depends("company_id")
    def _compute_crowdfunding_currency(self):
        for partner in self:
            partner.crowdfunding_currency_id = (
                partner.company_id.currency_id
                if partner.company_id
                else self.env.company.currency_id
            )

    @api.depends(
        "crowdfunding_investment_ids.state",
        "crowdfunding_investment_ids.amount",
        "crowdfunding_investment_ids.confirm_date",
        "crowdfunding_investment_ids.project_id.dividend_plan_ids.state",
        "crowdfunding_investment_ids.project_id.dividend_plan_ids.payout_ids.amount",
        "crowdfunding_investment_ids.project_id.dividend_plan_ids.payout_ids.partner_id",
    )
    def _compute_crowdfunding_statistics(self):
        for partner in self:
            confirmed = partner.crowdfunding_investment_ids.filtered(
                lambda inv: inv.state == "confirmed"
            )
            partner.crowdfunding_total_amount = sum(confirmed.mapped("amount"))
            partner.crowdfunding_last_invest_date = (
                max(confirmed.mapped("confirm_date")) if confirmed else False
            )
            partner.crowdfunding_investment_count = len(confirmed)

            payouts = self.env["store.crowdfunding.dividend.payout"].sudo().search(
                [("partner_id", "=", partner.id), ("dividend_id.state", "=", "paid")]
            )
            partner.crowdfunding_dividend_total = sum(payouts.mapped("amount"))
            partner.crowdfunding_dividend_count = len(payouts)

    def get_crowdfunding_summary(self):
        self.ensure_one()
        confirmed_amount = sum(
            self.crowdfunding_investment_ids.filtered(lambda inv: inv.state == "confirmed").mapped("amount")
        )
        payouts_amount = sum(
            self.env["store.crowdfunding.dividend.payout"]
            .sudo()
            .search([("partner_id", "=", self.id)])
            .mapped("amount")
        )
        return {
            "confirmed_amount": confirmed_amount,
            "stored_amount": self.crowdfunding_total_amount,
            "investment_count": self.crowdfunding_investment_count,
            "dividend_amount": self.crowdfunding_dividend_total,
            "dividend_count": self.crowdfunding_dividend_count,
        }

    def check_crowdfunding_consistency(self):
        self.ensure_one()
        summary = self.get_crowdfunding_summary()
        rounding = self.crowdfunding_currency_id.rounding or self.env.company.currency_id.rounding
        delta = abs(summary["confirmed_amount"] - summary["stored_amount"])
        return delta > rounding
