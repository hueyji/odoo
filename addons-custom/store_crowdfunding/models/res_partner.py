from odoo import _, api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    crowdfunding_investment_total = fields.Monetary(
        string="众筹累计认购",
        currency_field="member_balance_currency_id",
        compute="_compute_crowdfunding_stats",
        store=True,
        readonly=True,
        help="统计该会员已确认的众筹投资总额，使用会员储值币种显示。",
    )
    crowdfunding_investment_count = fields.Integer(
        string="众筹笔数",
        compute="_compute_crowdfunding_stats",
        store=True,
        readonly=True,
        help="该会员已确认的众筹投资记录数。",
    )
    crowdfunding_last_investment_date = fields.Date(
        string="最新众筹日期",
        compute="_compute_crowdfunding_stats",
        store=True,
        readonly=True,
        help="会员最近一次确认众筹投资的日期。",
    )

    @api.depends("store_crowdfunding_investment_ids.state", "store_crowdfunding_investment_ids.amount_confirmed")
    def _compute_crowdfunding_stats(self):
        partners = self.filtered(lambda p: p.ids)
        if not partners:
            return
        investment_model = self.env["store.crowdfunding.investment"]
        domain = [
            ("partner_id", "in", partners.ids),
            ("state", "=", "confirmed"),
        ]
        read_groups = investment_model.read_group(
            domain,
            ["partner_id", "amount_confirmed:sum", "investment_date:max"],
            ["partner_id"],
        )
        stats = {
            data["partner_id"][0]: {
                "amount": data["amount_confirmed"] or 0.0,
                "count": data["__count"] or 0,
                "last_date": data["investment_date"],
            }
            for data in read_groups
            if data.get("partner_id")
        }
        for partner in self:
            data = stats.get(partner.id, {})
            partner.crowdfunding_investment_total = data.get("amount", 0.0)
            partner.crowdfunding_investment_count = data.get("count", 0)
            partner.crowdfunding_last_investment_date = data.get("last_date")

    store_crowdfunding_investment_ids = fields.One2many(
        "store.crowdfunding.investment",
        "partner_id",
        string="众筹投资记录",
    )

    def action_open_crowdfunding_investment(self):
        self.ensure_one()
        action = self.env.ref("store_crowdfunding.action_store_crowdfunding_investment").read()[0]
        action["domain"] = [("partner_id", "=", self.id)]
        action.setdefault("context", {})
        action["context"].update(
            {
                "default_partner_id": self.id,
                "search_default_partner_id": self.id,
            }
        )
        return action
