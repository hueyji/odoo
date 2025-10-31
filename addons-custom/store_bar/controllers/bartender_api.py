from odoo import _, fields, http
from odoo.exceptions import AccessError
from odoo.http import request


class StoreBarBartenderAPI(http.Controller):
    def _ensure_bartender(self):
        user = request.env.user
        if not (
            user.has_group("store_bar.group_store_bar_bartender")
            or user.has_group("store_bar.group_store_bar_manager")
        ):
            raise AccessError(_("您没有权限访问调酒师工作台接口。"))

    @http.route("/store_bar/api/bartender/tasks", type="json", auth="user", methods=["POST"])
    def bartender_tasks(self, company_id=None, states=None, limit=50):
        self._ensure_bartender()
        Task = request.env["store.bar.task"]
        domain = [("state", "in", states or ["pending", "in_progress"])]
        if company_id:
            domain.append(("company_id", "=", int(company_id)))
        tasks = Task.search(domain, limit=limit, order="state asc, sequence asc, create_date asc")
        return [self._prepare_task_payload(task) for task in tasks]

    @http.route("/store_bar/api/bartender/tasks/<int:task_id>/start", type="json", auth="user", methods=["POST"])
    def bartender_task_start(self, task_id):
        self._ensure_bartender()
        task = request.env["store.bar.task"].browse(task_id)
        task.action_start()
        return self._prepare_task_payload(task)

    @http.route("/store_bar/api/bartender/tasks/<int:task_id>/done", type="json", auth="user", methods=["POST"])
    def bartender_task_done(self, task_id):
        self._ensure_bartender()
        task = request.env["store.bar.task"].browse(task_id)
        task.action_done()
        return self._prepare_task_payload(task)

    @http.route("/store_bar/api/bar/orders/<int:order_id>/commission_preview", type="json", auth="user", methods=["POST"])
    def bartender_order_commission_preview(self, order_id):
        self._ensure_bartender()
        order = request.env["store.bar.order"].browse(order_id)
        return order.action_preview_commission()

    def _prepare_task_payload(self, task):
        return {
            "id": task.id,
            "name": task.name,
            "state": task.state,
            "order_id": task.order_id.id,
            "order_name": task.order_id.name,
            "table": task.table_id.display_name if task.table_id else None,
            "sequence": task.sequence,
            "note": task.note,
            "expected_commission": task.expected_commission_amount,
            "start_time": fields.Datetime.to_string(task.start_time) if task.start_time else False,
            "complete_time": fields.Datetime.to_string(task.complete_time) if task.complete_time else False,
            "product": task.order_line_id.product_id.display_name if task.order_line_id and task.order_line_id.product_id else None,
            "prep_state": task.order_line_id.prep_state if task.order_line_id else None,
        }
