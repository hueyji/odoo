from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class StoreCommissionRule(models.Model):
    _name = "store.commission.rule"
    _description = "提成规则"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "sequence, id desc"
    _check_company_auto = True

    RULE_TYPE_SELECTION = [
        ("product", "按单品"),
        ("category", "按分类"),
        ("order", "整单提成"),
        ("recharge", "充值奖励"),
    ]

    RATE_TYPE_SELECTION = [
        ("percent", "按比例"),
        ("fixed", "固定金额"),
        ("ladder", "阶梯提成"),
    ]

    SCOPE_SELECTION = [
        ("all", "门店全员"),
        ("job", "指定职务"),
        ("employee", "指定员工"),
    ]

    LADDER_PERIOD_SELECTION = [
        ("day", "按日"),
        ("week", "按周"),
        ("month", "按月"),
    ]

    name = fields.Char(string="规则名称", required=True, tracking=True)
    code = fields.Char(string="规则编号", copy=False, tracking=True)
    sequence = fields.Integer(string="优先级", default=10)
    active = fields.Boolean(string="启用", default=True, tracking=True)
    state = fields.Selection(
        [("draft", "草稿"), ("active", "生效"), ("archived", "归档")],
        string="状态",
        default="draft",
        tracking=True,
    )
    rule_type = fields.Selection(
        selection=RULE_TYPE_SELECTION,
        string="规则类型",
        required=True,
        default="product",
        tracking=True,
    )
    rate_type = fields.Selection(
        selection=RATE_TYPE_SELECTION,
        string="计算方式",
        required=True,
        default="percent",
        tracking=True,
    )
    rate_value = fields.Float(
        string="提成数值",
        help="当为按比例时填写百分比（0-100），固定金额单位为币种。",
        tracking=True,
        digits="Payroll Rate",
    )
    ladder_period = fields.Selection(
        selection=LADDER_PERIOD_SELECTION,
        string="阶梯周期",
        default="month",
        help="阶梯提成累计周期，默认按月计算。",
        tracking=True,
    )
    ladder_line_ids = fields.One2many(
        "store.commission.rule.ladder",
        "rule_id",
        string="阶梯配置",
    )
    scope_type = fields.Selection(
        selection=SCOPE_SELECTION,
        string="适用范围",
        default="all",
        required=True,
        tracking=True,
    )
    job_ids = fields.Many2many(
        "hr.job",
        "store_commission_rule_job_rel",
        "rule_id",
        "job_id",
        string="适用职务",
    )
    employee_ids = fields.Many2many(
        "hr.employee",
        "store_commission_rule_employee_rel",
        "rule_id",
        "employee_id",
        string="适用员工",
    )
    company_id = fields.Many2one(
        "res.company",
        string="公司",
        required=True,
        default=lambda self: self.env.company.id,
        index=True,
    )
    start_date = fields.Date(string="生效日期", tracking=True)
    end_date = fields.Date(string="失效日期", tracking=True)
    version_code = fields.Char(string="版本号", default="1.0", tracking=True)
    previous_rule_id = fields.Many2one(
        "store.commission.rule",
        string="上一版本",
        tracking=True,
    )
    product_ids = fields.Many2many(
        "product.product",
        "store_commission_rule_product_rel",
        "rule_id",
        "product_id",
        string="适用商品",
    )
    category_ids = fields.Many2many(
        "product.category",
        "store_commission_rule_categ_rel",
        "rule_id",
        "categ_id",
        string="适用分类",
    )
    description = fields.Text(string="规则说明")
    is_effective = fields.Boolean(
        string="当前有效",
        compute="_compute_is_effective",
        store=True,
    )

    _sql_constraints = [
        ("code_company_unique", "unique(code, company_id)", "规则编号在同一公司内必须唯一。"),
    ]

    @api.model
    def create(self, vals):
        if not vals.get("code"):
            vals["code"] = self.env["ir.sequence"].next_by_code("store.commission.rule") or _("新规则")
        record = super().create(vals)
        record._check_dates()
        return record

    def write(self, vals):
        res = super().write(vals)
        if "start_date" in vals or "end_date" in vals or "state" in vals or "active" in vals:
            self._check_dates()
        return res

    @api.model
    def _get_today(self):
        return fields.Date.context_today(self)

    @api.depends("start_date", "end_date", "state", "active")
    def _compute_is_effective(self):
        today = self._get_today()
        for rule in self:
            if not rule.active or rule.state != "active":
                rule.is_effective = False
                continue
            if rule.start_date and rule.start_date > today:
                rule.is_effective = False
                continue
            if rule.end_date and rule.end_date < today:
                rule.is_effective = False
                continue
            rule.is_effective = True

    def _check_dates(self):
        for record in self:
            if record.start_date and record.end_date and record.start_date > record.end_date:
                raise ValidationError(_("生效日期不能晚于失效日期。"))

    def action_activate(self):
        for rule in self:
            rule._check_dates()
            rule.write({"state": "active", "active": True})

    def action_archive(self):
        for rule in self:
            rule.write({"state": "archived", "active": False})

    def action_reset_to_draft(self):
        self.write({"state": "draft", "active": True})

    # --- 业务逻辑 ----
    def _match_order_line(self, line):
        self.ensure_one()
        if self.rule_type == "product":
            return bool(self.product_ids & line.product_id)
        if self.rule_type == "category":
            return bool(self.category_ids & line.product_id.categ_id)
        if self.rule_type == "order":
            return True
        if self.rule_type == "recharge":
            # 充值类提成在会员模块中处理，这里不匹配普通销售行。
            return False
        return False

    def _get_applicable_employees(self, line):
        participants = line._get_commission_participants()
        if not participants:
            return participants
        if self.scope_type == "all":
            return participants
        if self.scope_type == "job":
            return participants.filtered(lambda emp: emp.job_id in self.job_ids)
        if self.scope_type == "employee":
            return participants.filtered(lambda emp: emp in self.employee_ids)
        return self.env["hr.employee"]

    def is_applicable_for_company(self, company):
        self.ensure_one()
        return self.company_id == company and self.is_effective

    def compute_line_commission(self, line):
        self.ensure_one()
        if not self.is_applicable_for_company(line.company_id):
            return []
        if not self._match_order_line(line):
            return []
        employees = self._get_applicable_employees(line)
        if not employees:
            return []

        base_amount = line.price_total
        quantity = line.product_uom_qty
        commission_amount, ladder_line = self._compute_amount(base_amount, quantity)
        if not commission_amount:
            return []

        result = []
        share_amount = commission_amount / len(employees)
        for employee in employees:
            result.append(
                {
                    "employee_id": employee.id,
                    "base_amount": base_amount,
                    "quantity": quantity,
                    "commission_amount": share_amount,
                    "rule_id": self.id,
                    "sale_order_line_id": line.id,
                    "ladder_line_id": ladder_line.id if ladder_line else False,
                }
            )
        return result

    def compute_order_commission(self, order):
        self.ensure_one()
        if self.rule_type != "order":
            return []
        if not self.is_applicable_for_company(order.company_id):
            return []
        employees = order._get_commission_participants()
        if self.scope_type == "job":
            employees = employees.filtered(lambda emp: emp.job_id in self.job_ids)
        elif self.scope_type == "employee":
            employees = employees.filtered(lambda emp: emp in self.employee_ids)
        if not employees:
            return []
        base_amount = order.amount_total
        total_qty = sum(order.order_line.mapped("product_uom_qty"))
        commission_amount, ladder_line = self._compute_amount(base_amount, total_qty)
        if not commission_amount:
            return []
        share_amount = commission_amount / len(employees)
        return [
            {
                "employee_id": emp.id,
                "base_amount": base_amount,
                "quantity": total_qty,
                "commission_amount": share_amount,
                "rule_id": self.id,
                "sale_order_id": order.id,
                "ladder_line_id": ladder_line.id if ladder_line else False,
            }
            for emp in employees
        ]

    def _compute_amount(self, base_amount, quantity):
        self.ensure_one()
        if self.rate_type == "percent":
            return base_amount * (self.rate_value / 100.0), False
        if self.rate_type == "fixed":
            return self.rate_value, False
        if self.rate_type == "ladder":
            ladder_line = self._select_ladder_line(base_amount, quantity)
            if not ladder_line:
                return 0.0, False
            return ladder_line.compute_amount(base_amount), ladder_line
        return 0.0, False

    def _select_ladder_line(self, base_amount, quantity):
        self.ensure_one()
        ordered_lines = self.ladder_line_ids.sorted("sequence")
        for ladder in ordered_lines:
            value = base_amount if ladder.threshold_type == "amount" else quantity
            if ladder.match_value(value):
                return ladder
        return False


class StoreCommissionRuleLadder(models.Model):
    _name = "store.commission.rule.ladder"
    _description = "提成阶梯"
    _order = "sequence, id asc"
    _check_company_auto = True

    THRESHOLD_SELECTION = [
        ("amount", "金额"),
        ("quantity", "数量"),
    ]

    RATE_SELECTION = [
        ("percent", "按比例"),
        ("fixed", "固定金额"),
    ]

    rule_id = fields.Many2one(
        "store.commission.rule",
        string="提成规则",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(string="排序", default=10)
    threshold_type = fields.Selection(
        selection=THRESHOLD_SELECTION,
        string="阶梯依据",
        default="amount",
        required=True,
    )
    min_value = fields.Float(string="起始值", required=True, default=0.0)
    max_value = fields.Float(string="结束值")
    ladder_rate_type = fields.Selection(
        selection=RATE_SELECTION,
        string="提成方式",
        default="percent",
        required=True,
    )
    ladder_rate_value = fields.Float(
        string="提成数值",
        required=True,
        digits="Payroll Rate",
        help="按比例时填写百分比（0-100）；固定金额时填写币种金额。",
    )

    company_id = fields.Many2one(
        related="rule_id.company_id",
        string="公司",
        store=True,
        readonly=True,
    )

    def match_value(self, value):
        self.ensure_one()
        if value < self.min_value:
            return False
        if self.max_value and value > self.max_value:
            return False
        return True

    def compute_amount(self, base_amount):
        self.ensure_one()
        if self.ladder_rate_type == "percent":
            return base_amount * (self.ladder_rate_value / 100.0)
        return self.ladder_rate_value
