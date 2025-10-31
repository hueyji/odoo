from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class StoreCrowdfundingProject(models.Model):
    _name = "store.crowdfunding.project"
    _description = "众筹项目"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc, id desc"
    _check_company_auto = True

    STATE_SELECTION = [
        ("draft", "草稿"),
        ("review", "待品牌审核"),
        ("funding", "募集中"),
        ("executing", "执行中"),
        ("closed", "已结项"),
        ("cancelled", "已取消"),
    ]

    name = fields.Char(
        string="项目名称",
        required=True,
        tracking=True,
    )
    code = fields.Char(
        string="项目编号",
        readonly=True,
        copy=False,
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="发起门店",
        required=True,
        default=lambda self: self.env.company.id,
        tracking=True,
    )
    brand_company_id = fields.Many2one(
        "res.company",
        string="品牌总部",
        tracking=True,
        help="关联的品牌总部，用于跨公司审批及门户展示。",
    )
    link_group_id = fields.Many2one(
        "store.link.group",
        string="互通组",
        tracking=True,
        help="若项目涉及多个门店联合众筹，可关联互通组用于权限管理。",
    )
    state = fields.Selection(
        selection=STATE_SELECTION,
        string="状态",
        default="draft",
        tracking=True,
    )
    target_amount = fields.Monetary(
        string="目标募集金额",
        required=True,
        tracking=True,
        currency_field="currency_id",
    )
    min_invest_amount = fields.Monetary(
        string="单笔最低认购额",
        default=1000.0,
        tracking=True,
        currency_field="currency_id",
    )
    max_invest_amount = fields.Monetary(
        string="单笔最高认购额",
        help="防止单一投资人占比过高，品牌方可按项目调整。",
        currency_field="currency_id",
    )
    min_success_ratio = fields.Float(
        string="成功阈值",
        default=0.7,
        help="达到该比例视为众筹成功，可进入执行阶段。",
        tracking=True,
    )
    amount_pledged = fields.Monetary(
        string="认购总额",
        compute="_compute_funding_stats",
        store=True,
        currency_field="currency_id",
    )
    amount_confirmed = fields.Monetary(
        string="已到账金额",
        compute="_compute_funding_stats",
        store=True,
        currency_field="currency_id",
    )
    funding_progress = fields.Float(
        string="募集进度",
        compute="_compute_funding_progress",
        store=True,
        help="按照已确认金额 / 目标金额计算的百分比。",
    )
    investment_count = fields.Integer(
        string="投资笔数",
        compute="_compute_funding_stats",
        store=True,
    )
    funding_start_date = fields.Date(
        string="募集开始日期",
        tracking=True,
    )
    funding_end_date = fields.Date(
        string="募集截止日期",
        tracking=True,
    )
    execution_start_date = fields.Date(
        string="执行开始日期",
        tracking=True,
    )
    execution_end_date = fields.Date(
        string="执行截止日期",
        tracking=True,
    )
    description = fields.Html(
        string="项目说明",
        sanitize=True,
        default="",
    )
    risk_note = fields.Html(
        string="风险提示",
        sanitize=True,
        default="",
    )
    contract_attachment_ids = fields.Many2many(
        "ir.attachment",
        "store_crowdfunding_project_attachment_rel",
        "project_id",
        "attachment_id",
        string="合同附件",
        help="上传加水印后的合同或审批文件，供品牌审核与投资人确认。",
    )
    contract_watermark = fields.Char(
        string="附件水印说明",
        help="记录生成水印时使用的标识内容，便于追踪。",
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="币种",
        required=True,
        default=lambda self: self.env.company.currency_id.id,
    )
    investment_ids = fields.One2many(
        "store.crowdfunding.investment",
        "project_id",
        string="投资记录",
    )
    dividend_plan_ids = fields.One2many(
        "store.crowdfunding.dividend",
        "project_id",
        string="分红计划",
    )
    dividend_count = fields.Integer(
        string="分红计划数量",
        compute="_compute_dividend_count",
        store=True,
    )
    company_contact_id = fields.Many2one(
        "res.partner",
        string="门店负责人",
        tracking=True,
        help="用于品牌沟通、门户展示的负责人信息。",
    )
    portal_visible = fields.Boolean(
        string="门户可见",
        default=True,
        tracking=True,
        help="关闭后仅内部员工可见，常用于审查或整改期间。",
    )
    color = fields.Integer(string="标记颜色")

    _sql_constraints = [
        (
            "code_company_unique",
            "unique(code, company_id)",
            "同一门店下的众筹项目编号必须唯一。",
        ),
        (
            "min_success_ratio_range",
            "CHECK(min_success_ratio >= 0 AND min_success_ratio <= 1)",
            "成功阈值需处于 0 到 1 之间。",
        ),
    ]

    @api.model
    def create(self, vals):
        if not vals.get("code"):
            vals["code"] = self.env["ir.sequence"].next_by_code("store.crowdfunding.project")
        if not vals.get("brand_company_id"):
            company = self.env["res.company"].browse(vals.get("company_id")) if vals.get("company_id") else self.env.company
            vals["brand_company_id"] = company.parent_id.id if company.parent_id else company.id
        return super().create(vals)

    def write(self, vals):
        if vals.get("company_id") and not vals.get("brand_company_id"):
            company = self.env["res.company"].browse(vals["company_id"])
            vals["brand_company_id"] = company.parent_id.id if company.parent_id else company.id
        res = super().write(vals)
        if {"target_amount"} & set(vals.keys()):
            for record in self:
                record._check_target_amount()
        return res

    @api.depends("investment_ids.state", "investment_ids.amount", "investment_ids.amount_confirmed")
    def _compute_funding_stats(self):
        for record in self:
            confirmed = sum(
                inv.amount_confirmed for inv in record.investment_ids if inv.state == "confirmed"
            )
            pledged = sum(inv.amount for inv in record.investment_ids if inv.state != "cancelled")
            record.amount_confirmed = confirmed
            record.amount_pledged = pledged
            record.investment_count = len(record.investment_ids.filtered(lambda inv: inv.state != "cancelled"))

    @api.depends("amount_confirmed", "target_amount")
    def _compute_funding_progress(self):
        for record in self:
            if not record.target_amount:
                record.funding_progress = 0.0
            else:
                record.funding_progress = min(
                    100.0,
                    (record.amount_confirmed / record.target_amount) * 100.0,
                )

    @api.depends("dividend_plan_ids")
    def _compute_dividend_count(self):
        for record in self:
            record.dividend_count = len(record.dividend_plan_ids)

    @api.constrains("target_amount", "min_invest_amount", "max_invest_amount")
    def _check_amount_constraints(self):
        for record in self:
            if record.target_amount <= 0:
                raise ValidationError(_("目标募集金额必须大于 0。"))
            if record.min_invest_amount and record.min_invest_amount <= 0:
                raise ValidationError(_("单笔最低认购额必须大于 0。"))
            if (
                record.max_invest_amount
                and record.min_invest_amount
                and record.max_invest_amount < record.min_invest_amount
            ):
                raise ValidationError(_("单笔最高认购额不得小于最低认购额。"))

    def _check_target_amount(self):
        if self.target_amount <= 0:
            raise ValidationError(_("目标募集金额必须大于 0。"))

    def action_submit_review(self):
        self._ensure_store_manager()
        for record in self:
            if record.state != "draft":
                raise UserError(_("只有草稿状态的项目才能提交审核。"))
            if record.funding_start_date and record.funding_end_date:
                if record.funding_end_date < record.funding_start_date:
                    raise ValidationError(_("募集结束日期不能早于开始日期。"))
            record.state = "review"
            record.message_post(
                body=_("门店已提交众筹项目至品牌审核。"),
                message_type="comment",
            )
        self._schedule_brand_review_activity()

    def _schedule_brand_review_activity(self):
        activity_type = self.env.ref("mail.mail_activity_data_todo")
        brand_group = self.env.ref("brand_core.group_brand_admin")
        for record in self:
            if not activity_type:
                continue
            brand_users = brand_group.users.filtered(
                lambda user: record.brand_company_id in user.company_ids or not user.company_ids
            )
            if not brand_users:
                brand_users = brand_group.users
            if not brand_users:
                continue
            for user in brand_users:
                record.activity_schedule(
                    activity_type.id,
                    user_id=user.id,
                    summary=_("众筹项目待审核"),
                    note=_("请审核众筹项目：%s") % record.display_name,
                )

    def action_approve(self):
        self._ensure_brand_operator()
        for record in self:
            if record.state != "review":
                raise UserError(_("只有待品牌审核状态可以执行此操作。"))
            if not record.funding_start_date:
                record.funding_start_date = date.today()
            if record.funding_end_date and record.funding_end_date < record.funding_start_date:
                raise ValidationError(_("募集截止日期需晚于开始日期。"))
            record.state = "funding"
            record.message_post(body=_("品牌方已通过审核，项目进入募集中阶段。"))
            todo_type = self.env.ref("mail.mail_activity_data_todo")
            brand_users = self.env.ref("brand_core.group_brand_admin").users
            activities = record.activity_ids.filtered(
                lambda act: act.activity_type_id == todo_type and act.user_id in brand_users
            )
            if activities:
                activities.sudo().unlink()

    def action_reject(self, reason=None):
        self._ensure_brand_operator()
        for record in self:
            if record.state != "review":
                raise UserError(_("只有待品牌审核状态可以驳回。"))
            record.state = "draft"
            record.message_post(
                body=_("品牌方驳回项目：%s") % (reason or _("请补充资料后重新提交。")),
                message_type="comment",
            )

    def action_start_execution(self):
        self._ensure_brand_operator()
        for record in self:
            if record.state != "funding":
                raise UserError(_("仅募集中项目可以转入执行阶段。"))
            if record.funding_end_date and record.funding_end_date > date.today():
                raise ValidationError(_("募集尚未截止，暂无法进入执行阶段。"))
            if record.target_amount and record.amount_confirmed < record.target_amount * record.min_success_ratio:
                raise ValidationError(_("当前到账金额未达到成功阈值，无法开启执行。"))
            if not record.execution_start_date:
                record.execution_start_date = date.today()
            record.state = "executing"
            record.message_post(body=_("项目已进入执行阶段，等待分红计划安排。"))

    def action_mark_closed(self):
        self._ensure_brand_operator()
        for record in self:
            if record.state not in ("executing", "funding"):
                raise UserError(_("只有执行中或募集中项目可以结项。"))
            record.state = "closed"
            record.execution_end_date = record.execution_end_date or date.today()
            record.message_post(body=_("项目已结项，所有流程全部完成。"))

    def action_cancel(self, reason=None):
        self._ensure_brand_operator()
        for record in self:
            if record.state == "closed":
                raise UserError(_("已结项的项目不可取消。"))
            record.state = "cancelled"
            record.message_post(
                body=_("项目被取消：%s") % (reason or _("品牌方手动执行。")),
                message_type="comment",
            )

    def _ensure_store_manager(self):
        if not self.env.user.has_group("brand_core.group_store_manager"):
            raise UserError(_("只有门店负责人可以执行该操作。"))

    def _ensure_brand_operator(self):
        if not (
            self.env.user.has_group("brand_core.group_brand_admin")
            or self.env.user.has_group("brand_core.group_brand_operator")
        ):
            raise UserError(_("只有品牌方用户可执行该操作。"))
