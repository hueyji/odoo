# -*- coding: utf-8 -*-
from odoo import api, fields, models


class StoreCrowdfundingDividendPayout(models.Model):
    _name = "store.crowdfunding.dividend.payout"
    _description = "众筹分红明细"
    _order = "dividend_id, partner_id"

    dividend_id = fields.Many2one(
        "store.crowdfunding.dividend",
        string="分红计划",
        required=True,
        ondelete="cascade",
    )
    project_id = fields.Many2one(
        "store.crowdfunding.project",
        string="众筹项目",
        related="dividend_id.project_id",
        store=True,
        readonly=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="投资人",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="所属公司",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    currency_id = fields.Many2one(
        related="dividend_id.currency_id",
        string="币种",
        readonly=True,
        store=True,
    )
    amount = fields.Monetary(
        string="分红金额",
        currency_field="currency_id",
        required=True,
    )
    allocation_ratio = fields.Float(
        string="分红占比(%)",
        compute="_compute_allocation_ratio",
        store=True,
        help="本笔分红金额占该投资人已确认投资额的比例。",
    )
    investment_amount = fields.Monetary(
        string="对应投资额",
        currency_field="currency_id",
        help="该投资人用于计算本次分红的确认投资额。",
    )
    wallet_entry_reference = fields.Char(
        string="会员钱包记录",
        help="记录与 store.member.wallet 的衔接 ID（如存在）。",
    )

    _sql_constraints = [
        (
            "dividend_partner_unique",
            "unique(dividend_id, partner_id)",
            "同一分红计划下的投资人只能出现一次。",
        )
    ]

    @api.depends("amount", "investment_amount")
    def _compute_allocation_ratio(self):
        for record in self:
            if record.investment_amount:
                record.allocation_ratio = (record.amount / record.investment_amount) * 100
            else:
                record.allocation_ratio = 0.0
