from odoo import _, fields, models


class BrandConfigCheck(models.Model):
    _name = "brand.config.check"
    _description = "品牌配置检查记录"
    _inherit = ["mail.thread"]
    _order = "create_date desc"

    name = fields.Char(
        string="检查编号",
        readonly=True,
        default=lambda self: self.env["ir.sequence"].next_by_code(
            "brand.config.check"
        ),
    )
    company_id = fields.Many2one(
        "res.company",
        string="品牌公司",
        default=lambda self: self.env.company,
        required=True,
    )
    state = fields.Selection(
        selection=[("draft", "草稿"), ("done", "已完成")],
        default="draft",
        tracking=True,
    )
    issue_count = fields.Integer(
        string="问题数量",
        readonly=True,
    )
    issue_summary = fields.Text(
        string="问题详情",
        readonly=True,
    )

    def action_run_checks(self):
        for record in self:
            issues = record._collect_issues()
            issue_text = "\n".join(f"{idx + 1}. {msg}" for idx, msg in enumerate(issues))
            record.write(
                {
                    "issue_count": len(issues),
                    "issue_summary": issue_text or _("配置完整，无需调整。"),
                    "state": "done",
                }
            )
            record.message_post(
                body=_("完成配置检查，共发现 %s 个问题。") % len(issues),
            )
        return True

    def _collect_issues(self):
        self.ensure_one()
        issues = []
        Store = self.env["res.company"].sudo()
        stores = Store.search(
            [
                ("company_role", "=", "store"),
                "|",
                ("parent_id", "=", self.company_id.id),
                ("parent_id", "=", False),
            ]
        )
        if not stores:
            issues.append(_("当前品牌下尚未配置任何门店。"))
            return issues

        for store in stores:
            if not store.store_owner_partner_id:
                issues.append(
                    _("门店【%s】缺少门店老板，请在公司表单中补充。") % store.display_name
                )
            if not store.aging_area_note:
                issues.append(
                    _("门店【%s】缺少陈化仓配置说明，建议填写陈化仓位置或编号。")
                    % store.display_name
                )
            group = store.default_link_group_id
            if not group:
                issues.append(
                    _("门店【%s】未设置默认互通组，无法参与库存或会员共享。")
                    % store.display_name
                )
            else:
                if store not in group.member_company_ids:
                    issues.append(
                        _(
                            "门店【%s】的默认互通组【%s】未包含该门店，请检查互通组成员。"
                        )
                        % (store.display_name, group.display_name)
                    )
                if len(group.member_company_ids) < 2:
                    issues.append(
                        _("互通组【%s】仅包含单一门店，建议补充其它门店。")
                        % group.display_name
                    )
        return issues
