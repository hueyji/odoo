import json
import logging

from odoo import _, fields, http
from odoo.exceptions import AccessError, MissingError, ValidationError
from odoo.http import request


_logger = logging.getLogger(__name__)


class StoreBarApi(http.Controller):
    """REST 接口：桌台状态、点单创建与结账"""

    def _ensure_bar_user(self):
        if not request.env.user.has_group("store_bar.group_bar_user"):
            raise AccessError(_("当前账号未授权访问吧台接口，请联系管理员开通权限。"))

    def _json_response(self, data=None, meta=None, warnings=None, status=200):
        payload = {
            "data": data or {},
            "meta": meta
            or {
                "code": "OK",
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

    def _serialize_table(self, table):
        return {
            "id": table.id,
            "name": table.name,
            "state": table.state,
            "state_label": dict(table._fields["state"].selection).get(table.state),
            "capacity": table.capacity,
            "current_order": self._serialize_order(table.current_order_id)
            if table.current_order_id
            else None,
            "reservation": {
                "partner_id": table.reservation_partner_id.id if table.reservation_partner_id else None,
                "partner_name": table.reservation_partner_id.display_name
                if table.reservation_partner_id
                else None,
                "phone": table.reservation_phone,
                "datetime": table.reservation_datetime,
            }
            if table.reservation_partner_id or table.reservation_phone
            else None,
        }

    def _serialize_order(self, order):
        if not order:
            return None
        return {
            "id": order.id,
            "name": order.name,
            "state": order.state,
            "state_label": dict(order._fields["state"].selection).get(order.state),
            "table_id": order.table_id.id,
            "employee_id": order.employee_id.id if order.employee_id else None,
            "member_id": order.member_id.id if order.member_id else None,
            "amount_total": order.amount_total,
            "locked_at": order.locked_at,
            "billed_at": order.billed_at,
            "lines": [
                {
                    "id": line.id,
                    "product_id": line.product_id.id,
                    "product_name": line.product_id.display_name,
                    "combo_id": line.combo_id.id if line.combo_id else None,
                    "is_combo_component": line.is_combo_component,
                    "batch_id": line.batch_id.id if line.batch_id else None,
                    "quantity": line.quantity,
                    "price_unit": line.price_unit,
                    "price_subtotal": line.price_subtotal,
                }
                for line in order.order_line_ids
            ],
        }

    def _parse_json_body(self):
        if request.jsonrequest is not None:
            payload = request.jsonrequest
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
        except Exception:  # pragma: no cover - 解码失败走统一异常
            raise ValidationError(_("请求体需为合法的 JSON 格式。"))

    @http.route("/api/v1/bar/tables", type="http", auth="user", methods=["GET"], csrf=False)
    def list_tables(self, **kwargs):
        try:
            self._ensure_bar_user()
            env = request.env["store.bar.table"]
            domain = []
            state = kwargs.get("state")
            if state:
                domain.append(("state", "=", state))
            tables = env.search(domain)
            data = {"tables": [self._serialize_table(t) for t in tables]}
            return self._json_response(data)
        except AccessError as exc:
            return self._json_error("TEAMF_2598", str(exc), status=403)
        except ValidationError as exc:
            return self._json_error("TEAMF_2501", str(exc), status=400)
        except Exception as exc:  # pragma: no cover - 兜底
            _logger.exception("Bar API - list_tables error")
            return self._json_error("TEAMF_2599", _("系统繁忙，请稍后重试。"), status=500)

    @http.route("/api/v1/bar/orders", type="json", auth="user", methods=["POST"], csrf=False)
    def create_order(self, **kw):
        try:
            self._ensure_bar_user()
            payload = self._parse_json_body()
            order_vals = self._prepare_order_values(payload)
            order = request.env["store.bar.order"].create(order_vals)
            if payload.get("auto_lock", True):
                order.action_lock()
            data = {"order": self._serialize_order(order)}
            meta = {"code": "TEAMF_0000", "timestamp": fields.Datetime.now().isoformat()}
            return self._json_response(data, meta=meta)
        except (ValidationError, MissingError) as exc:
            return self._json_error("TEAMF_2502", str(exc), status=400)
        except AccessError as exc:
            return self._json_error("TEAMF_2598", str(exc), status=403)
        except Exception:
            _logger.exception("Bar API - create_order error")
            return self._json_error("TEAMF_2599", _("系统繁忙，请稍后重试。"), status=500)

    @http.route(
        "/api/v1/bar/orders/<int:order_id>/close",
        type="json",
        auth="user",
        methods=["PATCH"],
        csrf=False,
    )
    def close_order(self, order_id, **kw):
        try:
            self._ensure_bar_user()
            payload = self._parse_json_body() if request.httprequest.method != "GET" else {}
            mode = payload.get("mode", "final")
            order = request.env["store.bar.order"].browse(order_id)
            if not order.exists():
                raise MissingError(_("未找到对应的吧台订单。"))
            if mode == "billing":
                order.action_request_billing()
            else:
                order.action_set_billed()
            data = {"order": self._serialize_order(order)}
            meta = {"code": "TEAMF_0001", "timestamp": fields.Datetime.now().isoformat()}
            return self._json_response(data, meta=meta)
        except (ValidationError, MissingError) as exc:
            return self._json_error("TEAMF_2503", str(exc), status=400)
        except AccessError as exc:
            return self._json_error("TEAMF_2598", str(exc), status=403)
        except Exception:
            _logger.exception("Bar API - close_order error")
            return self._json_error("TEAMF_2599", _("系统繁忙，请稍后重试。"), status=500)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _prepare_order_values(self, payload):
        table_id = payload.get("table_id")
        employee_id = payload.get("employee_id")
        if not table_id or not employee_id:
            raise ValidationError(_("参数缺失：table_id 与 employee_id 为必填项。"))

        lines = payload.get("lines", [])
        if not lines:
            raise ValidationError(_("参数缺失：lines 至少包含一条商品。"))

        self._validate_combo_structure(lines)

        order_lines = []
        for line in lines:
            order_lines.append((0, 0, self._prepare_line_values(line)))

        vals = {
            "table_id": table_id,
            "employee_id": employee_id,
            "member_id": payload.get("member_id"),
            "note": payload.get("note"),
            "order_line_ids": order_lines,
        }
        return vals

    def _prepare_line_values(self, line):
        required = {"product_id", "batch_id", "quantity"}
        if not required.issubset(line.keys()):
            missing = required - set(line.keys())
            raise ValidationError(_("明细缺失字段：%s") % ",".join(sorted(missing)))

        quantity = float(line.get("quantity", 0.0))
        if quantity <= 0:
            raise ValidationError(_("商品数量必须大于 0。"))

        price_unit = line.get("price_unit")
        line_vals = {
            "product_id": line["product_id"],
            "batch_id": line["batch_id"],
            "quantity": quantity,
            "note": line.get("note"),
            "combo_id": line.get("combo_id"),
            "is_combo_component": bool(line.get("is_combo_component", False)),
        }
        if price_unit is not None:
            line_vals["price_unit"] = float(price_unit)
        return line_vals

    def _validate_combo_structure(self, lines):
        combo_groups = {}
        for line in lines:
            combo_id = line.get("combo_id")
            if not combo_id:
                continue
            combo_groups.setdefault(combo_id, []).append(line)

        if not combo_groups:
            return True

        env = request.env["store.combo"]
        for combo_id, entries in combo_groups.items():
            combo = env.browse(combo_id)
            if not combo.exists():
                raise ValidationError(_("套餐 %(combo)s 不存在。", combo=combo_id))
            required_map = {item.product_id.id: item.quantity for item in combo.item_ids}
            aggregated = {}
            for entry in entries:
                product_id = entry.get("product_id")
                if product_id not in required_map:
                    raise ValidationError(
                        _("套餐 %(combo)s 未定义商品 %(product)s，请检查前端配置。",
                          combo=combo.display_name,
                          product=product_id)
                    )
                aggregated[product_id] = aggregated.get(product_id, 0.0) + float(entry.get("quantity", 0.0))

            base_multiplier = None
            for product_id, required_qty in required_map.items():
                total_qty = aggregated.get(product_id)
                if not total_qty:
                    raise ValidationError(
                        _("套餐 %(combo)s 缺少商品 %(product)s 的数量。",
                          combo=combo.display_name,
                          product=product_id)
                    )
                ratio = total_qty / required_qty
                if base_multiplier is None:
                    base_multiplier = ratio
                else:
                    precision = 0.0001
                    if abs(ratio - base_multiplier) > precision:
                        raise ValidationError(
                            _(
                                "套餐 %(combo)s 的商品数量不成比例，请确保一次添加的数量是套餐数量的整数倍。",
                                combo=combo.display_name,
                            )
                        )
        return True
