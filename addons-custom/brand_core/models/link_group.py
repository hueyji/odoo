from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class StoreLinkGroup(models.Model):
    _name = "store.link.group"
    _description = "门店互通组"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "code desc, name"

    code = fields.Char(
        string="互通编号",
        readonly=True,
        copy=False,
        tracking=True,
    )
    name = fields.Char(string="互通组名称", required=True, tracking=True)
    brand_company_id = fields.Many2one(
        "res.company",
        string="品牌总部",
        help="互通组归属的品牌总部，通常为成员门店的上级公司。",
        tracking=True,
    )
    owner_id = fields.Many2one(
        "res.partner",
        string="负责人",
        tracking=True,
        help="通常为拥有多个门店的投资人或老板。",
    )
    state = fields.Selection(
        selection=[
            ("draft", "草稿"),
            ("active", "已生效"),
            ("suspended", "已暂停"),
        ],
        string="状态",
        default="draft",
        tracking=True,
    )
    member_company_ids = fields.Many2many(
        "res.company",
        "store_link_group_company_rel",
        "group_id",
        "company_id",
        string="成员门店",
        tracking=True,
        help="互通组内允许共享资源的门店列表。",
    )
    share_inventory = fields.Boolean(
        string="共享库存",
        default=True,
        tracking=True,
    )
    share_member = fields.Boolean(
        string="共享会员",
        default=True,
        tracking=True,
    )
    share_finance = fields.Boolean(
        string="共享财务",
        default=False,
        tracking=True,
    )
    approval_user_id = fields.Many2one(
        "res.users",
        string="最后审批人",
        readonly=True,
    )
    approval_date = fields.Datetime(
        string="审批时间",
        readonly=True,
    )
    note = fields.Html(string="备注", sanitize=True)
    active = fields.Boolean(default=True)
    company_count = fields.Integer(
        string="门店数量",
        compute="_compute_company_count",
        store=True,
    )
    application_ids = fields.One2many(
        "store.link.group.application",
        "group_id",
        string="申请记录",
    )
    application_count = fields.Integer(
        string="申请数量",
        compute="_compute_application_count",
    )

    @api.depends("member_company_ids")
    def _compute_company_count(self):
        for record in self:
            record.company_count = len(record.member_company_ids)

    @api.depends("application_ids")
    def _compute_application_count(self):
        for record in self:
            record.application_count = len(record.application_ids)

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env.ref(
            "brand_core.sequence_store_link_group",
            raise_if_not_found=False,
        )
        for vals in vals_list:
            if not vals.get("code") and sequence:
                vals["code"] = sequence.next_by_id()
            if not vals.get("brand_company_id"):
                member_company_ids = vals.get("member_company_ids", [])
                brand_company = False
                for command in member_company_ids:
                    if not isinstance(command, (tuple, list)):
                        continue
                    if len(command) < 3:
                        continue
                    companies = self.env["res.company"]
                    if command[0] == 4:
                        companies = companies.browse(command[1])
                    elif command[0] == 6:
                        companies = companies.browse(command[2])
                    else:
                        continue
                    parent = companies.filtered(lambda c: c.parent_id).mapped("parent_id")[:1]
                    if parent:
                        brand_company = parent
                        break
                vals["brand_company_id"] = (
                    brand_company.id if brand_company else self.env.company.id
                )
        groups = super().create(vals_list)
        groups._sync_state_from_members()
        return groups

    def write(self, vals):
        res = super().write(vals)
        if {"member_company_ids"} & set(vals.keys()):
            self._sync_state_from_members()
        return res

    def _sync_state_from_members(self):
        for record in self:
            if record.state == "draft" and record.member_company_ids:
                record.state = "active"

    @api.constrains("member_company_ids")
    def _check_same_owner(self):
        for record in self:
            if not record.member_company_ids:
                continue
            owner_ids = record.member_company_ids.mapped("partner_id")
            if record.owner_id and record.owner_id not in owner_ids:
                continue
            parent_ids = set(record.member_company_ids.mapped("parent_id").ids)
            if len(parent_ids) > 1:
                raise ValidationError(_("互通组内门店需属于同一品牌或拥有相同上级公司。"))
            if not record.brand_company_id and parent_ids:
                record.brand_company_id = list(parent_ids)[0]

    def action_activate(self):
        self._ensure_brand_admin()
        for record in self:
            record.write(
                {
                    "state": "active",
                    "approval_user_id": self.env.user.id,
                    "approval_date": fields.Datetime.now(),
                }
            )

    def action_suspend(self):
        self._ensure_brand_admin()
        for record in self:
            record.write(
                {
                    "state": "suspended",
                    "approval_user_id": self.env.user.id,
                    "approval_date": fields.Datetime.now(),
                }
            )

    def action_view_applications(self):
        self.ensure_one()
        action = self.env.ref(
            "brand_core.action_store_link_group_application", raise_if_not_found=False
        )
        if not action:
            return False
        result = action.read()[0]
        domain = result.get("domain") or []
        domain = [("group_id", "=", self.id)]
        context = dict(result.get("context") or {})
        context.update(
            {
                "default_group_id": self.id,
            }
        )
        result.update(
            {
                "domain": domain,
                "context": context,
            }
        )
        return result

    def name_get(self):
        result = []
        for record in self:
            display = record.name
            if record.code:
                display = f"[{record.code}] {display}"
            result.append((record.id, display))
        return result

    def _ensure_brand_admin(self):
        if not self.env.user.has_group("base.group_system"):
            raise UserError(_("只有品牌管理员可以执行该操作。"))


class StoreLinkGroupApplication(models.Model):
    _name = "store.link.group.application"
    _description = "互通组申请"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"

    name = fields.Char(
        string="申请编号",
        readonly=True,
        default=lambda self: self.env["ir.sequence"].next_by_code(
            "store.link.group.application"
        ),
    )
    group_id = fields.Many2one(
        "store.link.group",
        string="目标互通组",
        tracking=True,
    )
    proposed_group_name = fields.Char(
        string="拟创建互通组名称",
        help="若为空表示申请加入现有互通组；若填写则审批通过后会新建互通组。",
    )
    request_company_id = fields.Many2one(
        "res.company",
        string="申请门店",
        required=True,
        tracking=True,
        default=lambda self: self.env.company,
    )
    requested_member_ids = fields.Many2many(
        "res.company",
        "store_link_group_application_company_rel",
        "application_id",
        "company_id",
        string="申请成员门店",
        help="审批通过后会加入互通组的门店，默认包含申请门店本身。",
    )
    share_inventory = fields.Boolean(
        string="共享库存",
        default=True,
        tracking=True,
    )
    share_member = fields.Boolean(
        string="共享会员",
        default=True,
        tracking=True,
    )
    share_finance = fields.Boolean(
        string="共享财务",
        default=False,
        tracking=True,
    )
    brand_company_id = fields.Many2one(
        "res.company",
        string="品牌总部",
        help="审批由该品牌总部的管理员负责。",
    )
    state = fields.Selection(
        selection=[
            ("draft", "草稿"),
            ("submitted", "待审批"),
            ("approved", "已通过"),
            ("rejected", "已拒绝"),
        ],
        string="状态",
        default="draft",
        tracking=True,
    )
    decision_note = fields.Text(string="审批意见")
    decision_user_id = fields.Many2one(
        "res.users",
        string="审批人",
        readonly=True,
    )
    decision_date = fields.Datetime(
        string="审批时间",
        readonly=True,
    )
    description = fields.Text(string="申请说明")

    @api.model_create_multi
    def create(self, vals_list):
        applications = super().create(vals_list)
        for app in applications:
            if not app.requested_member_ids:
                app.write(
                    {
                        "requested_member_ids": [(4, app.request_company_id.id)],
                    }
                )
        return applications

    def action_submit(self):
        for record in self:
            record.ensure_one()
            if record.state != "draft":
                raise UserError(_("只有草稿状态的申请可以提交。"))
            if not record.group_id and not record.proposed_group_name:
                raise UserError(_("请选择需要加入的互通组或填写拟创建的互通组名称。"))
            brand_company = (
                record.group_id.brand_company_id
                or record.request_company_id.parent_id
            )
            record.write(
                {
                    "state": "submitted",
                    "brand_company_id": brand_company.id if brand_company else False,
                }
            )

    def action_approve(self):
        if not self.env.user.has_group("base.group_system"):
            raise UserError(_("只有品牌管理员可以审批互通申请。"))
        for record in self:
            record._do_approve()

    def _do_approve(self):
        self.ensure_one()
        if self.state not in ("submitted", "draft"):
            raise UserError(_("只有草稿或待审批的申请可以通过审批。"))
        if self.group_id:
            group = self.group_id
            self._apply_updates_to_group(group)
        else:
            group_vals = {
                "name": self.proposed_group_name,
                "brand_company_id": (
                    self.brand_company_id.id
                    or self.request_company_id.parent_id.id
                ),
                "member_company_ids": [
                    (6, 0, self.requested_member_ids.ids)
                ],
                "share_inventory": self.share_inventory,
                "share_member": self.share_member,
                "share_finance": self.share_finance,
                "state": "active",
                "owner_id": self.request_company_id.partner_id.id,
            }
            group = self.env["store.link.group"].create(group_vals)
            self.group_id = group.id
        group.action_activate()
        self.write(
            {
                "state": "approved",
                "decision_user_id": self.env.user.id,
                "decision_date": fields.Datetime.now(),
            }
        )

    def _apply_updates_to_group(self, group):
        group.ensure_one()
        if not group.member_company_ids:
            group.write({"member_company_ids": [(6, 0, self.requested_member_ids.ids)]})
        else:
            commands = []
            for company in self.requested_member_ids:
                if company not in group.member_company_ids:
                    commands.append((4, company.id))
            if commands:
                group.write({"member_company_ids": commands})
        group_values = {
            "share_inventory": self.share_inventory,
            "share_member": self.share_member,
            "share_finance": self.share_finance,
        }
        group.write(group_values)

    def action_reject(self):
        if not self.env.user.has_group("base.group_system"):
            raise UserError(_("只有品牌管理员可以审批互通申请。"))
        for record in self:
            if record.state not in ("submitted", "draft"):
                raise UserError(_("只有草稿或待审批的申请可以拒绝。"))
            record.write(
                {
                    "state": "rejected",
                    "decision_user_id": self.env.user.id,
                    "decision_date": fields.Datetime.now(),
                }
            )
