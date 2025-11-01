from odoo import api, fields, models


class StoreSupplierPurchaseReport(models.Model):
    _name = "store.supplier.purchase.report"
    _description = "供应商采购分析"
    _auto = False
    _order = "purchase_amount_total desc"

    supplier_id = fields.Many2one("store.supplier", string="供应商档案", readonly=True)
    partner_id = fields.Many2one("res.partner", string="联系人", readonly=True)
    company_id = fields.Many2one("res.company", string="公司", readonly=True)
    contact_user_id = fields.Many2one("res.users", string="对接人", readonly=True)
    purchase_order_count = fields.Integer(string="采购订单数", readonly=True)
    purchase_amount_total = fields.Monetary(string="采购金额", readonly=True)
    last_purchase_date = fields.Date(string="最近采购", readonly=True)
    delivery_cycle_avg = fields.Float(string="平均交付周期（天）", readonly=True)
    on_time_rate = fields.Float(string="准时率（%）", readonly=True)
    rating_overall = fields.Float(string="综合评分", readonly=True)
    risk_level = fields.Selection(
        [
            ("low", "低风险"),
            ("medium", "中风险"),
            ("high", "高风险"),
        ],
        string="风险等级",
        readonly=True,
    )
    is_blacklisted = fields.Boolean(string="黑名单", readonly=True)
    currency_id = fields.Many2one("res.currency", string="币种", readonly=True)

    def init(self):
        self.env.cr.execute("DROP VIEW IF EXISTS store_supplier_purchase_report")
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW store_supplier_purchase_report AS (
                SELECT
                    ss.id AS id,
                    ss.id AS supplier_id,
                    ss.partner_id AS partner_id,
                    ss.company_id AS company_id,
                    ss.contact_user_id AS contact_user_id,
                    ss.purchase_order_count AS purchase_order_count,
                    ss.purchase_amount_total AS purchase_amount_total,
                    ss.last_purchase_date AS last_purchase_date,
                    ss.delivery_cycle_avg AS delivery_cycle_avg,
                    ss.on_time_rate AS on_time_rate,
                    ss.rating_overall AS rating_overall,
                    ss.risk_level AS risk_level,
                    ss.is_blacklisted AS is_blacklisted,
                    ss.currency_id AS currency_id
                FROM store_supplier ss
            )
            """
        )
