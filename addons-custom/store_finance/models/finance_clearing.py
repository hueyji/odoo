from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class StoreFinanceClearing(models.Model):
    _name = "store.finance.clearing"
    _description = "互通内部清算"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    name = fields.Char(
        string="清算单号",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _("新清算单"),
        tracking=True,
    )
    date = fields.Date(
        string="清算日期",
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    group_id = fields.Many2one(
        "store.link.group",
        string="互通组",
        required=True,
        tracking=True,
    )
    source_company_id = fields.Many2one(
        "res.company",
        string="付款门店",
        required=True,
        tracking=True,
    )
    target_company_id = fields.Many2one(
        "res.company",
        string="收款门店",
        required=True,
        tracking=True,
    )
    amount = fields.Monetary(
        string="清算金额",
        currency_field="currency_id",
        required=True,
        tracking=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="币种",
        required=True,
        default=lambda self: self.env.company.currency_id.id,
    )
    channel_id = fields.Many2one(
        "store.finance.channel",
        string="结算渠道",
        domain="[('company_id', '=', source_company_id)]",
        tracking=True,
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
    memo = fields.Text(string="对账说明")
    source_transaction_id = fields.Many2one(
        "store.account.transaction",
        string="付款流水",
        readonly=True,
        copy=False,
    )
    target_transaction_id = fields.Many2one(
        "store.account.transaction",
        string="收款流水",
        readonly=True,
        copy=False,
    )
    transaction_ids = fields.Many2many(
        "store.account.transaction",
        "store_finance_clearing_transaction_rel",
        "clearing_id",
        "transaction_id",
        string="关联流水",
        readonly=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env.ref(
            "store_finance.seq_store_finance_clearing",
            raise_if_not_found=False,
        )
        for vals in vals_list:
            if (not vals.get("name") or vals.get("name") == _("新清算单")) and sequence:
                vals["name"] = sequence.next_by_id()
        records = super().create(vals_list)
        records._ensure_default_channel()
        return records

    def write(self, vals):
        res = super().write(vals)
        if {"channel_id"} & set(vals.keys()):
            self._ensure_default_channel()
        return res

    def _ensure_default_channel(self):
        for record in self:
            if record.channel_id:
                continue
            record.channel_id = record._find_channel_for_company(record.source_company_id)

    @api.constrains("source_company_id", "target_company_id", "group_id")
    def _check_group_membership(self):
        for record in self:
            if record.source_company_id == record.target_company_id:
                raise ValidationError(_("付款门店与收款门店不可相同。"))
            members = record.group_id.member_company_ids
            if record.source_company_id and record.source_company_id not in members:
                raise ValidationError(_("付款门店不属于所选互通组。"))
            if record.target_company_id and record.target_company_id not in members:
                raise ValidationError(_("收款门店不属于所选互通组。"))

    @api.constrains("amount")
    def _check_amount_positive(self):
        for record in self:
            if record.amount <= 0:
                raise ValidationError(_("清算金额必须大于 0。"))

    def action_confirm(self):
        for record in self:
            if record.state != "draft":
                continue
            source_channel = record.channel_id or record._find_channel_for_company(record.source_company_id)
            target_channel = record._find_channel_for_company(
                record.target_company_id,
                allow_create=True,
            )

            source_vals = record._prepare_transaction_vals(
                company=record.source_company_id,
                channel=source_channel,
                amount=-abs(record.amount),
                description=record.memo,
            )
            target_vals = record._prepare_transaction_vals(
                company=record.target_company_id,
                channel=target_channel,
                amount=abs(record.amount),
                description=record.memo,
            )
            source_tx = self.env["store.account.transaction"].create(source_vals)
            target_tx = self.env["store.account.transaction"].create(target_vals)
            (source_tx + target_tx).action_confirm()
            record.write(
                {
                    "state": "confirmed",
                    "source_transaction_id": source_tx.id,
                    "target_transaction_id": target_tx.id,
                }
            )
            record.message_post(
                body=_(
                    "清算已确认，生成付款流水 %(pay)s 与收款流水 %(recv)s。",
                    pay=source_tx.display_name,
                    recv=target_tx.display_name,
                )
            )
        return True

    def action_cancel(self):
        for record in self:
            if record.state != "confirmed":
                record.state = "cancelled"
                continue
            (record.source_transaction_id | record.target_transaction_id).action_cancel()
            record.write({"state": "cancelled"})
            record.message_post(body=_("清算已取消，对应流水已标记为取消。"))
        return True

    def _prepare_transaction_vals(self, company, channel, amount, description=""):
        self.ensure_one()
        currency = self.currency_id
        if company and company.currency_id:
            currency = company.currency_id
        return {
            "company_id": company.id if company else self.env.company.id,
            "currency_id": currency.id,
            "transaction_type": "transfer",
            "channel_id": channel.id if channel else False,
            "amount": amount,
            "reference": "%s,%s" % (self._name, self.id),
            "description": description or self.name,
            "clearing_id": self.id,
            "link_group_id": self.group_id.id,
        }

    def _find_channel_for_company(self, company, allow_create=False):
        self.ensure_one()
        if not company:
            return False
        channel = (
            self.env["store.finance.channel"]
            .with_context(active_test=False)
            .search(
                [
                    ("company_id", "=", company.id),
                    ("channel_type", "=", "internal"),
                ],
                limit=1,
                order="sequence asc",
            )
        )
        if channel or not allow_create:
            return channel
        channel = self.env["store.finance.channel"].create(
            {
                "name": _("内部结算"),
                "code": "INTERNAL",
                "channel_type": "internal",
                "company_id": company.id,
                "auto_reconcile": False,
                "active": True,
            }
        )
        return channel
