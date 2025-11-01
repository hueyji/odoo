# -*- coding: utf-8 -*-
import json

from odoo import _, http
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request


class StoreCrowdfundingApi(http.Controller):
    def _check_manager(self):
        user = request.env.user
        if not (
            user.has_group("store_crowdfunding.group_store_crowdfunding_manager")
            or user.has_group("brand_core.group_brand_platform_admin")
        ):
            raise AccessError(_("需要众筹经理或品牌管理员权限。"))

    @http.route("/api/crowdfunding/projects", type="json", auth="user", methods=["POST"])
    def create_project(self, **payload):
        self._check_manager()
        data = payload or request.jsonrequest or {}
        required_fields = ["name", "goal_amount"]
        missing = [field for field in required_fields if not data.get(field)]
        if missing:
            raise ValidationError(_("缺少必要字段：%s") % ",".join(missing))

        project_vals = {
            "name": data["name"],
            "goal_amount": data["goal_amount"],
            "minimum_amount": data.get("minimum_amount"),
            "summary": data.get("summary"),
            "investor_highlight": data.get("investor_highlight"),
            "dividend_rule": data.get("dividend_rule"),
            "location": data.get("location"),
            "fundraising_start_date": data.get("fundraising_start_date"),
            "fundraising_deadline": data.get("fundraising_deadline"),
            "portal_published": data.get("portal_published", True),
            "company_id": data.get("company_id") or request.env.company.id,
            "contract_watermark_status": data.get("contract_watermark_status", "pending"),
        }
        project = request.env["store.crowdfunding.project"].sudo().create(project_vals)

        attachments = data.get("attachments") or []
        for attach in attachments:
            if not attach.get("name") or not attach.get("data"):
                continue
            request.env["ir.attachment"].sudo().create(
                {
                    "name": attach["name"],
                    "datas": attach["data"],
                    "res_model": project._name,
                    "res_id": project.id,
                    "mimetype": attach.get("mimetype", "application/pdf"),
                }
            )
        return {
            "id": project.id,
            "name": project.name,
            "code": project.code,
            "state": project.state,
        }

    @http.route("/api/crowdfunding/projects", type="http", auth="user", methods=["GET"], csrf=False)
    def list_projects(self):
        domain = []
        if not (request.env.user.has_group("store_crowdfunding.group_store_crowdfunding_manager") or request.env.user.has_group("brand_core.group_brand_platform_admin")):
            domain.extend(
                [
                    ("portal_published", "=", True),
                    ("state", "in", ("fundraising", "in_progress", "closed")),
                ]
            )
        projects = request.env["store.crowdfunding.project"].sudo().search(domain, limit=100)
        data = [
            {
                "id": project.id,
                "name": project.name,
                "code": project.code,
                "state": project.state,
                "goal_amount": project.goal_amount,
                "total_invest_amount": project.total_invest_amount,
                "progress_rate": project.progress_rate,
                "fundraising_deadline": project.fundraising_deadline,
            }
            for project in projects
        ]
        body = json.dumps({"data": data}, ensure_ascii=False)
        return request.make_response(
            body,
            headers={"Content-Type": "application/json; charset=utf-8"},
        )

    @http.route("/api/crowdfunding/investments", type="json", auth="user", methods=["POST"])
    def create_investment(self, **payload):
        data = payload or request.jsonrequest or {}
        if not data.get("project_id") or not data.get("partner_id") or not data.get("amount"):
            raise ValidationError(_("请提供项目、投资人以及金额。"))
        investment_vals = {
            "project_id": data["project_id"],
            "partner_id": data["partner_id"],
            "amount": data["amount"],
            "payment_channel_id": data.get("payment_channel_id"),
            "note": data.get("note"),
        }
        investment = request.env["store.crowdfunding.investment"].sudo().create(investment_vals)
        if data.get("confirm", True):
            investment.action_confirm()
        return {
            "id": investment.id,
            "name": investment.name,
            "state": investment.state,
            "transaction_id": investment.account_transaction_id.id,
        }

    @http.route("/api/crowdfunding/dividends/run", type="json", auth="user", methods=["POST"])
    def execute_dividends(self, **payload):
        self._check_manager()
        data = payload or request.jsonrequest or {}
        dividend_ids = data.get("dividend_ids") or []
        if not dividend_ids:
            raise ValidationError(_("请提供需要执行的分红计划 ID 列表。"))
        dividends = request.env["store.crowdfunding.dividend"].sudo().browse(dividend_ids)
        dividends.action_execute()
        return {"executed": dividends.ids}
