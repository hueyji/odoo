from odoo import models


class StoreCommissionLog(models.Model):
    _inherit = "store.commission.log"

    def _performance_snapshot(self):
        self.ensure_one()
        return {
            "state": self.state,
            "amount": self.amount,
            "base_amount": self.base_amount,
            "order_count": 1,
        }

    def _update_performance_records(self, previous_values=None):
        PerformanceRecord = self.env["store.performance.record"].sudo()
        for index, log in enumerate(self):
            if not log.employee_id or not log.company_id:
                continue
            prev = {}
            if previous_values and index < len(previous_values):
                prev = previous_values[index]
            trigger_datetime = log.trigger_datetime or log.create_date
            for period_type in ["daily", "monthly"]:
                record = PerformanceRecord._get_or_create_record(
                    log.employee_id, log.company_id, trigger_datetime, period_type=period_type
                )
                record._apply_log_delta(log, previous_values=prev)

    @staticmethod
    def _collect_snapshots(recordset):
        return [log._performance_snapshot() for log in recordset]

    def write(self, vals):
        previous_values = self._collect_snapshots(self)
        res = super().write(vals)
        self._update_performance_records(previous_values=previous_values)
        return res

    def create(self, vals_list):
        logs = super().create(vals_list)
        logs._update_performance_records()
        return logs
