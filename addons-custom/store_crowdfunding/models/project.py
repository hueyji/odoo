# -*- coding: utf-8 -*-
import base64
from datetime import timedelta

from odoo.tools import pdf as pdf_utils
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class StoreCrowdfundingProject(models.Model):
    _name = "store.crowdfunding.project"
    _description = "众筹项目"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"

    def _default_currency_id(self):
        return self.env.company.currency_id

    name = fields.Char(string="项目名称", required=True, tracking=True)
    code = fields.Char(string="项目编号", default="新项目", copy=False, tracking=True)
    company_id = fields.Many2one(
        "res.company",
        string="所属公司",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="币种",
        required=True,
        default=_default_currency_id,
    )
    applicant_id = fields.Many2one(
        "res.users",
        string="发起人",
        required=True,
        default=lambda self: self.env.user,
        tracking=True,
    )
    approval_user_id = fields.Many2one(
        "res.users",
        string="品牌审核人",
        tracking=True,
        readonly=True,
    )
    submit_date = fields.Datetime(string="提交时间", readonly=True, tracking=True)
    approval_date = fields.Datetime(string="审核时间", readonly=True, tracking=True)
    goal_amount = fields.Monetary(
        string="目标金额",
        required=True,
        currency_field="currency_id",
        tracking=True,
    )
    minimum_amount = fields.Monetary(
        string="最低可执行金额",
        currency_field="currency_id",
        help="品牌可在审核时确认是否允许未达标但超过最低金额情况下执行。",
    )
    dividend_rule = fields.Html(string="分红规则", sanitize=True)
    summary = fields.Text(string="项目概述")
    investor_highlight = fields.Text(string="投资亮点")
    location = fields.Char(string="项目地址")
    fundraising_start_date = fields.Date(string="募集开始日期", tracking=True)
    fundraising_deadline = fields.Date(string="募集截止日期", tracking=True)
    execution_start_date = fields.Date(string="执行开始日期", tracking=True)
    closed_date = fields.Date(string="结项日期", tracking=True)
    portal_published = fields.Boolean(
        string="门户展示",
        default=True,
        help="勾选后，满足状态要求的项目会展示在投资人门户。",
        tracking=True,
    )
    contract_attachment_ids = fields.Many2many(
        "ir.attachment",
        "store_crowdfunding_contract_rel",
        "project_id",
        "attachment_id",
        string="合同附件",
        help="上传带水印的合同、批复材料，供品牌方审核。",
    )
    contract_watermark_status = fields.Selection(
        [
            ("pending", "待验证"),
            ("ready", "水印已确认"),
            ("rejected", "水印不合规"),
        ],
        string="水印校验状态",
        default="pending",
        tracking=True,
    )
    watermark_method = fields.Selection(
        [
            ("manual", "人工确认"),
            ("auto", "系统水印"),
        ],
        string="水印方案",
        default="manual",
        tracking=True,
    )
    watermark_generated_at = fields.Datetime(string="水印生成时间", readonly=True, tracking=True)
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
    total_invest_amount = fields.Monetary(
        string="已募集金额",
        currency_field="currency_id",
        compute="_compute_statistics",
        store=True,
    )
    investor_count = fields.Integer(
        string="投资人数",
        compute="_compute_statistics",
        store=True,
    )
    total_dividend_amount = fields.Monetary(
        string="累计分红金额",
        currency_field="currency_id",
        compute="_compute_statistics",
        store=True,
    )
    dividend_paid_count = fields.Integer(
        string="已执行分红次数",
        compute="_compute_statistics",
        store=True,
    )
    last_dividend_date = fields.Date(
        string="最近分红日期",
        compute="_compute_statistics",
        store=True,
    )
    progress_rate = fields.Float(
        string="完成率",
        compute="_compute_statistics",
        store=True,
        help="以目标金额为基准的募集进度（0-100%）。",
    )
    state = fields.Selection(
        [
            ("draft", "草稿"),
            ("to_approve", "审核中"),
            ("fundraising", "募集中"),
            ("in_progress", "执行中"),
            ("closed", "已结项"),
            ("rejected", "已驳回"),
        ],
        string="状态",
        default="draft",
        required=True,
        tracking=True,
    )
    color = fields.Integer("颜色", default=2)

    _sql_constraints = [
        ("code_company_unique", "unique(code, company_id)", "项目编号在同一公司内必须唯一。"),
    ]

    def name_get(self):
        result = []
        for record in self:
            display = record.name
            if record.code and record.code != _("新项目"):
                display = "%s - %s" % (record.code, display)
            result.append((record.id, display))
        return result

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env.ref(
            "store_crowdfunding.sequence_store_crowdfunding_project", raise_if_not_found=False
        )
        for vals in vals_list:
            if vals.get("code") in (None, "/", _("新项目")) and sequence:
                vals["code"] = sequence.next_by_id()
            if not vals.get("company_id"):
                vals["company_id"] = self.env.company.id
        return super().create(vals_list)

    @api.depends(
        "investment_ids.state",
        "investment_ids.amount",
        "dividend_plan_ids.state",
        "dividend_plan_ids.amount",
        "dividend_plan_ids.payout_ids.amount",
        "dividend_plan_ids.paid_date",
    )
    def _compute_statistics(self):
        for project in self:
            confirmed = project.investment_ids.filtered(lambda rec: rec.state == "confirmed")
            total = sum(confirmed.mapped("amount"))
            investors = len(confirmed.mapped("partner_id"))
            project.total_invest_amount = total
            project.investor_count = investors
            rate = (100.0 * total / project.goal_amount) if project.goal_amount else 0.0
            project.progress_rate = min(rate, 100.0)

            paid_dividends = project.dividend_plan_ids.filtered(lambda rec: rec.state == "paid")
            project.dividend_paid_count = len(paid_dividends)
            project.last_dividend_date = max(paid_dividends.mapped("paid_date")) if paid_dividends else False
            payout_amount = sum(paid_dividends.mapped("amount"))
            project.total_dividend_amount = payout_amount

    @api.constrains("goal_amount", "minimum_amount")
    def _check_amounts(self):
        for record in self:
            if record.goal_amount <= 0:
                raise ValidationError(_("目标金额必须大于 0。"))
            if record.minimum_amount and record.minimum_amount > record.goal_amount:
                raise ValidationError(_("最低可执行金额不可超过目标金额。"))

    @api.constrains("fundraising_start_date", "fundraising_deadline")
    def _check_fundraising_range(self):
        for record in self:
            if record.fundraising_start_date and record.fundraising_deadline:
                delta = record.fundraising_deadline - record.fundraising_start_date
                if delta.days > 60:
                    raise ValidationError(_("募集期最长为 60 天，请调整截止日期。"))
                if delta.days < 0:
                    raise ValidationError(_("募集截止日期不得早于开始日期。"))

    def action_submit_for_approval(self):
        for project in self:
            if project.state not in ("draft", "rejected"):
                raise ValidationError(_("仅草稿或驳回的项目可重新提交审核。"))
            if project.watermark_method in ("auto", "sign") and project.contract_watermark_status != "ready":
                project._auto_generate_watermark()
            project._ensure_contract_ready()
            approver_users = project._get_brand_approvers()
            project.write(
                {
                    "state": "to_approve",
                    "submit_date": fields.Datetime.now(),
                }
            )
            for user in approver_users:
                project.activity_schedule(
                    "mail.mail_activity_data_todo",
                    user_id=user.id,
                    summary=_("众筹项目审核"),
                    note=_("请审核众筹项目：%s") % project.display_name,
                )
        return True

    def action_mark_watermark_ready(self):
        for project in self:
            if not project.contract_attachment_ids:
                raise ValidationError(_("请先上传合同附件后再设置水印状态。"))
            now = fields.Datetime.now()
            project.contract_attachment_ids.write(
                {
                    "crowdfunding_watermarked": True,
                    "crowdfunding_watermark_method": project.watermark_method,
                    "crowdfunding_watermark_date": now,
                }
            )
            project.write(
                {
                    "contract_watermark_status": "ready",
                    "watermark_generated_at": now,
                }
            )
        return True

    def action_approve(self):
        for project in self:
            if project.state != "to_approve":
                raise ValidationError(_("仅审核中的项目可以通过审核。"))
            if project.watermark_method in ("auto", "sign") and project.contract_watermark_status != "ready":
                project._auto_generate_watermark()
            project._ensure_contract_ready()
            vals = {
                "state": "fundraising",
                "approval_user_id": self.env.user.id,
                "approval_date": fields.Datetime.now(),
            }
            if not project.fundraising_start_date:
                vals["fundraising_start_date"] = fields.Date.today()
            start_date = (
                vals.get("fundraising_start_date") or project.fundraising_start_date
            )
            if not project.fundraising_deadline and start_date:
                vals["fundraising_deadline"] = start_date + timedelta(days=30)
            project.write(vals)
            project.activity_feedback("mail.mail_activity_data_todo")
        return True

    def action_reject(self, reason=None):
        for project in self:
            if project.state not in ("to_approve", "fundraising", "in_progress"):
                raise ValidationError(_("仅在审核或执行阶段的项目可以驳回。"))
            reject_reason = reason or self.env.context.get("reason")
            message = _("项目被驳回。")
            if reject_reason:
                message = "%s\n%s" % (message, reject_reason)
            project.message_post(body=message)
            project.write(
                {
                    "state": "rejected",
                    "approval_user_id": False,
                    "approval_date": False,
                }
            )
        return True

    def action_start_execution(self):
        for project in self:
            if project.state != "fundraising":
                raise ValidationError(_("仅已完成审核并处于募集中状态的项目可进入执行阶段。"))
            if (
                project.total_invest_amount < project.goal_amount
                and (not project.minimum_amount or project.total_invest_amount < project.minimum_amount)
            ):
                raise ValidationError(_("募集金额未达到执行阈值，无法进入执行阶段。"))
            project.write(
                {
                    "state": "in_progress",
                    "execution_start_date": fields.Date.today(),
                }
            )
        return True

    def action_close(self):
        for project in self:
            if project.state != "in_progress":
                raise ValidationError(_("仅执行中的项目可结项。"))
            pending_dividend = project.dividend_plan_ids.filtered(
                lambda d: d.state not in ("paid", "cancelled")
            )
            if pending_dividend:
                raise ValidationError(_("仍有未执行的分红计划，无法结项。"))
            project.write(
                {
                    "state": "closed",
                    "closed_date": fields.Date.today(),
                }
            )
        return True

    def _ensure_contract_ready(self):
        for project in self:
            if not project.contract_attachment_ids:
                raise ValidationError(_("请至少上传一份合同附件。"))
            if project.contract_watermark_status != "ready":
                raise ValidationError(_("合同水印状态需为“水印已确认”才能继续流程。"))
            if project.watermark_method == "manual":
                missing = project.contract_attachment_ids.filtered(lambda att: not att.crowdfunding_watermarked)
                if missing:
                    raise ValidationError(_("存在未标记水印的附件，请确认后再提交。"))

    def _get_brand_approvers(self):
        self.ensure_one()
        group = self.env.ref("brand_core.group_brand_platform_admin", raise_if_not_found=False)
        if not group:
            return self.env.user
        approvers = group.users.filtered(
            lambda user: user.has_group("brand_core.group_brand_platform_admin")
            and (not user.company_id or user.company_id == self.company_id)
            and (not self.company_id or self.company_id in user.company_ids)
        )
        if not approvers:
            return self.env.ref("base.user_admin")
        return approvers

    def get_state_label(self):
        self.ensure_one()
        selection = dict(self._fields["state"].selection)
        return selection.get(self.state, self.state)

    def action_generate_watermark(self):
        for project in self:
            project._auto_generate_watermark()
        return True

    def _auto_generate_watermark(self):
        self.ensure_one()
        if not self.contract_attachment_ids:
            raise ValidationError(_("请先上传合同附件后再生成水印。"))

        if self.watermark_method == "manual":
            raise ValidationError(_("当前水印方案为人工确认，请直接使用“标记水印已确认”。"))

        if self.watermark_method == "auto":
            self._generate_system_watermark()

    def _generate_system_watermark(self):
        now = fields.Datetime.now()
        errors = []
        banner_text = _("品牌审核副本 - %s") % (self.code or self.name)

        class _AttachmentWrapper:
            def __init__(self, raw, mimetype):
                self.raw = raw
                self.mimetype = mimetype

        for attachment in self.contract_attachment_ids:
            data_b64 = attachment.with_context(bin_size=False).datas
            if not data_b64:
                errors.append(_("%s：附件内容为空") % attachment.display_name)
                continue
            raw = base64.b64decode(data_b64)
            wrapper = _AttachmentWrapper(raw, attachment.mimetype or "application/pdf")
            try:
                stream = pdf_utils.to_pdf_stream(wrapper)
                if not stream:
                    raise ValueError("stream error")
                stream.seek(0)
                watermarked = pdf_utils.add_banner(stream, text=banner_text, logo=False)
            except Exception as error:  # pylint: disable=broad-except
                errors.append(_("%(name)s：生成水印失败（%(error)s）") % {"name": attachment.display_name, "error": error})
                continue

            attachment.write(
                {
                    "datas": base64.b64encode(watermarked.getvalue()).decode(),
                    "mimetype": "application/pdf",
                    "crowdfunding_watermarked": True,
                    "crowdfunding_watermark_method": "auto",
                    "crowdfunding_watermark_date": now,
                }
            )

        if errors:
            raise ValidationError(_("自动生成水印失败：\n%s") % "\n".join(errors))

        self.write(
            {
                "contract_watermark_status": "ready",
                "watermark_generated_at": now,
            }
        )
