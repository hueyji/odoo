from odoo import fields, http
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request


class StoreInventoryApiController(http.Controller):
    def _ensure_company(self, company_id):
        if company_id not in request.env.user.company_ids.ids:
            raise AccessError("您无权访问该公司库存数据。")

    def _serialize_batch(self, batch):
        return {
            "id": batch.id,
            "name": batch.name,
            "product": {
                "id": batch.product_id.id,
                "name": batch.product_id.display_name,
            },
            "supplier": {
                "id": batch.supplier_id.id,
                "name": batch.supplier_id.display_name,
            } if batch.supplier_id else None,
            "company_id": batch.company_id.id,
            "warehouse_id": batch.warehouse_id.id if batch.warehouse_id else None,
            "location_id": batch.location_id.id if batch.location_id else None,
            "qty_available": batch.qty_available,
            "qty_initial": batch.qty_initial,
            "reservation_qty": batch.reservation_qty,
            "state": batch.state,
            "aging_days": batch.aging_days,
            "aging_start_date": batch.aging_start_date,
            "best_before_date": batch.best_before_date,
            "lot_ids": [
                {
                    "id": lot.id,
                    "name": lot.name,
                    "expiration_date": lot.expiration_date,
                }
                for lot in batch.lot_ids
            ],
        }

    @http.route("/api/v1/inventory/batches", type="json", auth="user", methods=["POST"], csrf=False)
    def create_batch(self, **kwargs):
        payload = request.jsonrequest or {}
        try:
            company_id = payload.get("company_id") or request.env.company.id
            self._ensure_company(company_id)
            Batch = request.env["store.inventory.batch"].with_context(tracking_disable=True)
            vals = {
                "product_id": payload["product_id"],
                "product_uom_id": payload.get("product_uom_id") or request.env["product.product"].browse(payload["product_id"]).uom_id.id,
                "supplier_id": payload.get("supplier_id"),
                "company_id": company_id,
                "warehouse_id": payload.get("warehouse_id"),
                "location_id": payload.get("location_id"),
                "qty_initial": payload.get("qty_initial", 0.0),
                "purchase_price": payload.get("purchase_price", 0.0),
                "currency_id": payload.get("currency_id") or request.env.company.currency_id.id,
                "aging_start_date": payload.get("aging_start_date") or fields.Date.today(),
                "best_before_date": payload.get("best_before_date"),
                "state": payload.get("state") or "in_stock",
                "note": payload.get("note"),
            }
            batch = Batch.create(vals)
            return {"status": "success", "data": self._serialize_batch(batch)}
        except (ValidationError, AccessError, KeyError) as exc:
            request.env.cr.rollback()
            return {"status": "error", "message": str(exc)}

    @http.route("/api/v1/inventory/batches/<int:batch_id>", type="json", auth="user", methods=["GET"])
    def get_batch(self, batch_id, **kwargs):
        batch = request.env["store.inventory.batch"].browse(batch_id)
        if not batch.exists():
            return {"status": "error", "message": "批次不存在。"}
        self._ensure_company(batch.company_id.id)
        return {"status": "success", "data": self._serialize_batch(batch)}

    @http.route("/api/v1/inventory/transfers", type="json", auth="user", methods=["POST"], csrf=False)
    def create_transfer(self, **kwargs):
        if not request.env.user.has_group("store_inventory.group_store_inventory_manager"):
            return {"status": "error", "message": "当前用户无调拨审批权限。"}
        payload = request.jsonrequest or {}
        try:
            batch = request.env["store.inventory.batch"].browse(payload["batch_id"])
            if not batch.exists():
                raise ValidationError("批次不存在。")
            self._ensure_company(batch.company_id.id)
            operation_vals = {
                "batch_id": batch.id,
                "company_id": batch.company_id.id,
                "operation_type": "transfer",
                "requested_qty": payload["quantity"],
                "source_location_id": payload.get("source_location_id") or batch.location_id.id,
                "dest_location_id": payload.get("dest_location_id"),
                "scheduled_date": payload.get("scheduled_date") or fields.Datetime.now(),
                "note": payload.get("note"),
                "unit_cost": payload.get("unit_cost") or batch.purchase_price,
                "currency_id": payload.get("currency_id") or batch.currency_id.id,
            }
            operation = request.env["store.inventory.operation"].create(operation_vals)
            operation.action_submit()
            operation.action_approve()
            operation.action_execute()
            data = {
                "operation_id": operation.id,
                "operation_name": operation.name,
                "state": operation.state,
                "picking_id": operation.picking_id.id if operation.picking_id else None,
                "picking_name": operation.picking_id.name if operation.picking_id else None,
            }
            return {"status": "success", "data": data}
        except (ValidationError, AccessError, KeyError) as exc:
            request.env.cr.rollback()
            return {"status": "error", "message": str(exc)}
