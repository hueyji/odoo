from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PosOrder(models.Model):
    _inherit = "pos.order"

    commission_employee_id = fields.Many2one(
        comodel_name="hr.employee",
        string="责任员工",
        required=True,
        domain="[('company_id', 'in', [company_id, False])]",
        help="用于提成计算的责任员工，将自动同步至POS员工字段。",
    )

    @api.model
    def _find_employee_for_user(self, user_id, company_id=None):
        if not user_id:
            return False
        domain = [("user_id", "=", user_id)]
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

        if vals.get("employee_id"):
            employee = self.env["hr.employee"].browse(vals["employee_id"])
            if employee:
                return employee

        company_id = vals.get("company_id")
        session = False
        if vals.get("session_id"):
            session = self.env["pos.session"].browse(vals["session_id"])
            company_id = company_id or session.company_id.id

        user_id = vals.get("user_id")
        if not user_id and session:
            user_id = session.user_id.id

        employee = self._find_employee_for_user(user_id, company_id)
        if employee:
            return employee

        raise UserError(_("请为当前操作用户配置关联的员工档案后再创建 POS 订单。"))

    @api.model
    def create(self, vals):
        employee = self._prepare_commission_employee(vals)
        vals["commission_employee_id"] = employee.id
        if not vals.get("employee_id"):
            vals["employee_id"] = employee.id
        order = super().create(vals)
        order._sync_pos_employee()
        return order

    def write(self, vals):
        if "commission_employee_id" in vals:
            employee = self.env["hr.employee"].browse(vals["commission_employee_id"])
            for order in self:
                company_id = order.company_id.id
                if employee and employee.company_id and employee.company_id.id != company_id:
                    raise UserError(_("责任员工与订单公司不匹配。"))

        if (
            "employee_id" in vals
            and "commission_employee_id" not in vals
            and not self.env.context.get("skip_commission_employee_update")
        ):
            employee = self.env["hr.employee"].browse(vals["employee_id"])
            if not employee:
                raise UserError(_("请为该 POS 订单指定责任员工。"))
            vals = vals.copy()
            vals["commission_employee_id"] = employee.id
            return super().write(vals)

        res = super().write(vals)
        if "commission_employee_id" in vals and not self.env.context.get("skip_commission_employee_update"):
            self._sync_pos_employee()
        return res

    def _sync_pos_employee(self):
        for order in self:
            employee = order.commission_employee_id
            if employee and order.employee_id != employee:
                order.with_context(skip_commission_employee_update=True).write({"employee_id": employee.id})

    def _commission_service(self):
        return self.env["store.commission.service"]

    def _compute_commission_logs(self, trigger_type="order_confirm"):
        CommissionLog = self.env["store.commission.log"]
        for order in self:
            if not order.commission_employee_id:
                continue
            if order.refunded_order_ids:
                order.refunded_order_ids._cancel_commission_logs(
                    reason=_("POS 退款单 %s 触发回滚。") % (order.name,),
                    trigger="refund",
                )
                continue
            computed = self._commission_service().compute_commission(order, "pos")
            for item in computed:
                rule = item["rule"]
                existing_log = CommissionLog.search(
                    [("pos_order_id", "=", order.id), ("rule_id", "=", rule.id)],
                    limit=1,
                )
                values = {
                    "order_type": "pos",
                    "pos_order_id": order.id,
                    "company_id": order.company_id.id,
                    "employee_id": order.commission_employee_id.id,
                    "rule_id": rule.id,
                    "amount": item["amount"],
                    "base_amount": item["base_amount"],
                    "quantity": item["quantity"],
                    "currency_id": item["currency"].id,
                    "order_name": order.name,
                    "trigger_type": trigger_type,
                    "state": "pending",
                }
                if existing_log:
                    existing_log.write(values)
                else:
                    CommissionLog.create(values)

    def _cancel_commission_logs(self, reason=None, trigger="cancel"):
        logs = self.env["store.commission.log"].search([("pos_order_id", "in", self.ids)])
        if logs:
            logs.action_cancel(
                reason=reason or _("POS 订单取消，提成回滚。"), trigger=trigger
            )

    def action_pos_order_paid(self):
        res = super().action_pos_order_paid()
        if res:
            self._compute_commission_logs()
        return res

    def action_pos_order_cancel(self):
        self._cancel_commission_logs(reason=_("POS 订单作废。"))
        return super().action_pos_order_cancel()
