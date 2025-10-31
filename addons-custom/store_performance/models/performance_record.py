from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models


class StorePerformanceRecord(models.Model):
    _name = "store.performance.record"
    _description = "门店员工业绩记录"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "period_start desc, commission_amount desc"
    _check_company_auto = True

    PERIOD_SELECTION = [
        ("day", "按日"),
        ("week", "按周"),
        ("month", "按月"),
    ]

    STATE_SELECTION = [
        ("draft", "草稿"),
        ("in_progress", "进行中"),
        ("achieved", "已达成"),
        ("warning", "预警"),
    ]

    name = fields.Char(string="名称", compute="_compute_name", store=True)
    employee_id = fields.Many2one(
        "hr.employee",
        string="员工",
        required=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="公司",
        required=True,
        default=lambda self: self.env.company.id,
        index=True,
    )
    period_type = fields.Selection(
        selection=PERIOD_SELECTION,
        string="统计周期",
        required=True,
        default="month",
        tracking=True,
    )
    period_start = fields.Date(string="开始日期", required=True, tracking=True)
    period_end = fields.Date(string="结束日期", required=True, tracking=True)
    target_amount = fields.Monetary(
        string="业绩目标金额",
        currency_field="currency_id",
        tracking=True,
        default=0.0,
    )
    sales_amount = fields.Monetary(
        string="销售额",
        currency_field="currency_id",
        tracking=True,
        default=0.0,
    )
    commission_amount = fields.Monetary(
        string="提成金额",
        currency_field="currency_id",
        tracking=True,
        default=0.0,
    )
    order_count = fields.Integer(string="订单数", tracking=True, default=0)
    currency_id = fields.Many2one(
        "res.currency",
        string="币种",
        required=True,
        default=lambda self: self.env.company.currency_id.id,
    )
    state = fields.Selection(
        selection=STATE_SELECTION,
        string="状态",
        default="draft",
        tracking=True,
    )
    achievement_rate = fields.Float(string="达成率(%)", compute="_compute_achievement", store=True, digits="Payroll Rate")
    notification_sent = fields.Boolean(string="已提醒", default=False)
    commission_log_ids = fields.Many2many(
        "store.commission.log",
        "store_performance_commission_rel",
        "performance_id",
        "commission_id",
        string="关联提成",
        readonly=True,
    )

    _sql_constraints = [
        (
            "record_unique_employee_period",
            "unique(employee_id, period_type, period_start, company_id)",
            "同一员工同一统计周期只能有一条业绩记录。",
        )
    ]

    @api.depends("employee_id", "period_start", "period_type")
    def _compute_name(self):
        for record in self:
            if record.employee_id and record.period_start:
                record.name = "%s %s" % (record.employee_id.name, record.period_start.strftime("%Y-%m-%d"))
            else:
                record.name = _("未命名业绩记录")

    @api.depends("sales_amount", "target_amount")
    def _compute_achievement(self):
        for record in self:
            if record.target_amount:
                record.achievement_rate = round((record.sales_amount / record.target_amount) * 100, 2)
            else:
                record.achievement_rate = 0.0

    @api.model
    def _get_period_bounds(self, date, period_type):
        date = fields.Date.to_date(date)
        if period_type == "day":
            start = date
            end = date
        elif period_type == "week":
            start = date - timedelta(days=date.weekday())
            end = start + timedelta(days=6)
        else:  # month
            start = date.replace(day=1)
            end = (start + relativedelta(months=1)) - timedelta(days=1)
        return start, end

    @api.model
    def _get_period_type_from_log(self, log):
        period = log.rule_id.ladder_period or "month"
        if period not in dict(self.PERIOD_SELECTION):
            period = "month"
        return period

    @api.model
    def _get_or_create_from_log(self, log):
        period_type = self._get_period_type_from_log(log)
        log_dt = fields.Datetime.to_datetime(log.date)
        start, end = self._get_period_bounds(log_dt.date(), period_type)
        record = self.search(
            [
                ("employee_id", "=", log.employee_id.id),
                ("company_id", "=", log.company_id.id),
                ("period_type", "=", period_type),
                ("period_start", "=", start),
            ],
            limit=1,
        )
        if record:
            return record
        vals = {
            "employee_id": log.employee_id.id,
            "company_id": log.company_id.id,
            "currency_id": log.currency_id.id,
            "period_type": period_type,
            "period_start": start,
            "period_end": end,
            "state": "in_progress",
            "sales_amount": 0.0,
            "commission_amount": 0.0,
            "order_count": 0,
            "target_amount": 0.0,
        }
        return self.create(vals)

    @api.model
    def get_or_create_period_record(self, employee, period_type, target_date=None, company=None, currency=None):
        if period_type not in dict(self.PERIOD_SELECTION):
            period_type = "month"
        target_date = target_date or fields.Date.context_today(self)
        company = company or self.env.company
        currency = currency or company.currency_id
        start, end = self._get_period_bounds(target_date, period_type)
        record = self.search(
            [
                ("employee_id", "=", employee.id),
                ("company_id", "=", company.id),
                ("period_type", "=", period_type),
                ("period_start", "=", start),
            ],
            limit=1,
        )
        if record:
            return record
        vals = {
            "employee_id": employee.id,
            "company_id": company.id,
            "currency_id": currency.id,
            "period_type": period_type,
            "period_start": start,
            "period_end": end,
            "state": "draft",
        }
        return self.create(vals)

    def apply_commission_log(self, log):
        record = self._get_or_create_from_log(log)
        new_sales = record.sales_amount + log.base_amount
        new_commission = record.commission_amount + log.commission_amount
        new_order_count = record.order_count + (1 if log.commission_amount > 0 else 0)
        new_state = record.state
        if record.target_amount:
            new_state = "achieved" if new_sales >= record.target_amount else "in_progress"
        elif new_state == "draft":
            new_state = "in_progress"
        record.write(
            {
                "sales_amount": new_sales,
                "commission_amount": new_commission,
                "order_count": new_order_count,
                "state": new_state,
            }
        )
        record.commission_log_ids = [(4, log.id)]
        return record

    @api.model
    def cron_rebuild_performance(self):
        """定时任务：重新汇总近 30 天提成，保证数据一致。"""
        thirty_days_ago = fields.Datetime.now() - relativedelta(days=30)
        logs = self.env["store.commission.log"].search(
            [
                ("state", "=", "confirmed"),
                ("date", ">=", thirty_days_ago),
            ]
        )
        for employee in logs.mapped("employee_id"):
            self.search([("employee_id", "=", employee.id), ("period_start", ">=", thirty_days_ago.date())]).write(
                {
                    "sales_amount": 0.0,
                    "commission_amount": 0.0,
                    "order_count": 0,
                    "state": "draft",
                    "commission_log_ids": [(5, 0, 0)],
                }
            )
        for log in logs:
            self.apply_commission_log(log)
