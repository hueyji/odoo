from odoo import http
from odoo.exceptions import AccessError
from odoo.http import request


class StoreSupplierApiController(http.Controller):
    def _ensure_company(self, company_id):
        if company_id and company_id not in request.env.user.company_ids.ids:
            raise AccessError("您无权访问该公司的供应商数据。")

    def _serialize_supplier(self, supplier):
        return {
            "id": supplier.id,
            "name": supplier.name,
            "partner_id": supplier.partner_id.id,
            "company_id": supplier.company_id.id,
            "rating_overall": supplier.rating_overall,
            "risk_level": supplier.risk_level,
            "is_blacklisted": supplier.is_blacklisted,
            "contact_user": supplier.contact_user_id.name if supplier.contact_user_id else None,
            "purchase_order_count": supplier.purchase_order_count,
            "purchase_amount_total": supplier.purchase_amount_total,
            "last_purchase_date": supplier.last_purchase_date,
        }

    @http.route("/api/v1/suppliers", type="json", auth="user", methods=["GET"])
    def list_suppliers(self, **kwargs):
        payload = request.jsonrequest or {}
        try:
            company_id = payload.get("company_id")
            self._ensure_company(company_id)
            user_company_ids = request.env.user.company_ids.ids
            domain = [("company_id", "in", [company_id] if company_id else user_company_ids)]
            if payload.get("is_blacklisted") is not None:
                domain.append(("is_blacklisted", "=", bool(payload["is_blacklisted"])) )
            if payload.get("min_rating"):
                domain.append(("rating_overall", ">=", float(payload["min_rating"])) )
            limit = payload.get("limit")
            limit = int(limit) if limit else None
            suppliers = request.env["store.supplier"].search(domain, order="rating_overall desc", limit=limit)
            return {
                "status": "success",
                "data": [self._serialize_supplier(supplier) for supplier in suppliers],
            }
        except AccessError as exc:
            return {"status": "error", "message": str(exc)}
