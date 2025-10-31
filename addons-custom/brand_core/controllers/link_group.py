from odoo import _
from odoo.http import Controller, request, route


class LinkGroupAPI(Controller):
    def _json_response(self, data=None, status=200, message=None):
        payload = {"success": 200 <= status < 300}
        if message:
            payload["message"] = message
        if data is not None:
            payload["data"] = data
        body = request.make_json_response(payload, status=status)
        # make_json_response already returns Response
        return body

    def _serialize_group(self, group):
        return {
            "id": group.id,
            "code": group.code,
            "name": group.name,
            "brand_company_id": group.brand_company_id.id,
            "brand_company_name": group.brand_company_id.display_name
            if group.brand_company_id
            else None,
            "owner_id": group.owner_id.id,
            "owner_name": group.owner_id.display_name if group.owner_id else None,
            "share_inventory": group.share_inventory,
            "share_member": group.share_member,
            "share_finance": group.share_finance,
            "state": group.state,
            "member_company_ids": [
                {
                    "id": company.id,
                    "name": company.display_name,
                    "parent_id": company.parent_id.id,
                }
                for company in group.member_company_ids
            ],
            "application_count": group.application_count,
        }

    @route("/api/link-groups", type="json", auth="user", methods=["GET"])
    def list_link_groups(self, **kwargs):
        env = request.env
        company = env.company
        domain = []
        if not request.env.user.has_group("base.group_system"):
            domain = ["|", ("member_company_ids", "in", company.id), ("brand_company_id", "=", company.parent_id.id if company.parent_id else company.id)]
        groups = env["store.link.group"].search(domain)
        data = [self._serialize_group(group) for group in groups]
        return self._json_response(data=data)

    @route("/api/link-groups/apply", type="json", auth="user", methods=["POST"])
    def apply_link_group(self, **params):
        env = request.env
        values = params or {}
        group_id = values.get("group_id")
        proposed_group_name = values.get("proposed_group_name")
        requested_company_ids = values.get("requested_member_ids") or []
        description = values.get("description")
        share_inventory = values.get("share_inventory", True)
        share_member = values.get("share_member", True)
        share_finance = values.get("share_finance", False)

        if not group_id and not proposed_group_name:
            return self._json_response(
                status=400, message=_("请提供目标互通组或拟创建的互通组名称。")
            )

        Application = env["store.link.group.application"]
        create_vals = {
            "group_id": group_id,
            "proposed_group_name": proposed_group_name,
            "requested_member_ids": [(6, 0, requested_company_ids)]
            if requested_company_ids
            else False,
            "description": description,
            "share_inventory": share_inventory,
            "share_member": share_member,
            "share_finance": share_finance,
        }
        try:
            application = Application.create(create_vals)
        except Exception as error:
            return self._json_response(status=400, message=str(error))
        application.action_submit()
        data = {
            "id": application.id,
            "name": application.name,
            "state": application.state,
        }
        return self._json_response(
            data=data, status=201, message=_("互通申请提交成功，等待品牌审批。")
        )

    @route(
        "/api/link-groups/<int:group_id>",
        type="json",
        auth="user",
        methods=["PATCH"],
    )
    def update_link_group(self, group_id, **payload):
        user = request.env.user
        if not user.has_group("base.group_system"):
            return self._json_response(status=403, message=_("仅品牌管理员可执行此操作。"))

        group = request.env["store.link.group"].browse(group_id)
        if not group.exists():
            return self._json_response(status=404, message=_("未找到对应的互通组。"))

        updates = {}
        allowed_fields = {
            "share_inventory",
            "share_member",
            "share_finance",
            "state",
            "owner_id",
        }
        for field_name, value in payload.items():
            if field_name not in allowed_fields:
                continue
            updates[field_name] = value

        if not updates:
            return self._json_response(status=400, message=_("请求未包含可更新的字段。"))

        with request.env.cr.savepoint():
            if "state" in updates:
                state = updates.pop("state")
                if state == "active":
                    group.action_activate()
                elif state == "suspended":
                    group.action_suspend()
                elif state == "draft":
                    group.write({"state": "draft"})
                else:
                    return self._json_response(status=400, message=_("状态值不合法。"))
            if updates:
                group.write(updates)

        return self._json_response(
            data=self._serialize_group(group),
            message=_("互通组信息已更新。"),
        )
