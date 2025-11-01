from odoo import fields, http
from odoo.http import request


class StoreCommissionController(http.Controller):
    @http.route(
        "/api/v1/commissions/calculate",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def calculate_commission(self, **payload):
        order_type = payload.get("order_type")
        order_id = payload.get("order_id")
        if order_type not in ("sale", "pos"):
            return {"success": False, "message": "order_type 必须为 sale 或 pos"}
        if not order_id:
            return {"success": False, "message": "缺少 order_id 参数"}

        env = request.env
        order_model = "sale.order" if order_type == "sale" else "pos.order"
        order = env[order_model].browse(order_id)
        if not order.exists():
            return {"success": False, "message": "订单不存在或无访问权限"}
        service = env["store.commission.service"]
        items = service.compute_commission(order, order_type)
        data = []
        for item in items:
            rule = item["rule"]
            data.append(
                {
                    "rule_id": rule.id,
                    "rule_name": rule.name,
                    "order_id": order.id,
                    "order_name": order.name,
                    "employee_id": order.commission_employee_id.id if order.commission_employee_id else False,
                    "employee_name": order.commission_employee_id.name if order.commission_employee_id else "",
                    "amount": item["amount"],
                    "base_amount": item["base_amount"],
                    "quantity": item["quantity"],
                    "currency": item["currency"].name if item.get("currency") else "",
                }
            )
        return {"success": True, "data": data}

    @http.route(
        "/api/v1/commissions/logs",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def commission_logs(self, **payload):
        filters = payload.get("filters", {}) or {}
        limit = payload.get("limit", 80)
        offset = payload.get("offset", 0)
        domain = []
        if filters.get("employee_id"):
            domain.append(("employee_id", "=", filters["employee_id"]))
        if filters.get("order_type"):
            domain.append(("order_type", "=", filters["order_type"]))
        if filters.get("state"):
            domain.append(("state", "=", filters["state"]))
        if filters.get("company_id"):
            domain.append(("company_id", "=", filters["company_id"]))
        date_from = filters.get("date_from")
        date_to = filters.get("date_to")
        if date_from:
            domain.append(("trigger_datetime", ">=", date_from))
        if date_to:
            domain.append(("trigger_datetime", "<=", date_to))

        env = request.env
        logs = env["store.commission.log"].search(domain, limit=limit, offset=offset, order="trigger_datetime desc")
        data = []
        for log in logs:
            data.append(
                {
                    "id": log.id,
                    "name": log.name,
                    "order_type": log.order_type,
                    "order_name": log.order_name,
                    "state": log.state,
                    "employee_id": log.employee_id.id,
                    "employee_name": log.employee_id.name,
                    "amount": log.amount,
                    "base_amount": log.base_amount,
                    "quantity": log.quantity,
                    "rule_id": log.rule_id.id if log.rule_id else False,
                    "rule_name": log.rule_id.name if log.rule_id else "",
                    "trigger_type": log.trigger_type,
                    "trigger_datetime": log.trigger_datetime,
                    "currency": log.currency_id.name if log.currency_id else "",
                    "company_id": log.company_id.id if log.company_id else False,
                    "note": log.note,
                }
            )
        return {"success": True, "data": data, "count": len(logs)}

    @http.route(
        "/api/v1/commissions/logs/confirm",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def confirm_commission_logs(self, **payload):
        log_ids = payload.get("log_ids") or []
        if not log_ids:
            return {"success": False, "message": "缺少 log_ids 参数"}
        env = request.env
        logs = env["store.commission.log"].browse(log_ids).exists()
        if not logs:
            return {"success": False, "message": "提成日志不存在或无访问权限"}
        logs.action_confirm()
        return {"success": True, "message": "提成日志已确认"}

    @http.route(
        "/api/v1/performance/targets",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def performance_targets(self, **payload):
        employee_id = payload.get("employee_id")
        target_amount = payload.get("target_amount")
        period_start = payload.get("period_start")
        period_type = payload.get("period_type", "monthly")
        if not employee_id or target_amount is None or not period_start:
            return {"success": False, "message": "请提供 employee_id、target_amount、period_start"}

        env = request.env
        employee = env["hr.employee"].browse(employee_id)
        if not employee.exists():
            return {"success": False, "message": "员工不存在"}

        try:
            period_start_date = fields.Date.to_date(period_start)
        except Exception:  # noqa: BLE001
            return {"success": False, "message": "period_start 格式错误，需 YYYY-MM-DD"}

        target_model = env["store.performance.target"]
        existing = target_model.search(
            [
                ("employee_id", "=", employee.id),
                ("company_id", "=", employee.company_id.id or env.company.id),
                ("period_type", "=", period_type),
                ("period_start", "=", period_start_date),
            ],
            limit=1,
        )
        values = {
            "employee_id": employee.id,
            "company_id": employee.company_id.id or env.company.id,
            "period_type": period_type,
            "period_start": period_start_date,
            "target_amount": target_amount,
        }
        if payload.get("name"):
            values["name"] = payload["name"]
        if payload.get("note"):
            values["note"] = payload["note"]
        if existing:
            existing.write(values)
            target_id = existing.id
        else:
            target = target_model.create(values)
            target_id = target.id
        return {"success": True, "message": "业绩目标已更新", "target_id": target_id}
