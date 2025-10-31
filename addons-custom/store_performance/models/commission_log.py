from odoo import models


class StoreCommissionLog(models.Model):
    _inherit = "store.commission.log"

    def action_confirm(self):
        res = super().action_confirm()
        confirmed_logs = self.filtered(lambda log: log.state == "confirmed")
        if confirmed_logs:
            performance_env = self.env["store.performance.record"]
            for log in confirmed_logs:
                performance_env.apply_commission_log(log)
        return res
