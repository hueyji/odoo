# -*- coding: utf-8 -*-
from odoo import _, http
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
from odoo.exceptions import ValidationError
from odoo.http import request


class StoreCrowdfundingPortal(CustomerPortal):
    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if "crowdfunding_project_count" in counters:
            domain = [
                ("portal_published", "=", True),
                ("state", "in", ("fundraising", "in_progress", "closed")),
            ]
            values["crowdfunding_project_count"] = (
                request.env["store.crowdfunding.project"].sudo().search_count(domain)
            )
        if "crowdfunding_invest_count" in counters:
            values["crowdfunding_invest_count"] = request.env[
                "store.crowdfunding.investment"
            ].sudo().search_count(
                [
                    ("partner_id", "=", request.env.user.partner_id.id),
                    ("state", "=", "confirmed"),
                ]
            )
        partner = request.env.user.partner_id
        if partner and partner.enable_investment:
            summary = partner.get_crowdfunding_summary()
            values.update(
                {
                    "crowdfunding_amount_total": summary.get("stored_amount", 0.0),
                    "crowdfunding_dividend_total": summary.get("dividend_amount", 0.0),
                    "crowdfunding_has_inconsistency": partner.check_crowdfunding_consistency(),
                }
            )
        return values

    @http.route(["/my/crowdfunding", "/my/crowdfunding/page/<int:page>"], type="http", auth="user", website=True)
    def portal_crowdfunding_projects(self, page=1, **kw):
        partner = request.env.user.partner_id
        if not partner.enable_investment:
            return request.render(
                "store_crowdfunding.portal_crowdfunding_no_permission",
                {"page_name": "crowdfunding"},
            )
        Project = request.env["store.crowdfunding.project"].sudo()
        domain = [
            ("portal_published", "=", True),
            ("state", "in", ("fundraising", "in_progress", "closed")),
        ]
        total = Project.search_count(domain)
        pager = portal_pager(
            url="/my/crowdfunding",
            total=total,
            page=page,
            step=10,
        )
        projects = Project.search(domain, limit=pager["step"], offset=pager["offset"])
        summary = partner.get_crowdfunding_summary()
        return request.render(
            "store_crowdfunding.portal_crowdfunding_projects",
            {
                "projects": projects,
                "page_name": "crowdfunding",
                "pager": pager,
                "summary": summary,
                "has_inconsistency": partner.check_crowdfunding_consistency(),
                "currency": partner.crowdfunding_currency_id or request.env.company.currency_id,
                "partner": partner,
            },
        )

    @http.route("/my/crowdfunding/<int:project_id>", type="http", auth="user", website=True)
    def portal_crowdfunding_project_detail(self, project_id, **kw):
        partner = request.env.user.partner_id
        Project = request.env["store.crowdfunding.project"].sudo()
        project = Project.browse(project_id)
        if not partner.enable_investment:
            return request.render(
                "store_crowdfunding.portal_crowdfunding_no_permission",
                {"page_name": "crowdfunding"},
            )
        if (
            project.state not in ("fundraising", "in_progress", "closed")
            or not project.portal_published
        ):
            return request.redirect("/my/crowdfunding")
        summary = partner.get_crowdfunding_summary()
        return request.render(
            "store_crowdfunding.portal_crowdfunding_project_detail",
            {
                "project": project,
                "partner": partner,
                "summary": summary,
                "has_inconsistency": partner.check_crowdfunding_consistency(),
                "currency": partner.crowdfunding_currency_id or request.env.company.currency_id,
            },
        )

    @http.route("/my/crowdfunding/<int:project_id>/invest", type="http", auth="user", methods=["POST"], csrf=False)
    def portal_crowdfunding_invest(self, project_id, **post):
        partner = request.env.user.partner_id
        if not partner.enable_investment:
            return request.redirect("/my/crowdfunding")
        project = request.env["store.crowdfunding.project"].sudo().browse(project_id)
        if project.state not in ("fundraising", "in_progress"):
            return request.redirect("/my/crowdfunding/%s" % project_id)
        try:
            amount = float(post.get("amount", 0))
        except ValueError as error:
            raise ValidationError(_("请输入有效的投资金额。")) from error
        if amount <= 0:
            raise ValidationError(_("投资金额必须大于 0。"))
        investment = request.env["store.crowdfunding.investment"].sudo().create(
            {
                "project_id": project.id,
                "partner_id": partner.id,
                "amount": amount,
                "note": post.get("note"),
            }
        )
        investment.action_confirm()
        return request.redirect("/my/crowdfunding")
