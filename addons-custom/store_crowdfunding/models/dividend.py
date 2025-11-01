# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class StoreCrowdfundingDividend(models.Model):
    _name = "store.crowdfunding.dividend"
    _description = "众筹分红计划"
    _inherit = ["mail.thread", "mail.activity.mixin", "store.crowdfunding.wallet.mixin"]
    _order = "planned_date asc, id asc"

    name = fields.Char(string="分红名称", required=True, tracking=True)
    project_id = fields.Many2one(
        "store.crowdfunding.project",
        string="众筹项目",
        required=True,
        ondelete="cascade",
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="所属公司",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    currency_id = fields.Many2one(
        related="project_id.currency_id",
        string="币种",
        readonly=True,
        store=True,
    )
    planned_date = fields.Date(string="计划执行日期", required=True, tracking=True)
    amount = fields.Monetary(
        string="计划金额",
        currency_field="currency_id",
        required=True,
        tracking=True,
    )
    state = fields.Selection(
        [
            ("draft", "草稿"),
            ("pending", "待执行"),
            ("paid", "已执行"),
            ("cancelled", "已取消"),
        ],
        string="状态",
        default="draft",
        tracking=True,
    )
    paid_date = fields.Date(string="执行日期", readonly=True)
    account_transaction_id = fields.Many2one(
        "store.account.transaction",
        string="财务流水",
        readonly=True,
        copy=False,
    )
    note = fields.Text(string="备注")
    payout_ids = fields.One2many(
        "store.crowdfunding.dividend.payout",
        "dividend_id",
        string="分红明细",
    )

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env.ref(
            "store_crowdfunding.sequence_store_crowdfunding_dividend", raise_if_not_found=False
        )
        for vals in vals_list:
            project_id = vals.get("project_id")
            if project_id and not vals.get("company_id"):
                project = self.env["store.crowdfunding.project"].browse(project_id)
                vals["company_id"] = project.company_id.id
            if not vals.get("name") and sequence:
                vals["name"] = sequence.next_by_id()
        return super().create(vals_list)

    @api.constrains("amount")
    def _check_amount(self):
        for record in self:
            if record.amount <= 0:
                raise ValidationError(_("分红金额必须大于 0。"))

    def action_set_pending(self):
        for record in self:
            if record.state != "draft":
                raise ValidationError(_("仅草稿分红可标记待执行。"))
            record.state = "pending"
        return True

    def action_execute(self):
        Transaction = self.env["store.account.transaction"].sudo()
        for record in self:
            if record.state not in ("draft", "pending"):
                raise ValidationError(_("仅草稿或待执行的分红可执行。"))
            if record.project_id.state not in ("in_progress", "closed"):
                raise ValidationError(_("项目需在执行或结项阶段方可发放分红。"))
            if record.account_transaction_id and record.account_transaction_id.state == "confirmed":
                raise ValidationError(_("分红流水已存在，无需重复执行。"))

            confirmed_investments = record.project_id.investment_ids.filtered(
                lambda inv: inv.state == "confirmed"
            )
            if not confirmed_investments:
                raise ValidationError(_("当前无已确认的投资记录，无法执行分红。"))

            total_invest = sum(confirmed_investments.mapped("amount"))
            if not total_invest:
                raise ValidationError(_("确认投资金额为 0，无法执行分红。"))

            tx_vals = {
                "company_id": record.company_id.id,
                "currency_id": record.currency_id.id,
                "transaction_type": "crowdfunding_dividend",
                "amount": record.amount,
                "payment_channel_id": False,
                "state": "draft",
                "related_model": "%s,%s" % (record._name, record.id),
                "description": _("众筹项目 %(project)s 分红发放") % {"project": record.project_id.display_name},
            }
            transaction = Transaction.create(tx_vals)
            transaction.action_confirm()

            record._generate_partner_payouts(confirmed_investments)

            record.write(
                {
                    "state": "paid",
                    "paid_date": fields.Date.today(),
                    "account_transaction_id": transaction.id,
                }
            )
            record.project_id.message_post(
                body=_("分红 %(name)s 已执行，金额 %(amount)s")
                % {
                    "name": record.name,
                    "amount": record.currency_id._format(record.amount),
                }
            )
        return True

    def action_cancel(self):
        for record in self:
            if record.state == "paid":
                raise ValidationError(_("已执行的分红无法取消，请创建冲销凭证。"))
            if record.account_transaction_id and record.account_transaction_id.state == "confirmed":
                record.account_transaction_id.action_cancel()
            record.state = "cancelled"
        return True

    def _generate_partner_payouts(self, confirmed_investments):
        """根据投资额拆分分红，并尝试同步会员钱包。"""
        self.ensure_one()
        total_invest = sum(confirmed_investments.mapped("amount"))
        partner_amount_map = {}
        for investment in confirmed_investments:
            partner_amount_map.setdefault(investment.partner_id, 0.0)
            partner_amount_map[investment.partner_id] += investment.amount

        payouts_vals = []
        allocated_total = 0.0
        partners = sorted(partner_amount_map.keys(), key=lambda partner: partner.id)
        # 确保最后一位承担舍入差值
        for index, partner in enumerate(partners):
            invest_amount = partner_amount_map[partner]
            if not invest_amount:
                continue
            if index == len(partners) - 1:
                payout_amount = self.amount - allocated_total
            else:
                ratio = invest_amount / total_invest
                payout_amount = self.currency_id.round(self.amount * ratio)
                allocated_total += payout_amount
            if not payout_amount:
                continue
            payouts_vals.append(
                {
                    "partner": partner,
                    "investment_amount": invest_amount,
                    "amount": payout_amount,
                }
            )

        # 清理旧数据，重新生成
        if self.payout_ids:
            self.payout_ids.unlink()

        Payout = self.env["store.crowdfunding.dividend.payout"].sudo()
        for item in payouts_vals:
            payout = Payout.create(
                {
                    "dividend_id": self.id,
                    "partner_id": item["partner"].id,
                    "company_id": self.company_id.id,
                    "amount": item["amount"],
                    "investment_amount": item["investment_amount"],
                }
            )
            wallet_entry = self._post_member_wallet_entry(
                partner=item["partner"],
                amount=item["amount"],
                description=_("众筹项目 %(project)s 分红入账") % {"project": self.project_id.display_name},
            )
            if wallet_entry:
                payout.wallet_entry_reference = str(getattr(wallet_entry, "id", wallet_entry))
