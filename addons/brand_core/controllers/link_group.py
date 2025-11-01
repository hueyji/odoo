# -*- coding: utf-8 -*-
from typing import Dict, List

from odoo import _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request, route

from .base import BrandCoreRestController


class BrandCoreLinkGroupController(BrandCoreRestController):
    """REST API for store.link.group operations."""

    def _serialize_group(self, group) -> Dict:
        return {
            "id": group.id,
            "name": group.name,
            "state": group.state,
            "description": group.description,
            "share_scope": {
                "inventory": group.share_inventory,
                "member": group.share_member,
                "finance": group.share_finance,
            },
            "company": {
                "id": group.company_id.id,
                "name": group.company_id.display_name,
            },
            "owner": {
                "id": group.owner_id.id if group.owner_id else False,
                "name": group.owner_id.display_name if group.owner_id else False,
            },
            "member_companies": [
                {"id": company.id, "name": company.display_name}
                for company in group.member_company_ids.sorted(lambda c: c.name or "")
            ],
            "request_count": group.request_count,
        }

    def _serialize_application(self, application) -> Dict:
        return {
            "id": application.id,
            "state": application.state,
            "request_company": {
                "id": application.request_company_id.id,
                "name": application.request_company_id.display_name,
            },
            "requested_member_ids": [
                {"id": company.id, "name": company.display_name}
                for company in application.requested_member_ids.sorted(lambda c: c.name or "")
            ],
            "share_scope": {
                "inventory": application.share_inventory,
                "member": application.share_member,
                "finance": application.share_finance,
            },
            "approver": {
                "id": application.approver_id.id if application.approver_id else False,
                "name": application.approver_id.display_name if application.approver_id else False,
            },
            "approved_date": application.approved_date,
            "reject_reason": application.reject_reason,
        }

    @route("/api/v1/link-groups", type="http", auth="user", methods=["GET"], csrf=False)
    def list_link_groups(self, **params):
        Group = request.env["store.link.group"]
        domain: List = []
        state = params.get("state")
        if state:
            domain.append(("state", "=", state))
        groups = Group.search(domain, order="name asc")
        data = [self._serialize_group(group) for group in groups]
        return self._json_success(data={"items": data, "total": len(data)})

    @route("/api/v1/link-groups", type="http", auth="user", methods=["POST"], csrf=False)
    def create_link_group(self):
        try:
            payload = self._parse_json(required_fields=["name", "member_company_ids"])
        except Exception as exc:  # BadRequest handled upstream
            return self._json_error(str(exc), status=400)

        member_company_ids = payload.get("member_company_ids") or []
        if not isinstance(member_company_ids, list):
            return self._json_error("字段 member_company_ids 必须是整数列表。", status=400)
        try:
            member_company_ids = [int(cid) for cid in member_company_ids]
        except (TypeError, ValueError):
            return self._json_error("member_company_ids 仅支持整数 ID。", status=400)

        company_id = payload.get("company_id") or request.env.company.id
        Company = request.env["res.company"]
        company = Company.browse(company_id)
        if not company.exists():
            return self._json_error("品牌公司不存在。", code="brand_not_found", status=404)

        owner_id = payload.get("owner_id") or request.env.user.id

        vals = {
            "name": payload["name"],
            "company_id": company.id,
            "owner_id": owner_id,
            "share_inventory": bool(payload.get("share_inventory")),
            "share_member": bool(payload.get("share_member")),
            "share_finance": bool(payload.get("share_finance")),
            "description": payload.get("description", ""),
            "member_company_ids": [(6, 0, list({cid for cid in member_company_ids}))],
        }

        Group = request.env["store.link.group"]
        try:
            group = Group.create(vals)
            group.action_submit()
        except (ValidationError, UserError) as exc:
            return self._json_error(str(exc), status=400)
        except AccessError:
            return self._json_error("没有权限创建互通组。", code="no_permission", status=403)

        data = self._serialize_group(group)
        latest_application = group.application_ids[:1]
        if latest_application:
            data["latest_application"] = self._serialize_application(latest_application)

        return self._json_success(data=data, message="互通申请已提交", status=201)

    @route(
        "/api/v1/link-groups/<int:group_id>/approve",
        type="http",
        auth="user",
        methods=["POST"],
        csrf=False,
    )
    def approve_link_group(self, group_id):
        if not request.env.user.has_group("brand_core.group_brand_platform_admin"):
            return self._json_error("仅品牌平台管理员可以执行审批。", code="no_permission", status=403)

        group = request.env["store.link.group"].browse(group_id)
        if not group.exists():
            return self._json_error("互通组不存在。", code="not_found", status=404)

        try:
            group.action_approve()
        except UserError as exc:
            return self._json_error(str(exc), status=400)

        return self._json_success(data=self._serialize_group(group), message="审批已通过")

    @route(
        "/api/v1/link-groups/<int:group_id>/reject",
        type="http",
        auth="user",
        methods=["POST"],
        csrf=False,
    )
    def reject_link_group(self, group_id):
        if not request.env.user.has_group("brand_core.group_brand_platform_admin"):
            return self._json_error("仅品牌平台管理员可以驳回申请。", code="no_permission", status=403)

        group = request.env["store.link.group"].browse(group_id)
        if not group.exists():
            return self._json_error("互通组不存在。", code="not_found", status=404)

        payload = {}
        try:
            payload = self._parse_json()
        except Exception:
            # 忽略无 JSON 的情况，保持 reason 为空
            payload = {}

        reason = payload.get("reason")
        try:
            group.action_reject(reason)
        except UserError as exc:
            return self._json_error(str(exc), status=400)

        return self._json_success(data=self._serialize_group(group), message="申请已驳回")
