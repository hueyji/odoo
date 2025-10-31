from collections import defaultdict

from odoo import _, models


class AccountMove(models.Model):
    _inherit = "account.move"

    def action_post(self):
        res = super().action_post()
        self._process_commission_after_post()
        return res

    def _process_commission_after_post(self):
        for move in self:
            if move.move_type == "out_refund":
                move._refund_commission_logs()

    def _refund_commission_logs(self):
        self.ensure_one()
        sale_line_impact = defaultdict(lambda: {"qty": 0.0, "amount": 0.0})
        related_orders = self.env["sale.order"]
        for inv_line in self.invoice_line_ids:
            qty = abs(inv_line.quantity)
            amount = abs(inv_line.price_subtotal)
            sale_lines = inv_line.sale_line_ids
            if not sale_lines:
                continue
            share_qty = qty / len(sale_lines)
            share_amount = amount / len(sale_lines)
            for sale_line in sale_lines:
                info = sale_line_impact[sale_line]
                info["qty"] += share_qty
                info["amount"] += share_amount
                related_orders |= sale_line.order_id

        for sale_line, impact in sale_line_impact.items():
            order = sale_line.order_id
            logs = order.commission_log_ids.filtered(
                lambda log: log.sale_order_line_id == sale_line and log.state == "confirmed"
            )
            if not logs:
                continue
            quantity = sale_line.product_uom_qty or 0.0
            base_amount = abs(sale_line.price_total) or 0.0
            factor_qty = impact["qty"] / quantity if quantity else 0.0
            factor_amount = impact["amount"] / base_amount if base_amount else 0.0
            factor = max(factor_qty, factor_amount)
            factor = min(max(factor, 0.0), 1.0)
            for log in logs:
                log.action_refund(reason=_("订单退款 %s" % self.name), factor=factor)

        for order in related_orders:
            order_logs = order.commission_log_ids.filtered(lambda log: not log.sale_order_line_id and log.state == "confirmed")
            if not order_logs:
                continue
            original_amount = abs(order.amount_total) or 0.0
            refund_amount = abs(self.amount_total_signed) or abs(self.amount_total)
            factor = refund_amount / original_amount if original_amount else 0.0
            factor = min(max(factor, 0.0), 1.0)
            for log in order_logs:
                log.action_refund(reason=_("整单退款 %s" % self.name), factor=factor)
