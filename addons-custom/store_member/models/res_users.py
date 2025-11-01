from odoo import api, models


class ResUsers(models.Model):
    _inherit = "res.users"

    @api.model
    def _signup_create_user(self, values):
        user = super()._signup_create_user(values)
        partner = user.partner_id
        if partner and partner.is_store_member and partner.member_origin_company_id:
            user.write(
                {
                    "company_id": partner.member_origin_company_id.id,
                    "company_ids": [(6, 0, [partner.member_origin_company_id.id])],
                }
            )
        return user

    def write(self, vals):
        res = super().write(vals)
        for user in self:
            partner = user.partner_id
            if partner and partner.is_store_member and partner.member_origin_company_id:
                allowed_company_id = partner.member_origin_company_id.id
                if user.company_id.id != allowed_company_id:
                    super(ResUsers, user).write({"company_id": allowed_company_id})
                if allowed_company_id not in user.company_ids.ids:
                    super(ResUsers, user).write({"company_ids": [(4, allowed_company_id)]})
        return res
