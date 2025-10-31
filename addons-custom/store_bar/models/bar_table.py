from datetime import datetime, time, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class StoreBarTable(models.Model):
    _name = "store.bar.table"
    _description = "吧台桌台"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "sequence, name"
    _check_company_auto = True

    STATE_SELECTION = [
        ("available", "空闲"),
        ("reserved", "已预定"),
        ("seated", "占用"),
        ("billing", "结账中"),
        ("maintenance", "维护中"),
    ]

    name = fields.Char(
        string="桌台名称",
        required=True,
        tracking=True,
        default=lambda self: _("新桌台"),
    )
    code = fields.Char(string="桌台编号", tracking=True)
    sequence = fields.Integer(string="排序", default=10)
    area = fields.Selection(
        [
            ("bar", "吧台区"),
            ("lounge", "沙发区"),
            ("vip", "包厢"),
            ("outdoor", "露台"),
        ],
        string="所在区域",
        default="bar",
        tracking=True,
    )
    capacity = fields.Integer(string="建议人数", default=2, tracking=True)
    state = fields.Selection(
        selection=STATE_SELECTION,
        string="状态",
        default="available",
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="公司",
        default=lambda self: self.env.company.id,
        required=True,
        index=True,
    )
    responsible_employee_id = fields.Many2one(
        "hr.employee",
        string="值台负责人",
        domain="[('company_id', '=', company_id)]",
        tracking=True,
    )
    reminder_threshold_minutes = fields.Integer(
        string="提醒阈值（分钟）",
        default=90,
        help="顾客占用超过该时长将触发服务提醒。",
    )
    current_order_id = fields.Many2one(
        "store.bar.order",
        string="当前订单",
        copy=False,
        tracking=True,
    )
    order_ids = fields.One2many(
        "store.bar.order",
        "table_id",
        string="订单记录",
    )
    current_session_start = fields.Datetime(
        string="当前占用开始时间",
        tracking=True,
    )
    occupancy_minutes = fields.Integer(
        string="当前占用时长（分钟）",
        compute="_compute_occupancy_minutes",
        store=True,
    )
    need_service_reminder = fields.Boolean(
        string="需要服务提醒",
        compute="_compute_need_service_reminder",
        store=True,
    )
    today_turnover_count = fields.Integer(
        string="今日翻台次数",
        compute="_compute_today_metrics",
        store=False,
    )
    today_sales_total = fields.Monetary(
        string="今日销售额",
        compute="_compute_today_metrics",
        store=False,
        currency_field="currency_id",
    )
    today_avg_ticket = fields.Monetary(
        string="今日客单价",
        compute="_compute_today_metrics",
        store=False,
        currency_field="currency_id",
    )
    turnover_target = fields.Integer(
        string="翻台目标",
        default=3,
        help="用于计算翻台率的目标次数。",
    )
    today_turnover_rate = fields.Float(
        string="今日翻台率",
        compute="_compute_today_metrics",
        store=False,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="币种",
        default=lambda self: self.env.company.currency_id.id,
    )
    reserve_partner_id = fields.Many2one(
        "res.partner",
        string="预定会员",
        tracking=True,
    )
    reserve_mobile = fields.Char(string="预定手机号")
    reserve_start = fields.Datetime(string="预定开始时间", tracking=True)
    reserve_end = fields.Datetime(string="预定结束时间", tracking=True)
    last_checkout_at = fields.Datetime(string="上次结账时间", tracking=True)
    note = fields.Text(string="备注")
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("code_company_unique", "unique(code, company_id)", "同一公司内桌台编号必须唯一。"),
    ]

    @api.model
    def create(self, vals):
        if not vals.get("code"):
            vals["code"] = self.env["ir.sequence"].next_by_code("store.bar.table")
        if not vals.get("name") or vals.get("name") == _("新桌台"):
            vals["name"] = vals["code"] or _("新桌台")
        return super().create(vals)

    def write(self, vals):
        res = super().write(vals)
        if "state" in vals:
            for table in self:
                if table.state == "seated" and not table.current_session_start:
                    table.current_session_start = fields.Datetime.now()
                if table.state in {"available", "maintenance"}:
                    table.current_session_start = False
        if "current_order_id" in vals:
            for table in self:
                if not table.current_order_id and table.state == "seated":
                    table.state = "available"
        return res

    @api.depends("state", "current_session_start")
    def _compute_occupancy_minutes(self):
        now = fields.Datetime.now()
        for table in self:
            if table.state not in {"seated", "billing"} or not table.current_session_start:
                table.occupancy_minutes = 0
                continue
            delta = now - table.current_session_start
            table.occupancy_minutes = max(int(delta.total_seconds() / 60), 0)

    @api.depends("occupancy_minutes", "state", "reminder_threshold_minutes")
    def _compute_need_service_reminder(self):
        for table in self:
            if table.state == "billing":
                table.need_service_reminder = table.occupancy_minutes >= 10
            elif table.state == "seated":
                table.need_service_reminder = (
                    table.reminder_threshold_minutes > 0
                    and table.occupancy_minutes >= table.reminder_threshold_minutes
                )
            else:
                table.need_service_reminder = False

    def _compute_today_metrics(self):
        today = fields.Date.context_today(self)
        start_dt = datetime.combine(today, time.min)
        end_dt = start_dt + timedelta(days=1)
        Order = self.env["store.bar.order"]
        for table in self:
            orders = Order.search(
                [
                    ("table_id", "=", table.id),
                    ("state", "=", "done"),
                    ("closed_at", ">=", start_dt),
                    ("closed_at", "<", end_dt),
                ]
            )
            count = len(orders)
            total = sum(orders.mapped("amount_total"))
            table.today_turnover_count = count
            table.today_sales_total = total
            table.today_avg_ticket = total / count if count else 0.0
            table.today_turnover_rate = (
                (count / table.turnover_target) if table.turnover_target else 0.0
            )

    def action_reserve(self, partner_id=False, start=None, end=None, mobile=False):
        for table in self:
            if table.state not in {"available", "maintenance"}:
                raise ValidationError(_("桌台 %s 当前不可预定。", table.name))
            table.write(
                {
                    "state": "reserved",
                    "reserve_partner_id": partner_id,
                    "reserve_start": start,
                    "reserve_end": end,
                    "reserve_mobile": mobile,
                }
            )
            table.message_post(body=_("已为会员预定桌台，时间：%s - %s") % (start, end))

    def action_cancel_reservation(self):
        for table in self:
            if table.state != "reserved":
                continue
            table.write(
                {
                    "state": "available",
                    "reserve_partner_id": False,
                    "reserve_start": False,
                    "reserve_end": False,
                    "reserve_mobile": False,
                }
            )

    def action_assign_order(self, order):
        self.ensure_one()
        if self.company_id != order.company_id:
            raise ValidationError(_("桌台与订单必须属于同一公司。"))
        self.write(
            {
                "current_order_id": order.id,
                "state": "seated",
                "current_session_start": fields.Datetime.now(),
            }
        )

    def action_mark_billing(self):
        for table in self:
            if table.state not in {"seated", "reserved"}:
                continue
            table.write({"state": "billing"})

    def action_release(self):
        for table in self:
            table.write(
                {
                    "state": "available",
                    "current_order_id": False,
                    "current_session_start": False,
                }
            )

    def action_mark_maintenance(self):
        self.write({"state": "maintenance", "current_order_id": False})

    def action_trigger_service_reminder(self):
        for table in self.filtered("need_service_reminder"):
            table.message_post(body=_("桌台占用超时，请安排员工前往服务。"))

    @api.model
    def cron_refresh_table_metrics(self):
        tables = self.search([("state", "in", ["seated", "billing"])])
        tables._compute_occupancy_minutes()
        tables._compute_need_service_reminder()
