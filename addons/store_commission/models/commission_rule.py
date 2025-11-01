from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class StoreCommissionRule(models.Model):
    _name = "store.commission.rule"
    _description = "提成规则"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "sequence, id"

    name = fields.Char(string="规则名称", required=True, tracking=True)
    code = fields.Char(string="规则编号", copy=False, tracking=True)
    sequence = fields.Integer(string="显示顺序", default=10)
    description = fields.Text(string="规则说明")
    rule_type = fields.Selection(
        selection=[
            ("product", "指定商品"),
            ("category", "商品分类"),
            ("recharge", "储值充值"),
            ("combo", "套餐组合"),
            ("order_amount", "订单金额"),
        ],
        string="规则类型",
        default="product",
        required=True,
        tracking=True,
    )
    rate_type = fields.Selection(
        selection=[
            ("percent", "百分比"),
            ("fixed", "固定金额"),
            ("ladder", "阶梯提成"),
        ],
        string="计算方式",
        default="percent",
        required=True,
        tracking=True,
    )
    rate_value = fields.Float(string="提成数值", tracking=True)
    ladder_definition = fields.Text(string="阶梯配置说明")
    target_product_ids = fields.Many2many(
        comodel_name="product.product",
        relation="store_commission_rule_product_rel",
        column1="rule_id",
        column2="product_id",
        string="适用商品",
        tracking=True,
    )
    target_category_ids = fields.Many2many(
        comodel_name="product.category",
        relation="store_commission_rule_category_rel",
        column1="rule_id",
        column2="category_id",
        string="适用分类",
        tracking=True,
    )
    applicable_company_ids = fields.Many2many(
        comodel_name="res.company",
        relation="store_commission_rule_company_rel",
        column1="rule_id",
        column2="company_id",
        string="适用公司",
    )
    applicable_employee_ids = fields.Many2many(
        comodel_name="hr.employee",
        relation="store_commission_rule_employee_rel",
        column1="rule_id",
        column2="employee_id",
        string="适用员工",
        tracking=True,
    )
    applicable_job_ids = fields.Many2many(
        comodel_name="hr.job",
        relation="store_commission_rule_job_rel",
        column1="rule_id",
        column2="job_id",
        string="适用岗位",
    )
    period_type = fields.Selection(
        selection=[
            ("daily", "按日"),
            ("weekly", "按周"),
            ("monthly", "按月"),
            ("quarterly", "按季度"),
        ],
        string="阶梯周期",
        default="monthly",
        tracking=True,
    )
    effective_start_date = fields.Date(string="生效日期", tracking=True)
    effective_end_date = fields.Date(string="失效日期", tracking=True)
    state = fields.Selection(
        selection=[
            ("draft", "草稿"),
            ("active", "生效"),
            ("archived", "归档"),
        ],
        string="规则状态",
        default="draft",
        tracking=True,
    )
    version_number = fields.Char(
        string="版本号",
        default="v1",
        tracking=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="维护公司",
        default=lambda self: self.env.company,
        required=True,
    )
    active = fields.Boolean(string="是否启用", default=True)

    _sql_constraints = [
        (
            "code_unique",
            "unique(code)",
            "规则编号必须唯一。",
        )
    ]

    @api.constrains("rate_type", "rate_value")
    def _check_rate_value(self):
        for record in self:
            if record.rate_type in ("percent", "fixed") and record.rate_value <= 0:
                raise ValidationError("提成数值必须大于 0。")
            if record.rate_type == "percent" and record.rate_value > 100:
                raise ValidationError("百分比提成数值不能超过 100。")

    def _is_within_date_range(self, order_date):
        self.ensure_one()
        if self.effective_start_date and order_date.date() < self.effective_start_date:
            return False
        if self.effective_end_date and order_date.date() > self.effective_end_date:
            return False
        return True

    def _is_employee_applicable(self, employee):
        self.ensure_one()
        if not employee:
            return False
        if self.applicable_employee_ids and employee not in self.applicable_employee_ids:
            return False
        if self.applicable_job_ids and employee.job_id not in self.applicable_job_ids:
            return False
        if self.applicable_company_ids and employee.company_id not in self.applicable_company_ids:
            return False
        return True

    def _is_company_applicable(self, company):
        self.ensure_one()
        if not company:
            return True
        if self.applicable_company_ids and company not in self.applicable_company_ids:
            return False
        if self.company_id and self.company_id != company:
            return False
        return True

    def _match_line(self, line_dict):
        self.ensure_one()
        product = line_dict.get("product")
        category = line_dict.get("category")
        if self.target_product_ids and product not in self.target_product_ids:
            return False
        if self.target_category_ids:
            if not category:
                return False
            category_ids = set(self.target_category_ids.ids)
            current = category
            while current:
                if current.id in category_ids:
                    break
                current = current.parent_id
            else:
                return False
        if self.rule_type == "combo" and not line_dict.get("is_combo"):
            return False
        return True

    def _compute_base_for_lines(self, order_ctx):
        subtotal = 0.0
        quantity = 0.0
        for line in order_ctx["lines"]:
            if self._match_line(line):
                subtotal += line.get("subtotal", 0.0)
                quantity += line.get("qty", 0.0)
        return subtotal, quantity

    def _parse_ladder_definition(self):
        self.ensure_one()
        if not self.ladder_definition:
            return []
        ladder = []
        for entry in self.ladder_definition.replace("\n", ";").split(";"):
            entry = entry.strip()
            if not entry:
                continue
            if ":" not in entry:
                raise ValidationError(_("阶梯配置格式应为 金额:提成比例，例如 1000:5"))
            threshold, rate = entry.split(":", 1)
            ladder.append((float(threshold.strip()), float(rate.strip())))
        ladder.sort(key=lambda item: item[0])
        return ladder

    def _compute_amount_from_base(self, base_amount, quantity):
        self.ensure_one()
        if base_amount <= 0 and quantity <= 0:
            return 0.0
        if self.rate_type == "percent":
            return base_amount * self.rate_value / 100.0
        if self.rate_type == "fixed":
            units = quantity if quantity else 1.0
            return self.rate_value * units
        ladder = self._parse_ladder_definition()
        applicable_rate = 0.0
        for threshold, rate in ladder:
            if base_amount >= threshold:
                applicable_rate = rate
            else:
                break
        return base_amount * applicable_rate / 100.0

    def compute_commission(self, order_ctx):
        results = []
        for rule in self:
            employee = order_ctx["employee"]
            company = order_ctx["company"]
            order_date = order_ctx["order_date"]
            if not rule.active or rule.state != "active":
                continue
            if not rule._is_company_applicable(company):
                continue
            if not rule._is_employee_applicable(employee):
                continue
            if not rule._is_within_date_range(order_date):
                continue
            if rule.rule_type in ("product", "category", "combo"):
                base_amount, quantity = rule._compute_base_for_lines(order_ctx)
            elif rule.rule_type == "order_amount":
                base_amount = order_ctx["amount_total"]
                quantity = 1.0
            elif rule.rule_type == "recharge":
                base_amount = order_ctx.get("recharge_amount", 0.0)
                quantity = 1.0 if base_amount else 0.0
            else:
                base_amount = 0.0
                quantity = 0.0
            amount = rule._compute_amount_from_base(base_amount, quantity)
            if amount > 0:
                results.append(
                    {
                        "rule": rule,
                        "amount": amount,
                        "base_amount": base_amount,
                        "quantity": quantity,
                    }
                )
        return results
