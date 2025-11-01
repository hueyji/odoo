import json
import logging

from odoo import _, fields, http
from odoo.exceptions import AccessError, MissingError, ValidationError
from odoo.http import request


_logger = logging.getLogger(__name__)


class StoreMemberApi(http.Controller):
    """Team E 会员相关 REST 接口"""

    def _ensure_member_user(self):
        user = request.env.user
        if not (
            user.has_group("store_member.group_store_member_user")
            or user.has_group("store_member.group_store_member_admin")
        ):
            raise AccessError(_("当前账号未开通会员管理权限。"))

    def _json_response(self, data=None, meta=None, warnings=None, status=200):
        payload = {
            "data": data or {},
            "meta": meta
            or {
                "code": "TEAME_2000",
                "timestamp": fields.Datetime.now().isoformat(),
            },
            "warning": warnings,
        }
        response = request.make_response(
            json.dumps(payload, ensure_ascii=False),
            headers={"Content-Type": "application/json"},
        )
        response.status_code = status
        return response

    def _json_error(self, code, message, status=400, details=None):
        payload = {
            "error": {
                "code": code,
                "http_status": status,
                "message_cn": message,
                "details": details or [],
            }
        }
        response = request.make_response(
            json.dumps(payload, ensure_ascii=False),
            headers={"Content-Type": "application/json"},
        )
        response.status_code = status
        return response

    def _parse_json_body(self):
        json_payload = getattr(request, "jsonrequest", None)
        if json_payload is not None:
            payload = json_payload
            if isinstance(payload, dict) and payload.get("jsonrpc") and payload.get("params"):
                return payload.get("params", {})
            return payload
        try:
            content = request.httprequest.data.decode("utf-8")
            if not content:
                return {}
            payload = json.loads(content)
            if isinstance(payload, dict) and payload.get("jsonrpc") and payload.get("params"):
                return payload.get("params", {})
            return payload
        except Exception as exc:  # pragma: no cover
            _logger.debug("Invalid JSON payload: %s", exc)
            raise ValidationError(_("请求体需为合法的 JSON 格式。"))

    def _serialize_member(self, partner):
        level = partner.member_level_id
        wallets = [
            {
                "wallet_id": wallet.id,
                "balance_type": wallet.balance_type,
                "balance": wallet.balance,
                "sharing_scope": wallet.sharing_scope,
                "allow_negative": wallet.allow_negative,
                "last_transaction_date": fields.Datetime.to_string(wallet.last_transaction_date)
                if wallet.last_transaction_date
                else None,
            }
            for wallet in partner.member_wallet_ids
        ]
        return {
            "id": partner.id,
            "member_code": partner.member_code,
            "name": partner.name,
            "phone": partner.phone or partner.mobile,
            "email": partner.email,
            "member_level": level.code if level else None,
            "member_level_label": level.name if level else None,
            "origin_company_id": partner.member_origin_company_id.id if partner.member_origin_company_id else None,
            "origin_company_name": partner.member_origin_company_id.name
            if partner.member_origin_company_id
            else None,
            "member_cash_balance": partner.member_cash_balance,
            "member_crowdfunding_balance": partner.member_crowdfunding_balance,
            "preferences": partner.member_preference_ids.mapped("name"),
            "investor_profile": partner.investor_profile,
            "enable_crowdfunding": partner.enable_crowdfunding,
            "member_sensitive_mask": partner.member_sensitive_mask,
            "wallets": wallets,
        }

    def _find_member_by_identifier(self, member_id=None, phone=None):
        env = request.env["res.partner"]
        domain = [("is_store_member", "=", True)]
        if member_id:
            domain.append(("id", "=", member_id))
        elif phone:
            domain.append("|")
            domain.append(("phone", "=", phone))
            domain.append(("mobile", "=", phone))
        else:
            raise ValidationError(_("请提供 member_id 或 phone 参数。"))
        partner = env.search(domain, limit=1)
        if not partner:
            raise MissingError(_("未找到对应的会员信息。"))
        return partner

    @http.route("/api/v1/members", type="http", auth="user", methods=["GET"], csrf=False)
    def list_members(self, **kwargs):
        try:
            self._ensure_member_user()
            env = request.env["res.partner"]
            domain = [("is_store_member", "=", True)]
            company_id = kwargs.get("company_id")
            if company_id:
                domain.append(("member_origin_company_id", "=", int(company_id)))
            level = kwargs.get("level")
            if level:
                domain.append(("member_level_id.code", "=", level))
            keyword = kwargs.get("keyword")
            if keyword:
                domain += [
                    "|",
                    "|",
                    ("name", "ilike", keyword),
                    ("phone", "ilike", keyword),
                    ("member_code", "ilike", keyword),
                ]
            limit = int(kwargs.get("limit", 20))
            offset = int(kwargs.get("offset", 0))
            partners = env.search(domain, limit=limit, offset=offset, order="write_date desc")
            data = {
                "members": [self._serialize_member(partner) for partner in partners],
                "offset": offset,
                "limit": limit,
                "count": env.search_count(domain),
            }
            return self._json_response(data)
        except AccessError as exc:
            return self._json_error("TEAME_2403", str(exc), status=403)
        except ValidationError as exc:
            return self._json_error("TEAME_2001", str(exc), status=400)
        except Exception:
            _logger.exception("Member API - list_members error")
            return self._json_error("TEAME_2499", _("系统繁忙，请稍后重试。"), status=500)

    @http.route("/api/v1/members/bind", type="http", auth="user", methods=["POST"], csrf=False)
    def bind_member(self, **kw):
        try:
            self._ensure_member_user()
            payload = self._parse_json_body()
            phone = payload.get("phone")
            if not phone:
                raise ValidationError(_("手机号不能为空。"))
            company_id = payload.get("company_id") or request.env.user.company_id.id
            if company_id:
                company_id = int(company_id)
            partner_model = request.env["res.partner"]
            partner_sudo = partner_model.sudo()
            partner = partner_sudo.search(
                [
                    "|",
                    ("phone", "=", phone),
                    ("mobile", "=", phone),
                ],
                limit=1,
            )
            vals = {}
            if payload.get("name"):
                vals["name"] = payload["name"]
            if payload.get("email"):
                vals["email"] = payload["email"]
            if company_id:
                vals.setdefault("company_id", company_id)
            if partner:
                update_vals = vals.copy()
                if not partner.is_store_member:
                    update_vals["is_store_member"] = True
                if not partner.member_origin_company_id and company_id:
                    update_vals["member_origin_company_id"] = company_id
                if company_id and not partner.company_id:
                    update_vals["company_id"] = company_id
                if update_vals:
                    partner.write(update_vals)
            else:
                vals.update(
                    {
                        "phone": phone,
                        "mobile": phone,
                        "is_store_member": True,
                        "member_origin_company_id": company_id,
                    }
                )
                if company_id:
                    vals.setdefault("company_id", company_id)
                partner = partner_sudo.create(vals)
            partner_user = partner.with_env(request.env)
            data = {"member": self._serialize_member(partner_user)}
            meta = {"code": "TEAME_2000", "timestamp": fields.Datetime.now().isoformat()}
            return self._json_response(data, meta=meta)
        except AccessError as exc:
            return self._json_error("TEAME_2403", str(exc), status=403)
        except ValidationError as exc:
            return self._json_error("TEAME_2001", str(exc), status=400)
        except Exception:
            _logger.exception("Member API - bind_member error")
            return self._json_error("TEAME_2499", _("系统繁忙，请稍后重试。"), status=500)

    @http.route("/api/v1/members/recharge", type="http", auth="user", methods=["POST"], csrf=False)
    def recharge_member(self, **kw):
        try:
            self._ensure_member_user()
            payload = self._parse_json_body()
            member_id = payload.get("member_id")
            phone = payload.get("phone")
            amount = payload.get("amount")
            if not amount:
                raise ValidationError(_("请输入储值金额。"))
            try:
                amount = float(amount)
            except Exception:
                raise ValidationError(_("储值金额格式不正确。"))
            partner = self._find_member_by_identifier(member_id=member_id, phone=phone)
            note = payload.get("note") or _("门店充值")
            reference = payload.get("reference")
            trace_payload = json.dumps(
                {
                    "channel_id": payload.get("channel_id"),
                    "operator_id": request.env.user.id,
                    "link_group_id": payload.get("link_group_id"),
                },
                ensure_ascii=False,
            )
            partner.action_member_recharge(
                amount,
                balance_type=payload.get("balance_type", "cash"),
                note=note,
                reference=reference,
                trace_payload=trace_payload,
            )
            partner.flush_model()  # 确保余额字段更新
            data = {"member": self._serialize_member(partner)}
            meta = {"code": "TEAME_2000", "timestamp": fields.Datetime.now().isoformat()}
            return self._json_response(data, meta=meta)
        except (ValidationError, MissingError) as exc:
            return self._json_error("TEAME_2002", str(exc), status=400)
        except AccessError as exc:
            return self._json_error("TEAME_2403", str(exc), status=403)
        except Exception:
            _logger.exception("Member API - recharge_member error")
            return self._json_error("TEAME_2499", _("系统繁忙，请稍后重试。"), status=500)

    @http.route("/api/v1/members/balance", type="http", auth="user", methods=["GET"], csrf=False)
    def member_balance(self, **kwargs):
        try:
            self._ensure_member_user()
            member_id = kwargs.get("member_id")
            phone = kwargs.get("phone")
            partner = self._find_member_by_identifier(member_id=member_id, phone=phone)
            data = {"member": self._serialize_member(partner)}
            return self._json_response(data)
        except (ValidationError, MissingError) as exc:
            return self._json_error("TEAME_2002", str(exc), status=400)
        except AccessError as exc:
            return self._json_error("TEAME_2403", str(exc), status=403)
        except Exception:
            _logger.exception("Member API - member_balance error")
            return self._json_error("TEAME_2499", _("系统繁忙，请稍后重试。"), status=500)
