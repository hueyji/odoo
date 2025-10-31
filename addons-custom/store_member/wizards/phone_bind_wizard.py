from odoo import _, fields, models
from odoo.exceptions import UserError


class StoreMemberPhoneBindWizard(models.TransientModel):
    _name = "store.member.phone.bind.wizard"
    _description = "会员手机号快速绑定"

    partner_id = fields.Many2one(
        "res.partner",
        string="会员",
        required=True,
    )
    phone = fields.Char(string="座机号码")
    mobile = fields.Char(string="手机号")

    def _check_duplicate_phone(self):
        self.ensure_one()
        partner = self.partner_id
        values = {val for val in [self.phone, self.mobile] if val}
        if not values:
            raise UserError(_("请录入手机号或座机号码。"))
        domain = [("id", "!=", partner.id)]
        domain += ["|", ("phone", "in", list(values)), ("mobile", "in", list(values))]
        duplicate = self.env["res.partner"].search(domain, limit=1)
        if duplicate:
            raise UserError(
                _("号码 %s 已绑定至会员：%s")
                % (", ".join(sorted(values)), duplicate.display_name)
            )

    def action_confirm(self):
        self.ensure_one()
        self._check_duplicate_phone()
        updates = {}
        if self.phone:
            updates["phone"] = self.phone
        if self.mobile:
            updates["mobile"] = self.mobile
        if (
            not self.partner_id.origin_store_id
            and self.env.user.company_id
            and not self.partner_id.is_company
        ):
            updates["origin_store_id"] = self.env.user.company_id.id
        if updates:
            self.partner_id.with_context(tracking_disable=False).write(updates)
        return {"type": "ir.actions.act_window_close"}
