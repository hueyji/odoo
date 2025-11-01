# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.safe_eval import safe_eval


class StoreLinkGroup(models.Model):
    """
    门店互通组：负责标记加盟公司之间的库存/会员/财务共享范围。
    审批流程：草稿（门店编辑）→ 待品牌审批 → 生效 / 驳回，记录在 mail.thread。
    """

    _name = "store.link.group"
    _description = "门店互通组"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _check_company_auto = True

    name = fields.Char(string="互通组名称", required=True, tracking=True)
    company_id = fields.Many2one(
        "res.company",
        string="品牌公司",
        required=True,
        default=lambda self: self.env.company,
        help="品牌总部公司，所有互通门店需隶属于该品牌。",
    )
    owner_id = fields.Many2one(
        "res.users",
        string="负责人",
        required=True,
        default=lambda self: self.env.user,
        tracking=True,
        help="品牌审批负责人，负责处理互通申请与审批。",
    )
    member_company_ids = fields.Many2many(
        "res.company",
        "store_link_group_company_rel",
        "group_id",
        "company_id",
        string="互通门店",
        tracking=True,
        help="参与互通的加盟门店列表，每个门店须隶属于品牌公司。",
    )
    share_inventory = fields.Boolean(string="共享库存", tracking=True)
    share_member = fields.Boolean(string="共享会员", tracking=True)
    share_finance = fields.Boolean(string="共享财务", tracking=True)
    state = fields.Selection(
        [
            ("draft", "草稿"),
            ("pending", "待审批"),
            ("active", "生效"),
            ("rejected", "已驳回"),
        ],
        string="状态",
        default="draft",
        tracking=True,
    )
    description = fields.Text(string="互通说明")
    application_ids = fields.One2many(
        "store.link.group.application", "group_id", string="申请记录"
    )
    request_count = fields.Integer(
        string="待审批数量",
        compute="_compute_request_count",
    )

    _sql_constraints = [
        (
            "brand_group_unique",
            "UNIQUE(name, company_id)",
            "同一品牌下互通组名称必须唯一。",
        )
    ]

    @api.depends("application_ids.state")
    def _compute_request_count(self):
        for group in self:
            group.request_count = len(group.application_ids.filtered(lambda a: a.state == "pending"))

    @api.constrains("member_company_ids", "company_id")
    def _check_member_companies(self):
        for group in self:
            if not group.member_company_ids:
                raise ValidationError(_("互通组至少需要包含一个加盟门店。"))
            for company in group.member_company_ids:
                # 品牌公司本身可被包含以便总部参与共享
                if company == group.company_id:
                    continue
                if company.parent_id != group.company_id:
                    raise ValidationError(
                        _("门店 %s 不隶属于品牌公司 %s，无法加入互通组。")
                        % (company.name, group.company_id.name)
                    )

    def action_submit(self):
        for group in self:
            if group.state not in ("draft", "rejected"):
                raise UserError(_("仅草稿或已驳回的互通组可以提交审批。"))
            if group.application_ids.filtered(lambda a: a.state == "pending"):
                raise UserError(_("存在尚未处理的互通申请，请等待品牌审批。"))
            application = group._create_application_snapshot()
            group.state = "pending"
            group._schedule_brand_activity(application)
            group._post_state_message("pending", application)
        return True

    def action_approve(self):
        for group in self:
            if group.state != "pending":
                raise UserError(_("仅待审批的互通组可以执行品牌审批。"))
            application = group._get_latest_pending_application()
            if not application:
                raise UserError(_("未找到待审批的互通申请记录。"))
            group.state = "active"
            application.write(
                {
                    "state": "approved",
                    "approver_id": self.env.user.id,
                    "approved_date": fields.Datetime.now(),
                }
            )
            group.activity_feedback(["brand_core.mail_activity_brand_approval"])
            group._post_state_message("active", application)
        return True

    def action_reject(self, reason=None):
        for group in self:
            if group.state != "pending":
                raise UserError(_("仅待审批的互通组可以驳回。"))
            application = group._get_latest_pending_application()
            if not application:
                raise UserError(_("未找到待审批的互通申请记录。"))
            update_vals = {
                "state": "rejected",
                "approver_id": self.env.user.id,
                "approved_date": fields.Datetime.now(),
            }
            if reason:
                update_vals["reject_reason"] = reason
            application.write(update_vals)
            group.state = "rejected"
            group.activity_unlink(["brand_core.mail_activity_brand_approval"])
            group._post_state_message("rejected", application, extra_body=reason)
        return True

    def action_reset_to_draft(self):
        for group in self:
            if group.state not in ("rejected", "active"):
                raise UserError(_("仅在生效或已驳回状态下可重新编辑为草稿。"))
            group.state = "draft"
            group.activity_unlink(["brand_core.mail_activity_brand_approval"])
            group._post_state_message("draft")
        return True

    # Helpers -----------------------------------------------------------------

    def _create_application_snapshot(self):
        self.ensure_one()
        Application = self.env["store.link.group.application"].sudo()
        request_company = self.env.company
        if request_company not in (self.company_id | self.company_id.child_ids):
            raise UserError(_("申请公司不属于品牌 %s，无法提交互通申请。") % self.company_id.display_name)
        if request_company not in self.member_company_ids:
            # 门店发起时需将自身加入成员列表
            self.write({"member_company_ids": [(4, request_company.id)]})
        application_vals = {
            "name": _("%s 互通申请") % self.name,
            "group_id": self.id,
            "company_id": self.company_id.id,
            "request_company_id": request_company.id,
            "requested_member_ids": [(6, 0, self.member_company_ids.ids)],
            "share_inventory": self.share_inventory,
            "share_member": self.share_member,
            "share_finance": self.share_finance,
            "state": "pending",
        }
        return Application.create(application_vals)

    def _get_latest_pending_application(self):
        self.ensure_one()
        return self.application_ids.filtered(lambda a: a.state == "pending")[:1]

    def _schedule_brand_activity(self, application):
        self.ensure_one()
        activity_type = self.env.ref("brand_core.mail_activity_brand_approval", raise_if_not_found=False)
        user = self.owner_id
        if activity_type and user:
            self.activity_schedule(
                "brand_core.mail_activity_brand_approval",
                user_id=user.id,
                summary=_("互通申请待审批"),
                note=_("申请编号：%s") % application.display_name,
            )

    def _post_state_message(self, new_state, application=None, extra_body=None):
        self.ensure_one()
        subtype = self.env.ref("brand_core.mt_link_group", raise_if_not_found=False)
        messages = {
            "draft": _("互通组已重置为草稿，可继续编辑共享范围。"),
            "pending": _("互通组已提交审批，等待品牌负责人审核。"),
            "active": _("互通组审批通过，互通关系已生效。"),
            "rejected": _("互通组审批被驳回，请根据原因调整后重新提交。"),
        }
        body_parts = [messages.get(new_state, "")]
        if application:
            member_names = ", ".join(application.requested_member_ids.mapped("name")) or _("无")
            body_parts.append(
                _("申请公司：%s；互通门店：%s")
                % (application.request_company_id.display_name, member_names)
            )
        if extra_body:
            body_parts.append(extra_body)
        body = "<br/>".join(part for part in body_parts if part)
        self.message_post(body=body, subtype_id=subtype.id if subtype else False)

    def action_view_applications(self):
        self.ensure_one()
        action = self.env.ref("brand_core.action_store_link_group_application", raise_if_not_found=False)
        if not action:
            return False
        action_dict = action.read()[0]
        action_dict["domain"] = [("group_id", "=", self.id)]
        ctx = action_dict.get("context") or {}
        if isinstance(ctx, str):
            ctx = safe_eval(ctx)
        ctx.update({"default_group_id": self.id, "default_company_id": self.company_id.id})
        action_dict["context"] = ctx
        return action_dict


class StoreLinkGroupApplication(models.Model):
    """互通申请记录，用于保留门店提交快照与审批结果。"""

    _name = "store.link.group.application"
    _description = "互通申请"
    _inherit = ["mail.thread"]
    _check_company_auto = True
    _order = "create_date desc"

    name = fields.Char(string="标题", required=True, tracking=True)
    group_id = fields.Many2one(
        "store.link.group",
        string="互通组",
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        "res.company",
        string="品牌公司",
        required=True,
        default=lambda self: self.env.company,
        help="所属品牌公司，用于多公司记录规则校验。",
    )
    request_company_id = fields.Many2one(
        "res.company",
        string="申请公司",
        required=True,
        help="发起互通申请的门店公司。",
    )
    requested_member_ids = fields.Many2many(
        "res.company",
        "store_link_group_application_member_rel",
        "application_id",
        "company_id",
        string="申请互通门店",
        help="申请中包含的互通门店列表。",
    )
    share_inventory = fields.Boolean(string="申请共享库存", tracking=True)
    share_member = fields.Boolean(string="申请共享会员", tracking=True)
    share_finance = fields.Boolean(string="申请共享财务", tracking=True)
    state = fields.Selection(
        [
            ("pending", "待审批"),
            ("approved", "已通过"),
            ("rejected", "已驳回"),
        ],
        string="审批状态",
        default="pending",
        tracking=True,
    )
    reason = fields.Text(string="申请说明")
    reject_reason = fields.Text(string="驳回原因")
    approver_id = fields.Many2one("res.users", string="审批人", tracking=True)
    approved_date = fields.Datetime(string="审批时间", tracking=True)

    @api.constrains("requested_member_ids", "group_id")
    def _check_requested_members(self):
        for application in self:
            if not application.requested_member_ids:
                raise ValidationError(_("互通申请必须至少包含一个门店。"))
            for company in application.requested_member_ids:
                if company.parent_id != application.group_id.company_id and company != application.group_id.company_id:
                    raise ValidationError(
                        _("门店 %s 不属于品牌 %s，无法加入申请。")
                        % (company.name, application.group_id.company_id.name)
                    )
