from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class StoreCrowdfundingInvestment(models.Model):
    _name = "store.crowdfunding.investment"
    _description = "众筹投资记录"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc, id desc"
    _check_company_auto = True

    STATE_SELECTION = [
        ("draft", "草稿"),
        ("confirmed", "已确认"),
        ("refunded", "已退款"),
        ("cancelled", "已取消"),
    ]

    name = fields.Char(
        string="投资编号",
        readonly=True,
        copy=False,
        default="新投资",
        tracking=True,
    )
    project_id = fields.Many2one(
        "store.crowdfunding.project",
        string="项目",
        required=True,
        ondelete="cascade",
        tracking=True,
    )
    project_company_id = fields.Many2one(
        "res.company",
        string="门店",
        related="project_id.company_id",
        store=True,
    )
    brand_company_id = fields.Many2one(
        "res.company",
        string="品牌总部",
        related="project_id.brand_company_id",
        store=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="投资人",
        required=True,
        tracking=True,
        domain="[('company_id', 'in', [project_company_id, False])]",
    )
    contact_phone = fields.Char(
        string="联系方式",
        related="partner_id.mobile",
        readonly=True,
    )
    state = fields.Selection(
        selection=STATE_SELECTION,
        string="状态",
        default="draft",
        tracking=True,
    )
    amount = fields.Monetary(
        string="认购金额",
        required=True,
        tracking=True,
        currency_field="currency_id",
    )
    amount_confirmed = fields.Monetary(
        string="已确认金额",
        currency_field="currency_id",
        default=0.0,
    )
    amount_refunded = fields.Monetary(
        string="已退款金额",
        currency_field="currency_id",
        default=0.0,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="币种",
        related="project_id.currency_id",
        store=True,
    )
    investment_date = fields.Date(
        string="投资日期",
        default=fields.Date.context_today,
        tracking=True,
    )
    transaction_id = fields.Many2one(
        "store.account.transaction",
        string="到账流水",
        readonly=True,
        copy=False,
    )
    refund_transaction_id = fields.Many2one(
        "store.account.transaction",
        string="退款流水",
        readonly=True,
        copy=False,
    )
    note = fields.Text(string="备注")
    dividend_line_ids = fields.One2many(
        "store.crowdfunding.dividend.line",
        "investment_id",
        string="分红明细",
    )

    _sql_constraints = [
        ("amount_positive", "CHECK(amount > 0)", "投资金额必须大于 0。"),
    ]

    @api.model
    def create(self, vals):
        if not vals.get("name") or vals.get("name") == "新投资":
            vals["name"] = self.env["ir.sequence"].next_by_code("store.crowdfunding.investment") or "新投资"
        record = super().create(vals)
        record.project_id.message_subscribe(partner_ids=[record.partner_id.id])
        return record

    def action_confirm(self):
        self._ensure_can_operate()
        for record in self:
            if record.state != "draft":
                raise UserError(_("仅草稿状态可以确认投资。"))
            record._validate_investment_constraints()
            transaction = record._create_finance_transaction()
            record.write(
                {
                    "state": "confirmed",
                    "amount_confirmed": record.amount,
                    "transaction_id": transaction.id,
                    "investment_date": fields.Date.today(),
                }
            )
            record.project_id.message_post(
                body=_("投资 %s 元已确认，投资人：%s") % (record.amount, record.partner_id.display_name),
                message_type="comment",
            )

    def action_refund(self, amount=None, reason=None):
        self._ensure_brand_operator()
        for record in self:
            if record.state != "confirmed":
                raise UserError(_("只有已确认的投资可以退款。"))
            refund_amount = amount or record.amount_confirmed
            if refund_amount <= 0:
                raise ValidationError(_("退款金额必须大于 0。"))
            if refund_amount > record.amount_confirmed - record.amount_refunded:
                raise ValidationError(_("退款金额不可超过已确认金额减去已退款金额。"))
            refund_tx = record._create_refund_transaction(refund_amount, reason)
            new_refunded = record.amount_refunded + refund_amount
            vals = {
                "amount_refunded": new_refunded,
                "refund_transaction_id": refund_tx.id,
            }
            if new_refunded >= record.amount_confirmed:
                vals["state"] = "refunded"
            record.write(vals)
            record.project_id.message_post(
                body=_("已为投资人 %s 处理退款 %s 元。") % (record.partner_id.display_name, refund_amount),
                message_type="comment",
            )

    def action_cancel(self, reason=None):
        self._ensure_brand_operator()
        for record in self:
            if record.state not in ("draft", "confirmed"):
                raise UserError(_("只有草稿或已确认投资可以取消。"))
            if record.amount_confirmed and record.amount_refunded < record.amount_confirmed:
                raise ValidationError(_("请先完成退款再取消投资。"))
            record.state = "cancelled"
            record.project_id.message_post(
                body=_("投资记录被取消：%s") % (reason or _("品牌方操作")),
                message_type="comment",
            )

    def _validate_investment_constraints(self):
        for record in self:
            project = record.project_id
            today = fields.Date.today()
            if project.state not in ("funding", "executing"):
                raise ValidationError(_("项目不在募集或执行阶段，不能确认投资。"))
            if project.funding_start_date and today < project.funding_start_date:
                raise ValidationError(_("募集尚未开始，无法确认投资。"))
            if project.funding_end_date and today > project.funding_end_date:
                raise ValidationError(_("募集已结束，请联系品牌方处理。"))
            if project.min_invest_amount and record.amount < project.min_invest_amount:
                raise ValidationError(_("投资金额不能低于项目设定的最低认购额。"))
            if project.max_invest_amount and record.amount > project.max_invest_amount:
                raise ValidationError(_("投资金额不能超过项目设定的最高认购额。"))

    def _create_finance_transaction(self):
        self.ensure_one()
        transaction_vals = {
            "company_id": self.project_company_id.id,
            "transaction_type": "crowdfunding",
            "amount": self.amount,
            "currency_id": self.currency_id.id,
            "member_id": self.partner_id.id,
            "link_group_id": self.project_id.link_group_id.id,
            "reference": f"store.crowdfunding.investment,{self.id}",
            "description": _("众筹投资：%s") % self.project_id.display_name,
            "state": "confirmed",
            "date": fields.Datetime.now(),
        }
        transaction = self.env["store.account.transaction"].create(transaction_vals)
        return transaction

    def _create_refund_transaction(self, amount, reason=None):
        self.ensure_one()
        transaction_vals = {
            "company_id": self.project_company_id.id,
            "transaction_type": "refund",
            "amount": -amount,
            "currency_id": self.currency_id.id,
            "member_id": self.partner_id.id,
            "link_group_id": self.project_id.link_group_id.id,
            "reference": f"store.crowdfunding.investment,{self.id}",
            "description": _("众筹退款：%s") % (reason or self.project_id.display_name),
            "state": "confirmed",
            "date": fields.Datetime.now(),
        }
        return self.env["store.account.transaction"].create(transaction_vals)

    def _ensure_can_operate(self):
        if self.env.user.has_group("brand_core.group_brand_admin") or self.env.user.has_group("brand_core.group_brand_operator"):
            return
        if self.env.user.has_group("brand_core.group_store_manager"):
            return
        raise UserError(_("只有品牌方或门店负责人可以确认投资。"))

    def _ensure_brand_operator(self):
        if not (
            self.env.user.has_group("brand_core.group_brand_admin")
            or self.env.user.has_group("brand_core.group_brand_operator")
        ):
            raise UserError(_("只有品牌方可以执行该操作。"))
