from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class StoreCrowdfundingDividend(models.Model):
    _name = "store.crowdfunding.dividend"
    _description = "众筹分红计划"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "plan_date asc, id desc"
    _check_company_auto = True

    STATE_SELECTION = [
        ("draft", "草稿"),
        ("scheduled", "待执行"),
        ("done", "已执行"),
        ("cancelled", "已取消"),
    ]

    name = fields.Char(
        string="分红计划编号",
        readonly=True,
        copy=False,
        default="新分红",
        tracking=True,
    )
    project_id = fields.Many2one(
        "store.crowdfunding.project",
        string="关联项目",
        required=True,
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
    state = fields.Selection(
        selection=STATE_SELECTION,
        string="状态",
        default="draft",
        tracking=True,
    )
    plan_date = fields.Date(
        string="计划执行日期",
        required=True,
        tracking=True,
    )
    amount_total = fields.Monetary(
        string="计划分红金额",
        compute="_compute_amounts",
        store=True,
        currency_field="currency_id",
    )
    amount_paid = fields.Monetary(
        string="已支付金额",
        compute="_compute_amounts",
        store=True,
        currency_field="currency_id",
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="币种",
        related="project_id.currency_id",
        store=True,
    )
    line_ids = fields.One2many(
        "store.crowdfunding.dividend.line",
        "dividend_id",
        string="分红明细",
    )
    description = fields.Text(string="分红说明")
    execution_note = fields.Text(string="执行备注")

    _sql_constraints = [
        (
            "plan_date_future",
            "CHECK(plan_date IS NOT NULL)",
            "计划执行日期不能为空。",
        ),
    ]

    @api.model
    def create(self, vals):
        if not vals.get("name") or vals.get("name") == "新分红":
            vals["name"] = self.env["ir.sequence"].next_by_code("store.crowdfunding.dividend") or "新分红"
        record = super().create(vals)
        record.project_id.message_post(
            body=_("创建新的分红计划，执行日期：%s") % fields.Date.to_string(record.plan_date),
            message_type="comment",
        )
        return record

    @api.depends("line_ids.amount", "line_ids.amount_paid")
    def _compute_amounts(self):
        for record in self:
            total = sum(line.amount for line in record.line_ids)
            paid = sum(line.amount_paid for line in record.line_ids)
            record.amount_total = total
            record.amount_paid = paid

    def action_confirm(self):
        self._ensure_brand_operator()
        for record in self:
            if record.state != "draft":
                raise UserError(_("只有草稿状态可以提交执行。"))
            if not record.line_ids:
                raise ValidationError(_("请先添加分红明细。"))
            record.state = "scheduled"
            record.project_id.message_post(
                body=_("分红计划已提交待执行，执行日期：%s") % fields.Date.to_string(record.plan_date),
                message_type="comment",
            )

    def action_execute(self):
        self._ensure_brand_operator()
        for record in self:
            if record.state != "scheduled":
                raise UserError(_("只有待执行的计划可以执行。"))
            pending_lines = record.line_ids.filtered(lambda line: not line.is_paid)
            if not pending_lines:
                raise ValidationError(_("所有分红明细均已执行。"))
            for line in pending_lines:
                line._execute_payout()
            record.write(
                {
                    "state": "done",
                    "execution_note": _("共计执行 %s 条分红。") % len(pending_lines),
                }
            )
            record.project_id.message_post(
                body=_("分红计划已执行，共支付 %s 元。") % record.amount_paid,
                message_type="comment",
            )

    def action_cancel(self, reason=None):
        self._ensure_brand_operator()
        for record in self:
            if record.state == "done":
                raise UserError(_("已执行完毕的计划不可取消。"))
            record.state = "cancelled"
            record.project_id.message_post(
                body=_("分红计划已取消：%s") % (reason or _("品牌方操作")),
                message_type="comment",
            )

    def _ensure_brand_operator(self):
        if not (
            self.env.user.has_group("brand_core.group_brand_admin")
            or self.env.user.has_group("brand_core.group_brand_operator")
        ):
            raise UserError(_("只有品牌方可执行该操作。"))


class StoreCrowdfundingDividendLine(models.Model):
    _name = "store.crowdfunding.dividend.line"
    _description = "众筹分红明细"
    _order = "investment_id, id"
    _check_company_auto = True

    dividend_id = fields.Many2one(
        "store.crowdfunding.dividend",
        string="分红计划",
        required=True,
        ondelete="cascade",
    )
    project_id = fields.Many2one(
        "store.crowdfunding.project",
        string="项目",
        related="dividend_id.project_id",
        store=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="门店",
        related="dividend_id.project_company_id",
        store=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="投资人",
        related="investment_id.partner_id",
        store=True,
    )
    investment_id = fields.Many2one(
        "store.crowdfunding.investment",
        string="投资记录",
        required=True,
        domain="[('project_id', '=', project_id)]",
    )
    amount = fields.Monetary(
        string="计划金额",
        required=True,
        currency_field="currency_id",
    )
    amount_paid = fields.Monetary(
        string="已支付金额",
        default=0.0,
        currency_field="currency_id",
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="币种",
        related="dividend_id.currency_id",
        store=True,
    )
    payout_transaction_id = fields.Many2one(
        "store.account.transaction",
        string="支付流水",
        readonly=True,
    )
    is_paid = fields.Boolean(
        string="是否完成",
        compute="_compute_is_paid",
        store=True,
    )

    _sql_constraints = [
        ("amount_positive", "CHECK(amount >= 0)", "金额必须大于等于 0。"),
    ]

    @api.depends("amount", "amount_paid")
    def _compute_is_paid(self):
        for record in self:
            record.is_paid = record.amount_paid >= record.amount

    def _execute_payout(self):
        self.ensure_one()
        if self.is_paid:
            return
        if self.amount <= 0:
            raise ValidationError(_("分红金额需大于 0。"))
        transaction_vals = {
            "company_id": self.company_id.id,
            "transaction_type": "crowdfunding_dividend",
            "amount": -self.amount,
            "currency_id": self.currency_id.id,
            "member_id": self.partner_id.id,
            "reference": f"store.crowdfunding.dividend.line,{self.id}",
            "description": _("众筹分红：%s") % self.project_id.display_name,
            "state": "confirmed",
            "date": fields.Datetime.now(),
        }
        transaction = self.env["store.account.transaction"].create(transaction_vals)
        self.write(
            {
                "payout_transaction_id": transaction.id,
                "amount_paid": self.amount,
            }
        )

    @api.constrains("investment_id")
    def _check_investment_state(self):
        for record in self:
            if record.investment_id.state != "confirmed":
                raise ValidationError(_("仅允许对已确认的投资创建分红明细。"))
