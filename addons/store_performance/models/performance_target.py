from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class StorePerformanceTarget(models.Model):
    _name = "store.performance.target"
    _description = "业绩目标"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "period_start desc, employee_id"

    name = fields.Char(string="目标名称", required=True, tracking=True)
    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        string="员工",
        required=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="公司",
        required=True,
        default=lambda self: self.env.company.id,
    )
    period_type = fields.Selection(
        selection=[
            ("daily", "按日"),
            ("monthly", "按月"),
        ],
        string="目标周期",
        default="monthly",
        required=True,
    )
    period_start = fields.Date(string="开始日期", required=True)
    period_end = fields.Date(string="结束日期", required=True)
    target_amount = fields.Monetary(string="目标销售额", required=True, currency_field="currency_id")
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        string="币种",
        required=True,
        default=lambda self: self.env.company.currency_id.id,
    )
    note = fields.Text(string="说明")

    _sql_constraints = [
        (
            "performance_target_unique",
            "unique(employee_id, company_id, period_type, period_start)",
            "该员工该周期的目标已存在。",
        )
    ]

    @api.model
    def _get_period_bounds(self, period_type, reference_date):
        if period_type == "daily":
            return reference_date, reference_date
        start = reference_date.replace(day=1)
        end = (start + relativedelta(months=1)) - relativedelta(days=1)
        return start, end

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            period_start = fields.Date.to_date(vals["period_start"])
            start, end = self._get_period_bounds(vals.get("period_type", "monthly"), period_start)
            vals["period_start"] = start
            vals["period_end"] = end
            if not vals.get("name") and vals.get("employee_id"):
                employee = self.env["hr.employee"].browse(vals["employee_id"])
                employee_name = employee.name or "员工"
                if vals["period_type"] == "monthly":
                    vals["name"] = f"{employee_name} {start.strftime('%Y-%m')} 目标"
                else:
                    vals["name"] = f"{employee_name} {start} 目标"
        targets = super().create(vals_list)
        targets._update_performance_records()
        return targets

    def write(self, vals):
        res = super().write(vals)
        self._update_performance_records()
        return res

    def unlink(self):
        records = self.mapped("employee_id")
        period_info = [(target.employee_id, target.company_id, target.period_type, target.period_start) for target in self]
        res = super().unlink()
        if period_info:
            PerformanceRecord = self.env["store.performance.record"]
            for employee, company, period_type, period_start in period_info:
                record = PerformanceRecord.search(
                    [
                        ("employee_id", "=", employee.id),
                        ("company_id", "=", company.id),
                        ("period_type", "=", period_type),
                        ("period_start", "=", period_start),
                    ],
                    limit=1,
                )
                if record:
                    record.refresh_target_amount()
        return res

    @api.model
    def _compute_target_amount_for_record(self, record):
        targets = self.search(
            [
                ("employee_id", "=", record.employee_id.id),
                ("company_id", "=", record.company_id.id),
                ("period_type", "=", record.period_type),
                ("period_start", "=", record.period_start),
            ]
        )
        return sum(target.target_amount for target in targets)

    def _update_performance_records(self):
        PerformanceRecord = self.env["store.performance.record"]
        for target in self:
            record = PerformanceRecord._get_or_create_record(
                target.employee_id,
                target.company_id,
                target.period_start,
                target.period_type,
            )
            record.refresh_target_amount()
