from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    responsible_employee_id = fields.Many2one(
        "hr.employee",
        string="责任员工",
        tracking=True,
        domain="[('company_id', '=', company_id)]",
        help="默认使用当前操作员对应的员工，可在确认前调整。",
    )
    assistant_employee_ids = fields.Many2many(
        "hr.employee",
        "sale_order_employee_rel",
        "order_id",
        "employee_id",
        string="协同员工",
        domain="[('company_id', '=', company_id)]",
    )
    commission_log_ids = fields.One2many(
        "store.commission.log",
        "sale_order_id",
        string="提成日志",
    )
    commission_total_amount = fields.Monetary(
        string="提成合计",
        currency_field="currency_id",
        compute="_compute_commission_totals",
    )
    commission_state = fields.Selection(
        [
            ("none", "未生成"),
            ("draft", "待审核"),
            ("confirmed", "已确认"),
            ("refunded", "已回滚"),
        ],
        string="提成状态",
        compute="_compute_commission_state",
        store=False,
    )

    @api.model
    def create(self, vals):
        if not vals.get("responsible_employee_id"):
            employee = self.env.user.employee_id
            if employee and (not vals.get("company_id") or employee.company_id.id == vals.get("company_id")):
                vals["responsible_employee_id"] = employee.id
        order = super().create(vals)
        if not order.assistant_employee_ids and order.responsible_employee_id:
            order.assistant_employee_ids = [(4, order.responsible_employee_id.id)]
        return order

    def write(self, vals):
        res = super().write(vals)
        if "responsible_employee_id" in vals:
            for order in self:
                if order.responsible_employee_id and order.responsible_employee_id not in order.assistant_employee_ids:
                    order.assistant_employee_ids = [(4, order.responsible_employee_id.id)]
        return res

    def _get_commission_participants(self):
        self.ensure_one()
        participants = self.responsible_employee_id | self.assistant_employee_ids
        return participants.filtered(lambda emp: not emp.company_id or emp.company_id == self.company_id)

    def _compute_commission_totals(self):
        for order in self:
            order.commission_total_amount = sum(order.commission_log_ids.mapped("commission_amount"))

    def _compute_commission_state(self):
        for order in self:
            logs = order.commission_log_ids
            if not logs:
                order.commission_state = "none"
            elif any(log.state == "draft" for log in logs):
                order.commission_state = "draft"
            elif all(log.state == "refunded" for log in logs):
                order.commission_state = "refunded"
            else:
                order.commission_state = "confirmed"

    def action_confirm(self):
        res = super().action_confirm()
        self._generate_commission_logs()
        return res

    def _generate_commission_logs(self):
        CommissionLog = self.env["store.commission.log"]
        values_map = self._prepare_commission_log_values()
        for order_id, payload in values_map.items():
            order = payload["order"]
            vals_list = payload["vals"]
            draft_logs = order.commission_log_ids.filtered(lambda l: l.state == "draft")
            if draft_logs:
                draft_logs.unlink()
            if vals_list:
                CommissionLog.create(vals_list)

    def _prepare_commission_log_values(self):
        Rule = self.env["store.commission.rule"]
        values_map = {}
        for order in self:
            vals_list = []
            values_map[order.id] = {"order": order, "vals": vals_list}
            if order.state not in ("sale", "done"):
                continue
            rules = Rule.search(
                [
                    ("company_id", "=", order.company_id.id),
                    ("is_effective", "=", True),
                    ("state", "=", "active"),
                    ("active", "=", True),
                ],
                order="sequence asc, id desc",
            )
            if not rules:
                continue
            line_results = []
            order_results = []
            for rule in rules:
                if rule.rule_type == "order":
                    order_results.extend(rule.compute_order_commission(order))
                    continue
                for line in order.order_line:
                    if line.display_type:
                        continue
                    line_results.extend(rule.compute_line_commission(line))
            all_results = line_results + order_results
            if not all_results:
                continue
            grouped = defaultdict(float)
            for vals in all_results:
                key = (
                    vals.get("employee_id"),
                    vals.get("rule_id"),
                    vals.get("sale_order_line_id"),
                    vals.get("ladder_line_id"),
                )
                grouped[key] += vals.get("commission_amount", 0.0)
            for (employee_id, rule_id, line_id, ladder_line_id), amount in grouped.items():
                base_amount = 0.0
                quantity = 0.0
                if line_id:
                    line = self.env["sale.order.line"].browse(line_id)
                    base_amount = line.price_total
                    quantity = line.product_uom_qty
                else:
                    base_amount = order.amount_total
                    quantity = sum(order.order_line.filtered(lambda l: not l.display_type).mapped("product_uom_qty"))
                vals = {
                    "sale_order_id": order.id,
                    "sale_order_line_id": line_id,
                    "employee_id": employee_id,
                    "rule_id": rule_id,
                    "ladder_line_id": ladder_line_id,
                    "base_amount": base_amount,
                    "quantity": quantity,
                    "commission_amount": amount,
                    "company_id": order.company_id.id,
                    "currency_id": order.currency_id.id,
                }
                vals_list.append(vals)
        return values_map


    def compute_commission_preview(self):
        self.ensure_one()
        values_map = self._prepare_commission_log_values()
        payload = values_map.get(self.id, {})
        vals_list = payload.get("vals", [])
        result = []
        for vals in vals_list:
            employee = self.env['hr.employee'].browse(vals.get('employee_id'))
            rule = self.env['store.commission.rule'].browse(vals.get('rule_id'))
            result.append(
                {
                    "employee_id": employee.id,
                    "employee_name": employee.name,
                    "rule_id": rule.id,
                    "rule_name": rule.name,
                    "base_amount": vals.get('base_amount'),
                    "commission_amount": vals.get('commission_amount'),
                    "sale_order_line_id": vals.get('sale_order_line_id'),
                    "quantity": vals.get('quantity'),
                }
            )
        return result
    def action_recompute_commission(self):
        for order in self:
            if any(log.state == "confirmed" for log in order.commission_log_ids):
                raise ValidationError(_("已存在确认的提成日志，请先回滚后再重新计算。"))
        self._generate_commission_logs()


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    participant_employee_ids = fields.Many2many(
        "hr.employee",
        "sale_order_line_employee_rel",
        "line_id",
        "employee_id",
        string="参与员工",
        domain="[('company_id', '=', company_id)]",
        help="默认继承自订单责任员工，可按行调整。",
    )

    def _get_commission_participants(self):
        self.ensure_one()
        employees = self.participant_employee_ids
        if not employees and self.order_id:
            employees = self.order_id._get_commission_participants()
        return employees.filtered(lambda emp: not emp.company_id or emp.company_id == self.company_id)

    @api.onchange("order_id")
    def _onchange_order_id_assign_employees(self):
        if self.order_id and not self.participant_employee_ids:
            participants = self.order_id._get_commission_participants()
            self.participant_employee_ids = participants
