from odoo import _, http
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager


class CrowdfundingPortal(CustomerPortal):
    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        partner = http.request.env.user.partner_id
        if "crowdfunding_project_count" in counters:
            project_count = (
                http.request.env["store.crowdfunding.project"]
                .sudo()
                .search_count(self._get_crowdfunding_domain())
            )
            values["crowdfunding_project_count"] = project_count
        if "crowdfunding_investment_count" in counters:
            values["crowdfunding_investment_count"] = partner.crowdfunding_investment_count
        values.update(
            {
                "crowdfunding_investment_total": partner.crowdfunding_investment_total,
                "crowdfunding_last_investment_date": partner.crowdfunding_last_investment_date,
            }
        )
        return values

    def _get_crowdfunding_domain(self):
        partner = http.request.env.user.partner_id
        companies = partner.company_ids | http.request.env.company
        domain = [
            "|",
            ("company_id", "in", companies.ids),
            ("brand_company_id", "=", http.request.env.company.id),
        ]
        return domain

    def _get_investment_domain(self):
        partner = http.request.env.user.partner_id
        return [
            ("partner_id", "=", partner.id),
        ]

    @http.route(
        "/my/crowdfunding",
        type="http",
        auth="user",
        website=True,
    )
    def portal_my_crowdfunding(self, page=1, sortby="date", **kw):
        values = self._prepare_portal_layout_values()
        project_obj = http.request.env["store.crowdfunding.project"].sudo()

        searchbar_sortings = {
            "date": {
                "label": _("按创建时间"),
                "order": "create_date desc",
            },
            "progress": {
                "label": _("按募集进度"),
                "order": "funding_progress desc",
            },
            "amount": {
                "label": _("按目标金额"),
                "order": "target_amount desc",
            },
        }
        order = searchbar_sortings.get(sortby, searchbar_sortings["date"])["order"]
        domain = self._get_crowdfunding_domain()
        project_count = project_obj.search_count(domain)
        pager = portal_pager(
            url="/my/crowdfunding",
            total=project_count,
            page=page,
            step=self._items_per_page,
            url_args={"sortby": sortby},
        )

        projects = project_obj.search(
            domain,
            limit=self._items_per_page,
            offset=pager["offset"],
            order=order,
        )
        investments = (
            http.request.env["store.crowdfunding.investment"]
            .sudo()
            .read_group(
                [
                    ("partner_id", "=", http.request.env.user.partner_id.id),
                    ("project_id", "in", projects.ids),
                ],
                ["project_id", "amount_confirmed:sum"],
                ["project_id"],
            )
        )
        investment_map = {
            data["project_id"][0]: data["amount_confirmed"]
            for data in investments
            if data["project_id"]
        }
        values.update(
            {
                "projects": projects,
                "pager": pager,
                "page_name": "crowdfunding",
                "default_url": "/my/crowdfunding",
                "searchbar_sortings": searchbar_sortings,
                "sortby": sortby,
                "investment_map": investment_map,
            }
        )
        return http.request.render(
            "store_crowdfunding.portal_my_crowdfunding", values
        )

    @http.route(
        "/my/crowdfunding/<int:project_id>",
        type="http",
        auth="user",
        website=True,
    )
    def portal_crowdfunding_project(self, project_id, **kw):
        project = (
            http.request.env["store.crowdfunding.project"]
            .sudo()
            .browse(project_id)
        )
        if not project.exists():
            return http.request.not_found()
        if not http.request.env.user.has_group("base.group_portal") and not http.request.env.user.has_group("base.group_user"):
            return http.request.redirect("/my")
        if project.company_id not in http.request.env.user.company_ids and project.brand_company_id != http.request.env.company:
            return http.request.redirect("/my/crowdfunding")

        investment_domain = self._get_investment_domain() + [("project_id", "=", project.id)]
        investments = (
            http.request.env["store.crowdfunding.investment"]
            .sudo()
            .search(investment_domain)
        )
        dividends = project.dividend_plan_ids.filtered(lambda d: d.state != "cancelled")
        values = {
            "project": project,
            "investments": investments,
            "dividends": dividends,
            "page_name": "crowdfunding",
        }
        return http.request.render(
            "store_crowdfunding.portal_crowdfunding_project", values
        )
