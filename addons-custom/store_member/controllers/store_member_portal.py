from odoo import _, http
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.http import request


class StoreMemberPortal(CustomerPortal):
    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        partner = request.env.user.partner_id
        if partner and partner.is_store_member:
            values.update(
                {
                    "member_level_name": partner.member_level_id.name or _("普通会员"),
                    "member_cash_balance": partner.member_cash_balance,
                    "member_crowdfunding_balance": partner.member_crowdfunding_balance,
                }
            )
        return values

    @http.route(
        ["/my/membership"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_my_membership(self, **kwargs):
        partner = request.env.user.partner_id
        if not partner or not partner.is_store_member:
            return request.redirect("/my")
        masked_taboo = partner.member_taboo
        if partner.member_sensitive_mask and masked_taboo:
            masked_taboo = _("敏感信息已遮蔽，请联系品牌方审批查看。")
        wallet_type_labels = dict(request.env["store.member.wallet"]._fields["balance_type"].selection)
        sharing_scope_labels = dict(request.env["store.member.wallet"]._fields["sharing_scope"].selection)
        wallet_values = []
        for wallet in partner.member_wallet_ids:
            wallet_values.append(
                {
                    "id": wallet.id,
                    "balance_type": wallet.balance_type,
                    "balance_type_label": wallet_type_labels.get(wallet.balance_type, wallet.balance_type),
                    "balance": wallet.balance,
                    "currency": wallet.currency_id,
                    "sharing_scope_label": sharing_scope_labels.get(wallet.sharing_scope, wallet.sharing_scope),
                    "sharing_scope": wallet.sharing_scope,
                }
            )
        values = {
            "page_name": "membership",
            "partner": partner,
            "member_wallets": wallet_values,
            "member_taboo_masked": masked_taboo,
        }
        return request.render("store_member.portal_my_membership", values)
