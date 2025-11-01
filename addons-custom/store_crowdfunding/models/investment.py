# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class StoreCrowdfundingInvestment(models.Model):
    _name = "store.crowdfunding.investment"
    _description = "众筹投资记录"
    _inherit = ["mail.thread", "mail.activity.mixin", "store.crowdfunding.wallet.mixin"]
    _order = "create_date desc"

    name = fields.Char(string="投资编号", default="/", copy=False, tracking=True)
    project_id = fields.Many2one(
        "store.crowdfunding.project",
        string="众筹项目",
        required=True,
        ondelete="cascade",
        index=True,
        tracking=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="投资人",
        required=True,
        domain=[("enable_investment", "=", True)],
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="公司",
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
    amount = fields.Monetary(
        string="投资金额",
        currency_field="currency_id",
        required=True,
        tracking=True,
    )
    investment_date = fields.Datetime(
        string="投资时间",
        default=fields.Datetime.now,
        tracking=True,
    )
    confirm_date = fields.Datetime(string="确认时间", readonly=True)
    payment_channel_id = fields.Many2one(
        "store.finance.payment.channel",
        string="支付渠道",
        domain="[('company_id', '=', company_id)]",
    )
    account_transaction_id = fields.Many2one(
        "store.account.transaction",
        string="财务流水",
        readonly=True,
        copy=False,
    )
    state = fields.Selection(
        [
            ("draft", "草稿"),
            ("confirmed", "已确认"),
            ("cancelled", "已取消"),
        ],
        string="状态",
        default="draft",
        tracking=True,
    )
    note = fields.Text(string="备注")

    _sql_constraints = [
        ("name_company_unique", "unique(name, company_id)", "同一公司内投资编号已存在。"),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env.ref(
            "store_crowdfunding.sequence_store_crowdfunding_investment", raise_if_not_found=False
        )
        for vals in vals_list:
            project_id = vals.get("project_id")
            if project_id and not vals.get("company_id"):
                project = self.env["store.crowdfunding.project"].browse(project_id)
                vals["company_id"] = project.company_id.id
            if vals.get("name") in (None, "/", _("新建投资")) and sequence:
                vals["name"] = sequence.next_by_id()
        return super().create(vals_list)

    @api.constrains("amount")
    def _check_amount(self):
        for record in self:
            if record.amount <= 0:
                raise ValidationError(_("投资金额必须大于 0。"))

    def action_confirm(self):
        Transaction = self.env["store.account.transaction"].sudo()
        for record in self:
            if record.state != "draft":
                raise ValidationError(_("仅草稿状态的投资可以确认。"))
            if record.project_id.state not in ("fundraising", "in_progress"):
                raise ValidationError(_("仅募集中或执行中的项目可以确认投资。"))
            if not record.partner_id.enable_investment:
                raise ValidationError(_("该投资人未开启众筹权限，无法确认投资。"))
            tx_vals = {
                "company_id": record.company_id.id,
                "currency_id": record.currency_id.id,
                "transaction_type": "crowdfunding_invest",
                "amount": record.amount,
                "payment_channel_id": record.payment_channel_id.id
                if record.payment_channel_id
                else False,
                "state": "draft",
                "related_model": "%s,%s" % (record._name, record.id),
                "description": _("众筹项目 %(project)s 投资款") % {"project": record.project_id.display_name},
            }
            transaction = Transaction.create(tx_vals)
            transaction.action_confirm()
            record.write(
                {
                    "state": "confirmed",
                    "confirm_date": fields.Datetime.now(),
                    "account_transaction_id": transaction.id,
                }
            )
            wallet_entry = record._post_member_wallet_entry(
                partner=record.partner_id,
                amount=-record.amount,
                description=_("众筹项目 %(project)s 投资支出") % {"project": record.project_id.display_name},
                extra_vals={"company_id": record.company_id.id},
            )
            if wallet_entry:
                record.message_post(
                    body=_("已同步会员钱包支出记录：%s") % getattr(wallet_entry, "display_name", wallet_entry.id)
                )
            record.project_id.message_post(
                body=_("投资 %(partner)s 已确认，金额 %(amount)s")
                % {
                    "partner": record.partner_id.display_name,
                    "amount": record.currency_id._format(record.amount),
                }
            )
        return True

    def action_cancel(self):
        for record in self:
            if record.state == "cancelled":
                continue
            if record.account_transaction_id and record.account_transaction_id.state == "confirmed":
                record.account_transaction_id.action_cancel()
            if record.state == "confirmed":
                wallet_entry = record._post_member_wallet_entry(
                    partner=record.partner_id,
                    amount=record.amount,
                    description=_("众筹项目 %(project)s 投资退款") % {"project": record.project_id.display_name},
                    extra_vals={"company_id": record.company_id.id},
                )
                if wallet_entry:
                    record.message_post(
                        body=_("已同步会员钱包退款记录：%s") % getattr(wallet_entry, "display_name", wallet_entry.id)
                    )
            record.write({"state": "cancelled"})
            record.project_id.message_post(
                body=_("投资 %(name)s 已取消。") % {"name": record.name}
            )
        return True
