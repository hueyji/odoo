import json

from odoo import http
from odoo.exceptions import AccessError
from odoo.http import request


class CommissionAPI(http.Controller):
    def _ensure_user(self):
        if not request.env.user.has_group("store_commission.group_store_commission_user"):
            raise AccessError("当前账号无权访问提成数据。")

    @http.route("/api/commissions/calculate", type="json", auth="user", methods=["POST"], csrf=False)
    def commission_calculate(self, **payload):
        self._ensure_user()
        params = payload or request.jsonrequest or {}
        order_id = params.get("order_id")
        if not order_id:
            raise AccessError("缺少订单标识。")
        order = request.env["sale.order"].browse(int(order_id)).sudo()
        if not order:
            raise AccessError("订单不存在或无权访问。")
        preview = order.compute_commission_preview()
        return {
            "order_id": order.id,
            "currency_id": order.currency_id.id,
            "commission_total": sum(line["commission_amount"] for line in preview),
            "items": preview,
        }

    @http.route("/api/commissions/logs", type="http", auth="user", methods=["GET"], csrf=False)
    def commission_logs(self, **kwargs):
        self._ensure_user()
        domain = []
        employee_id = kwargs.get("employee_id")
        order_id = kwargs.get("order_id")
        state = kwargs.get("state")
        limit = int(kwargs.get("limit", 50))
        if employee_id:
            domain.append(("employee_id", "=", int(employee_id)))
        if order_id:
            domain.append(("sale_order_id", "=", int(order_id)))
        if state:
            domain.append(("state", "=", state))
        else:
            domain.append(("state", "=", "confirmed"))
        logs = request.env["store.commission.log"].sudo().search(domain, limit=limit, order="date desc")
        data = [
            {
                "id": log.id,
                "name": log.name,
                "date": log.date.isoformat() if log.date else None,
                "employee": {
                    "id": log.employee_id.id,
                    "name": log.employee_id.name,
                },
                "rule": {
                    "id": log.rule_id.id,
                    "name": log.rule_id.name,
                },
                "commission_amount": log.commission_amount,
                "base_amount": log.base_amount,
                "order_id": log.sale_order_id.id,
                "state": log.state,
                "is_refund": log.is_refund,
            }
            for log in logs
        ]
        headers = [("Content-Type", "application/json")]
        return request.make_response(json.dumps({"items": data, "count": len(data)}), headers=headers)
