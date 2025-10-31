from odoo import fields, models


class StoreAccountTransaction(models.Model):
    _inherit = "store.account.transaction"

    transaction_type = fields.Selection(
        selection_add=[("commission", "提成发放")],
        ondelete={"commission": "set default"},
    )
