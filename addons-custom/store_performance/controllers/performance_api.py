from odoo import fields, http
from odoo.exceptions import AccessError
from odoo.http import request


class PerformanceAPI(http.Controller):
    def _ensure_user(self):
        if not request.env.user.has_group("store_performance.group_store_performance_user"):
            raise AccessError("当前账号无权访问业绩数据。")

    def _ensure_manager(self):
        if not request.env.user.has_group("store_performance.group_store_performance_manager"):
            raise AccessError("当前账号无权修改业绩目标。")

    @http.route("/api/performance/summary", type="json", auth="user", methods=["POST"], csrf=False)
    def performance_summary(self, **payload):
        self._ensure_user()
        params = payload or request.jsonrequest or {}
        employee_id = params.get("employee_id") or request.env.user.employee_id.id
        period_type = params.get("period_type", "month")
        date_str = params.get("date")
        employee = request.env["hr.employee"].browse(employee_id)
        if not employee:
            raise AccessError("员工不存在或无权查看。")
        company = employee.company_id or request.env.company
        target_date = fields.Date.from_string(date_str) if date_str else fields.Date.context_today(request.env.user)
        performance_env = request.env["store.performance.record"].sudo()
        record = performance_env.get_or_create_period_record(employee, period_type, target_date, company)
        return {
            "employee": {
                "id": employee.id,
                "name": employee.name,
                "job": employee.job_id.name,
            },
            "period": {
                "type": record.period_type,
                "start": record.period_start.strftime("%Y-%m-%d") if record.period_start else None,
                "end": record.period_end.strftime("%Y-%m-%d") if record.period_end else None,
            },
            "metrics": {
                "sales_amount": record.sales_amount,
                "commission_amount": record.commission_amount,
                "target_amount": record.target_amount,
                "achievement_rate": record.achievement_rate,
                "order_count": record.order_count,
            },
            "state": record.state,
        }

    @http.route("/api/performance/targets", type="json", auth="user", methods=["POST"], csrf=False)
    def set_performance_target(self, **payload):
        self._ensure_manager()
        params = payload or request.jsonrequest or {}
        employee_id = params.get("employee_id")
        if not employee_id:
            raise AccessError("缺少员工标识。")
        period_type = params.get("period_type", "month")
        date_str = params.get("date")
        target_amount = params.get("target_amount")
        if target_amount is None:
            raise AccessError("缺少目标金额。")
        employee = request.env["hr.employee"].browse(employee_id)
        if not employee:
            raise AccessError("员工不存在或无权设置目标。")
        company = employee.company_id or request.env.company
        target_date = fields.Date.from_string(date_str) if date_str else fields.Date.context_today(request.env.user)
        performance_env = request.env["store.performance.record"].sudo()
        record = performance_env.get_or_create_period_record(employee, period_type, target_date, company)
        record.write({"target_amount": float(target_amount)})
        return {
            "message": "目标已更新",
            "performance_id": record.id,
            "target_amount": record.target_amount,
        }
