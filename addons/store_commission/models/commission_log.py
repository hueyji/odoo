from odoo import api, fields, models
from odoo.exceptions import ValidationError


class StoreCommissionLog(models.Model):
    _name = "store.commission.log"
    _description = "提成日志"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "trigger_datetime desc, id desc"

    name = fields.Char(string="提成编号", required=True, copy=False, default=lambda self: self._default_name())
    order_type = fields.Selection(
        selection=[
            ("sale", "销售订单"),
            ("pos", "POS订单"),
            ("recharge", "储值"),
        ],
        string="来源类型",
        required=True,
        tracking=True,
    )
    sale_order_id = fields.Many2one(
        comodel_name="sale.order",
        string="销售订单",
        ondelete="set null",
        index=True,
    )
    pos_order_id = fields.Many2one(
        comodel_name="pos.order",
        string="POS订单",
        ondelete="set null",
        index=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="所属公司",
        required=True,
        default=lambda self: self.env.company,
    )
    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        string="责任员工",
        required=True,
        tracking=True,
    )
    rule_id = fields.Many2one(
        comodel_name="store.commission.rule",
        string="提成规则",
        tracking=True,
        ondelete="restrict",
    )
    amount = fields.Monetary(string="提成金额", currency_field="currency_id", tracking=True)
    base_amount = fields.Monetary(string="计提基数", currency_field="currency_id")
    quantity = fields.Float(string="涉及数量")
    trigger_type = fields.Selection(
        selection=[
            ("order_confirm", "订单确认"),
            ("refund", "退款回滚"),
            ("cancel", "订单作废"),
            ("manual", "手工调整"),
        ],
        string="触发类型",
        default="order_confirm",
        tracking=True,
    )
    order_name = fields.Char(string="来源单号")
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        string="币种",
        default=lambda self: self.env.company.currency_id,
        required=True,
    )
    state = fields.Selection(
        selection=[
            ("pending", "待确认"),
            ("confirmed", "已确认"),
            ("cancelled", "已回滚"),
        ],
        string="状态",
        default="pending",
        tracking=True,
    )
    trigger_datetime = fields.Datetime(string="触发时间", default=fields.Datetime.now, tracking=True)
    note = fields.Text(string="备注")

    _sql_constraints = [
        (
            "sale_rule_unique",
            "unique(sale_order_id, rule_id)",
            "同一销售订单不能重复生成提成日志。",
        ),
        (
            "pos_rule_unique",
            "unique(pos_order_id, rule_id)",
            "同一 POS 订单不能重复生成提成日志。",
        ),
    ]

    def _default_name(self):
        return self.env["ir.sequence"].next_by_code("store.commission.log") or "COMMISSION"

    @api.constrains("order_type", "sale_order_id", "pos_order_id")
    def _check_order_links(self):
        for record in self:
            if record.order_type == "sale" and not record.sale_order_id:
                raise ValidationError("销售提成日志必须关联销售订单。")
            if record.order_type == "pos" and not record.pos_order_id:
                raise ValidationError("POS 提成日志必须关联 POS 订单。")

    def action_set_pending(self):
        self.write(
            {
                "state": "pending",
                "trigger_datetime": fields.Datetime.now(),
            }
        )

    def action_confirm(self):
        self.write(
            {
                "state": "confirmed",
                "trigger_datetime": fields.Datetime.now(),
            }
        )

    def action_cancel(self, reason=None, trigger="cancel"):
        values = {
            "state": "cancelled",
            "trigger_datetime": fields.Datetime.now(),
            "trigger_type": trigger,
        }
        if reason:
            for record in self:
                record.note = "{}\n{}".format(record.note or "", reason).strip()
        self.write(values)

    def _bus_channel(self):
        self.ensure_one()
        return f"commission.notify.{self.company_id.id}"

    def _bus_payload(self, action):
        self.ensure_one()
        return {
            "action": action,
            "log_id": self.id,
            "order_type": self.order_type,
            "order_name": self.order_name,
            "employee_id": self.employee_id.id,
            "employee_name": self.employee_id.name,
            "amount": self.amount,
            "state": self.state,
            "trigger_type": self.trigger_type,
            "rule_id": self.rule_id.id if self.rule_id else False,
            "rule_name": self.rule_id.name if self.rule_id else "",
            "company_id": self.company_id.id,
            "timestamp": fields.Datetime.now(),
        }

    def _notify_realtime(self, action):
        bus = self.env["bus.bus"].sudo()
        for record in self:
            bus.sendone(record._bus_channel(), record._bus_payload(action))

    @api.model_create_multi
    def create(self, vals_list):
        logs = super().create(vals_list)
        logs._notify_realtime("created")
        return logs

    def write(self, vals):
        previous_states = {log.id: log.state for log in self}
        res = super().write(vals)
        for log in self:
            action = "updated"
            previous_state = previous_states.get(log.id)
            if previous_state != log.state:
                if log.state == "confirmed":
                    action = "confirmed"
                elif log.state == "cancelled":
                    action = "cancelled"
            log._notify_realtime(action)
        return res
