from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class StorePerformanceRecord(models.Model):
    _name = "store.performance.record"
    _description = "门店个人业绩"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "period_start desc, employee_id"

    name = fields.Char(string="业绩名称", compute="_compute_name", store=True)
    period_type = fields.Selection(
        selection=[
            ("daily", "按日"),
            ("monthly", "按月"),
        ],
        string="统计周期",
        required=True,
        default="monthly",
        tracking=True,
    )
    period_start = fields.Date(string="开始日期", required=True, tracking=True)
    period_end = fields.Date(string="结束日期", required=True)
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
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        string="币种",
        required=True,
        default=lambda self: self.env.company.currency_id.id,
    )
    pending_sales_amount = fields.Monetary(string="待确认销售额", default=0.0, currency_field="currency_id")
    confirmed_sales_amount = fields.Monetary(string="已确认销售额", default=0.0, currency_field="currency_id")
    pending_commission_amount = fields.Monetary(string="待确认提成", default=0.0, currency_field="currency_id")
    confirmed_commission_amount = fields.Monetary(string="已确认提成", default=0.0, currency_field="currency_id")
    pending_order_count = fields.Integer(string="待确认订单数", default=0)
    confirmed_order_count = fields.Integer(string="已确认订单数", default=0)
    target_amount = fields.Monetary(string="目标销售额", default=0.0, currency_field="currency_id")
    achievement_rate = fields.Float(string="目标达成率", compute="_compute_achievement_rate", store=True)
    last_update = fields.Datetime(string="最后更新", default=fields.Datetime.now, tracking=True)

    _sql_constraints = [
        (
            "performance_unique_period",
            "unique(employee_id, company_id, period_type, period_start)",
            "同一周期的业绩记录已存在。",
        )
    ]

    @api.depends("employee_id", "period_start", "period_end", "period_type")
    def _compute_name(self):
        for record in self:
            if record.period_type == "daily":
                name = f"{record.employee_id.name} {record.period_start}"
            else:
                name = f"{record.employee_id.name} {record.period_start.strftime('%Y-%m')}"
            record.name = name

    @api.depends("confirmed_sales_amount", "target_amount")
    def _compute_achievement_rate(self):
        for record in self:
            if record.target_amount:
                record.achievement_rate = (record.confirmed_sales_amount / record.target_amount) * 100
            else:
                record.achievement_rate = 0.0

    @api.model
    def _get_period_bounds(self, period_type, reference_datetime):
        reference_date = reference_datetime.date() if hasattr(reference_datetime, "date") else reference_datetime
        if period_type == "daily":
            start = reference_date
            end = reference_date
        else:
            start = reference_date.replace(day=1)
            end = (start + relativedelta(months=1)) - relativedelta(days=1)
        return start, end

    @api.model
    def _get_or_create_record(self, employee, company, trigger_datetime, period_type="monthly"):
        start, end = self._get_period_bounds(period_type, trigger_datetime)
        record = self.search(
            [
                ("employee_id", "=", employee.id),
                ("company_id", "=", company.id),
                ("period_type", "=", period_type),
                ("period_start", "=", start),
            ],
            limit=1,
        )
        if not record:
            record = self.create(
                {
                    "employee_id": employee.id,
                    "company_id": company.id,
                    "period_type": period_type,
                    "period_start": start,
                    "period_end": end,
                    "currency_id": company.currency_id.id,
                }
            )
        return record

    def _bucket_fields(self, state):
        if state == "pending":
            return ("pending_commission_amount", "pending_sales_amount", "pending_order_count")
        if state == "confirmed":
            return ("confirmed_commission_amount", "confirmed_sales_amount", "confirmed_order_count")
        return None

    def _apply_log_delta(self, log, previous_values=None):
        previous_values = previous_values or {}
        prev_state = previous_values.get("state")
        new_state = log.state
        values = {
            "pending_commission_amount": self.pending_commission_amount,
            "pending_sales_amount": self.pending_sales_amount,
            "pending_order_count": self.pending_order_count,
            "confirmed_commission_amount": self.confirmed_commission_amount,
            "confirmed_sales_amount": self.confirmed_sales_amount,
            "confirmed_order_count": self.confirmed_order_count,
        }

        prev_bucket = self._bucket_fields(prev_state)
        if prev_bucket:
            commission_field, sales_field, count_field = prev_bucket
            values[commission_field] -= previous_values.get("amount", 0.0)
            values[sales_field] -= previous_values.get("base_amount", 0.0)
            values[count_field] -= previous_values.get("order_count", 0)

        new_bucket = self._bucket_fields(new_state)
        if new_bucket:
            commission_field, sales_field, count_field = new_bucket
            values[commission_field] += log.amount
            values[sales_field] += log.base_amount
            values[count_field] += previous_values.get("order_count", 1)

        for key in values:
            if isinstance(values[key], (int, float)) and values[key] < 0:
                values[key] = 0
        values["last_update"] = fields.Datetime.now()
        self.write(values)

    def refresh_target_amount(self):
        Target = self.env["store.performance.target"]
        for record in self:
            target_amount = Target._compute_target_amount_for_record(record)
            record.write({"target_amount": target_amount, "last_update": fields.Datetime.now()})
