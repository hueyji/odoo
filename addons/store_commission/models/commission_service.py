from collections import defaultdict

from odoo import api, fields, models


class StoreCommissionService(models.AbstractModel):
    _name = "store.commission.service"
    _description = "提成计算服务"

    @api.model
    def _prepare_sale_context(self, order):
        order_date = order.date_order or fields.Datetime.now()
        lines = []
        for line in order.order_line.filtered(lambda l: l.display_type is False):
            lines.append(
                {
                    "product": line.product_id,
                    "category": line.product_id.categ_id,
                    "qty": line.product_uom_qty,
                    "subtotal": line.price_subtotal,
                    "is_combo": bool(
                        getattr(line, "is_combo_component", False)
                        or getattr(line, "combo_id", False)
                    ),
                }
            )
        return {
            "order": order,
            "order_type": "sale",
            "employee": order.commission_employee_id,
            "company": order.company_id,
            "order_date": order_date,
            "amount_total": order.amount_total,
            "lines": lines,
            "currency": order.currency_id,
        }

    @api.model
    def _prepare_pos_context(self, order):
        order_date = order.date_order or fields.Datetime.now()
        lines = []
        for line in order.lines.filtered(lambda l: not getattr(l, "is_tip", False)):
            lines.append(
                {
                    "product": line.product_id,
                    "category": line.product_id.categ_id,
                    "qty": line.qty,
                    "subtotal": line.price_subtotal,
                    "is_combo": bool(
                        getattr(line, "is_combo_component", False)
                        or getattr(line, "combo_id", False)
                    ),
                }
            )
        return {
            "order": order,
            "order_type": "pos",
            "employee": order.commission_employee_id,
            "company": order.company_id,
            "order_date": order_date,
            "amount_total": order.amount_total,
            "lines": lines,
            "currency": order.currency_id,
        }

    @api.model
    def _compute_rules(self, order_ctx):
        company = order_ctx["company"]
        employee = order_ctx["employee"]
        domain = [
            ("active", "=", True),
            ("state", "=", "active"),
            "|",
            ("company_id", "=", False),
            ("company_id", "in", [company.id if company else False]),
        ]
        if employee:
            domain = domain + [
                "|",
                ("applicable_employee_ids", "=", False),
                ("applicable_employee_ids", "in", [employee.id]),
            ]
        rules = self.env["store.commission.rule"].search(domain, order="sequence, id")
        return rules.compute_commission(order_ctx)

    @api.model
    def compute_commission(self, order, order_type):
        if order_type == "sale":
            context = self._prepare_sale_context(order)
        elif order_type == "pos":
            context = self._prepare_pos_context(order)
        else:
            raise ValueError("Unsupported order type for commission calculation.")
        computed_rules = self._compute_rules(context)
        aggregated = defaultdict(lambda: {"amount": 0.0, "base_amount": 0.0, "quantity": 0.0})
        for item in computed_rules:
            rule = item["rule"]
            aggregated[rule]["amount"] += item["amount"]
            aggregated[rule]["base_amount"] += item["base_amount"]
            aggregated[rule]["quantity"] += item["quantity"]
        result = []
        for rule, values in aggregated.items():
            result.append(
                {
                    "rule": rule,
                    "amount": values["amount"],
                    "base_amount": values["base_amount"],
                    "quantity": values["quantity"],
                    "currency": context["currency"],
                    "order": context["order"],
                    "order_type": context["order_type"],
                    "employee": context["employee"],
                }
            )
        return result
