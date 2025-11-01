# -*- coding: utf-8 -*-
import logging
from typing import Any, Dict, Iterable, Optional

from werkzeug import exceptions

from odoo import http
from odoo.http import request

_LOGGER = logging.getLogger(__name__)


class BrandCoreRestController(http.Controller):
    """Shared helpers for brand_core REST endpoints."""

    @staticmethod
    def _json_success(
        data: Optional[Dict[str, Any]] = None, message: str = "操作成功", status: int = 200
    ):
        payload = {"success": True, "message": message}
        if data is not None:
            payload["data"] = data
        response = request.make_json_response(payload)
        response.status_code = status
        return response

    @staticmethod
    def _json_error(message: str, code: str = "brand_core_error", status: int = 400):
        payload = {"success": False, "code": code, "message": message}
        response = request.make_json_response(payload)
        response.status_code = status
        return response

    @staticmethod
    def _parse_json(required_fields: Optional[Iterable[str]] = None) -> Dict[str, Any]:
        try:
            data = request.get_json_data()
        except ValueError as exc:
            _LOGGER.exception("Invalid JSON payload")
            raise exceptions.BadRequest("请求体必须是合法 JSON") from exc
        data = data or {}
        if required_fields:
            missing = [field for field in required_fields if field not in data]
            if missing:
                raise exceptions.BadRequest("缺少必要字段：%s" % ", ".join(missing))
        return data
