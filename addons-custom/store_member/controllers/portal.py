from odoo import http
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.http import request


class StoreMemberPortal(CustomerPortal):
    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        partner = request.env.user.partner_id.sudo()
        if partner and "member_balance_log_count" in counters:
            log_env = request.env["store.member.balance.log"].sudo()
            values["member_balance_log_count"] = log_env.search_count(
                [
                    ("partner_id", "=", partner.id),
                    ("portal_visible", "=", True),
                ]
            )
        return values

    @http.route(["/my/member"], type="http", auth="user", website=True)
    def portal_member_dashboard(self, **kwargs):
        partner = request.env.user.partner_id.sudo()
        if not partner:
            return request.redirect("/my/home")
        values = self._prepare_portal_layout_values()
        member_values = self._prepare_member_portal_values(partner)
        values.update(member_values)
        values.update({
            "page_name": "member_profile",
            "success": kwargs.get("success"),
        })
        return request.render("store_member.portal_member_dashboard", values)

    def _prepare_member_portal_values(self, partner):
        log_env = request.env["store.member.balance.log"].sudo()
        recharge_logs = log_env.search(
            [
                ("partner_id", "=", partner.id),
                ("change_type", "=", "recharge"),
                ("portal_visible", "=", True),
            ],
            order="create_date desc",
            limit=10,
        )
        consume_logs = log_env.search(
            [
                ("partner_id", "=", partner.id),
                ("change_type", "in", ["consumption", "adjustment"]),
                ("portal_visible", "=", True),
            ],
            order="create_date desc",
            limit=10,
        )

        crowdfunding_projects = []
        if request.env.registry.get("store.crowdfunding.project"):
            crowdfunding_projects = (
                request.env["store.crowdfunding.project"].sudo().search(
                    [],
                    limit=3,
                    order="write_date desc",
                )
            )

        level_selection = dict(partner._fields["member_level"].selection)
        level_label = level_selection.get(partner.member_level, "标准会员")

        return {
            "member_partner": partner,
            "member_balance": partner.member_balance,
            "recharge_logs": recharge_logs,
            "consume_logs": consume_logs,
            "crowdfunding_projects": crowdfunding_projects,
            "member_level_label": level_label,
        }

    @http.route(
        ["/my/member/preferences"],
        type="http",
        auth="user",
        methods=["POST"],
        website=True,
    )
    def portal_member_update_preferences(self, **post):
        partner = request.env.user.partner_id.sudo()
        if not partner:
            return request.redirect("/my/home")
        privacy = bool(post.get("portal_privacy_opt_out"))
        enable_investment = bool(post.get("enable_investment"))
        to_write = {
            "portal_privacy_opt_out": privacy,
            "enable_investment": enable_investment,
        }
        partner.write(to_write)
        return request.redirect("/my/member?success=1")
