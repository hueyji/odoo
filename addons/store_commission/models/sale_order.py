from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    commission_employee_id = fields.Many2one(
        comodel_name="hr.employee",
        string="责任员工",
        required=True,
        domain="[('company_id', 'in', [company_id, False])]",
        help="用于提成计算的责任员工，仅允许单人负责。",
    )

    @api.model
    def _find_employee_for_user(self, user, company_id=None):
        if not user:
            return False
        domain = [("user_id", "=", user.id)]
        if company_id:
            domain = [
                "|",
                ("company_id", "=", company_id),
                ("company_id", "=", False),
            ] + domain
        return self.env["hr.employee"].sudo().search(domain, limit=1, order="company_id desc")

    @api.model
    def _prepare_commission_employee(self, vals):
        if vals.get("commission_employee_id"):
            return self.env["hr.employee"].browse(vals["commission_employee_id"])

        company_id = vals.get("company_id") or self.env.company.id
        user_id = vals.get("user_id") or self.env.uid
        user = self.env["res.users"].browse(user_id)
        employee = self._find_employee_for_user(user, company_id)
        if employee:
            return employee
        raise UserError(_("请先为当前操作用户关联员工档案，再创建销售订单。"))

    @api.model
    def create(self, vals):
        employee = self._prepare_commission_employee(vals)
        vals["commission_employee_id"] = employee.id
        order = super().create(vals)
        order._sync_user_from_employee()
        return order

    def write(self, vals):
        if "commission_employee_id" in vals:
            employees = self.env["hr.employee"].browse(vals["commission_employee_id"])
            company_map = {employee.company_id.id or False for employee in employees}
            for order in self:
                if employees and order.company_id.id not in company_map and False not in company_map:
                    raise UserError(_("责任员工与订单公司不匹配。"))

        if (
            "user_id" in vals
            and "commission_employee_id" not in vals
            and not self.env.context.get("skip_commission_employee_sync")
        ):
            user = self.env["res.users"].browse(vals["user_id"])
            for order in self:
                employee = order._find_employee_for_user(user, order.company_id.id)
                if not employee:
                    raise UserError(_("该销售人员缺少关联的员工档案，请补充后再变更责任员工。"))
                order_vals = vals.copy()
                order_vals["commission_employee_id"] = employee.id
                super(SaleOrder, order).write(order_vals)
            return True

        res = super().write(vals)
        if "commission_employee_id" in vals and "user_id" not in vals:
            self._sync_user_from_employee()
        return res

    def _sync_user_from_employee(self):
        for order in self:
            employee = order.commission_employee_id
            if employee and employee.user_id and order.user_id != employee.user_id:
                order.with_context(skip_commission_employee_sync=True).write(
                    {"user_id": employee.user_id.id}
                )

    def _commission_service(self):
        return self.env["store.commission.service"]

    def _compute_commission_logs(self):
        CommissionLog = self.env["store.commission.log"]
        for order in self:
            if not order.commission_employee_id:
                continue
            computed = self._commission_service().compute_commission(order, "sale")
            for item in computed:
                rule = item["rule"]
                existing_log = CommissionLog.search(
                    [("sale_order_id", "=", order.id), ("rule_id", "=", rule.id)],
                    limit=1,
                )
                values = {
                    "order_type": "sale",
                    "sale_order_id": order.id,
                    "company_id": order.company_id.id,
                    "employee_id": order.commission_employee_id.id,
                    "rule_id": rule.id,
                    "amount": item["amount"],
                    "base_amount": item["base_amount"],
                    "quantity": item["quantity"],
                    "currency_id": item["currency"].id,
                    "order_name": order.name,
                    "trigger_type": "order_confirm",
                    "state": "pending",
                }
                if existing_log:
                    existing_log.write(values)
                else:
                    CommissionLog.create(values)

    def _cancel_commission_logs(self, reason=None, trigger="cancel"):
        logs = self.env["store.commission.log"].search(
            [("sale_order_id", "in", self.ids)]
        )
        if logs:
            logs.action_cancel(
                reason=reason or _("订单取消，提成回滚。"), trigger=trigger
            )

    def action_confirm(self):
        res = super().action_confirm()
        sale_orders = self.filtered(lambda so: so.state in ("sale", "done"))
        sale_orders._compute_commission_logs()
        return res

    def action_cancel(self):
        self._cancel_commission_logs(reason=_("销售订单作废。"))
        return super().action_cancel()
