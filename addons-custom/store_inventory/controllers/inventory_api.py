import csv
import io
from datetime import datetime

from odoo import _, fields
from odoo.http import Controller, request, route


class InventoryAPI(Controller):
    def _json_response(self, data=None, status=200, message=None):
        payload = {"success": 200 <= status < 300}
        if message:
            payload["message"] = message
        if data is not None:
            payload["data"] = data
        return request.make_json_response(payload, status=status)

    def _resolve_record(self, model, value, search_field=None):
        if not value:
            return request.env[model]
        env = request.env[model]
        record = env.browse()
        if isinstance(value, int):
            record = env.browse(value)
        elif isinstance(value, str):
            if value.isdigit():
                record = env.browse(int(value))
            else:
                try:
                    record = request.env.ref(value)
                except ValueError:
                    if search_field:
                        record = env.search([(search_field, "=", value)], limit=1)
        if not record or not record.exists():
            raise ValueError(_("无法定位记录：%(model)s=%(value)s", model=model, value=value))
        return record

    def _to_float(self, value, field_name):
        try:
            return float(value)
        except Exception as exc:  # pylint: disable=broad-except
            raise ValueError(_("字段 %(field)s 需要数值类型。", field=field_name)) from exc

    def _to_date(self, value, field_name):
        if not value:
            return fields.Date.context_today(request.env.user)
        if isinstance(value, datetime):
            return value.date()
        try:
            return fields.Date.from_string(value)
        except Exception as exc:  # pylint: disable=broad-except
            raise ValueError(_("字段 %(field)s 需要有效日期。", field=field_name)) from exc

    def _serialize_batch(self, batch):
        return {
            "id": batch.id,
            "name": batch.name,
            "product": {
                "id": batch.product_id.id,
                "name": batch.product_id.display_name,
            },
            "company_id": batch.company_id.id,
            "company_name": batch.company_id.display_name,
            "qty_initial": batch.qty_initial,
            "qty_available": batch.qty_available,
            "purchase_price": batch.purchase_price,
            "currency": batch.currency_id.name,
            "aging_days": batch.aging_days,
            "aging_stage": batch.aging_stage,
            "state": batch.state,
            "attention_flag": batch.attention_flag,
            "supplier_id": batch.supplier_id.id,
            "supplier_name": batch.supplier_id.display_name if batch.supplier_id else None,
            "warehouse_id": batch.warehouse_id.id,
            "location_id": batch.location_id.id,
            "aging_start_date": batch.aging_start_date,
        }

    def _serialize_transfer(self, transfer):
        return {
            "id": transfer.id,
            "name": transfer.name,
            "batch_id": transfer.batch_id.id,
            "source_company_id": transfer.source_company_id.id,
            "target_company_id": transfer.target_company_id.id,
            "qty": transfer.qty,
            "unit_price": transfer.unit_price,
            "currency": transfer.currency_id.name,
            "state": transfer.state,
            "link_group_id": transfer.link_group_id.id if transfer.link_group_id else None,
            "out_move_id": transfer.out_move_id.id if transfer.out_move_id else None,
            "in_move_id": transfer.in_move_id.id if transfer.in_move_id else None,
        }

    def _serialize_supplier(self, supplier):
        return {
            "id": supplier.id,
            "name": supplier.name,
            "partner_id": supplier.partner_id.id,
            "company_id": supplier.company_id.id,
            "rating": supplier.rating,
            "delivery_lead_days": supplier.delivery_lead_days,
            "last_purchase_date": supplier.last_purchase_date,
            "last_purchase_amount": supplier.last_purchase_amount,
            "is_blacklisted": supplier.is_blacklisted,
            "total_purchase_amount": supplier.total_purchase_amount,
            "total_purchase_qty": supplier.total_purchase_qty,
            "average_purchase_price": supplier.average_purchase_price,
            "order_count": supplier.purchase_order_count,
        }

    @route("/api/inventory/batches", type="json", auth="user", methods=["POST"])
    def create_batch(self, **payload):
        try:
            product = self._resolve_record("product.product", payload.get("product_id"), search_field="default_code")
            company = self._resolve_record("res.company", payload.get("company_id")) or request.env.company
            supplier = False
            if payload.get("supplier_id"):
                supplier = self._resolve_record("res.partner", payload.get("supplier_id"))
            supplier_record = False
            if payload.get("supplier_record_id"):
                supplier_record = self._resolve_record("store.supplier", payload.get("supplier_record_id"))
            qty = self._to_float(payload.get("qty_initial"), "qty_initial")
            purchase_price = self._to_float(payload.get("purchase_price", 0.0), "purchase_price")
            aging_start = self._to_date(payload.get("aging_start_date"), "aging_start_date")
            warehouse = False
            if payload.get("warehouse_id"):
                warehouse = self._resolve_record("stock.warehouse", payload.get("warehouse_id"))
            location = False
            if payload.get("location_id"):
                location = self._resolve_record("stock.location", payload.get("location_id"))
        except ValueError as error:
            return self._json_response(status=400, message=str(error))

        Batch = request.env["store.inventory.batch"].with_company(company).sudo()
        Move = request.env["store.inventory.move"].with_company(company).sudo()

        batch_vals = {
            "product_id": product.id,
            "qty_initial": qty,
            "qty_available": 0.0,
            "purchase_price": purchase_price,
            "aging_start_date": aging_start,
            "supplier_id": supplier.id if supplier else False,
            "supplier_record_id": supplier_record.id if supplier_record else False,
            "warehouse_id": warehouse.id if warehouse else False,
            "location_id": location.id if location else False,
            "company_id": company.id,
        }
        batch = Batch.create(batch_vals)

        move = Move.create(
            {
                "batch_id": batch.id,
                "move_type": "incoming",
                "quantity": qty,
                "unit_price": purchase_price,
                "company_id": company.id,
                "note": payload.get("note"),
            }
        )
        move.with_context(skip_approval_activity=True).action_submit()
        move.with_context(bypass_inventory_approval=True).action_approve()

        return self._json_response(
            data=self._serialize_batch(batch),
            status=201,
            message=_("批次创建成功。"),
        )

    @route("/api/inventory/batches/<int:batch_id>", type="json", auth="user", methods=["GET"])
    def get_batch(self, batch_id):
        batch = request.env["store.inventory.batch"].browse(batch_id)
        if not batch.exists():
            return self._json_response(status=404, message=_("未找到指定的批次。"))
        batch = batch.sudo()
        return self._json_response(data=self._serialize_batch(batch))

    @route("/api/inventory/transfers", type="json", auth="user", methods=["POST"])
    def create_transfer(self, **payload):
        try:
            batch = self._resolve_record("store.inventory.batch", payload.get("source_batch_id"))
            target_company = self._resolve_record("res.company", payload.get("target_company_id"))
            qty = self._to_float(payload.get("qty"), "qty")
            unit_price = payload.get("unit_price")
            if unit_price is not None:
                unit_price = self._to_float(unit_price, "unit_price")
            warehouse = False
            if payload.get("target_warehouse_id"):
                warehouse = self._resolve_record("stock.warehouse", payload.get("target_warehouse_id"))
            location = False
            if payload.get("target_location_id"):
                location = self._resolve_record("stock.location", payload.get("target_location_id"))
        except ValueError as error:
            return self._json_response(status=400, message=str(error))

        Transfer = request.env["store.inventory.transfer"].sudo()
        transfer_vals = {
            "batch_id": batch.id,
            "target_company_id": target_company.id,
            "qty": qty,
            "unit_price": unit_price if unit_price is not None else batch.purchase_price,
            "reason": payload.get("reason"),
            "note": payload.get("note"),
            "target_warehouse_id": warehouse.id if warehouse else False,
            "target_location_id": location.id if location else False,
        }
        transfer = Transfer.create(transfer_vals)
        transfer.action_submit()
        auto_approve = payload.get("auto_approve")
        user = request.env.user
        if auto_approve and not user.has_group("stock.group_stock_manager"):
            return self._json_response(
                data=self._serialize_transfer(transfer),
                status=202,
                message=_("调拨申请已提交，等待库存经理审批。"),
            )
        if user.has_group("stock.group_stock_manager"):
            transfer.with_context(bypass_inventory_approval=True, skip_approval_activity=True).action_approve()
        return self._json_response(
            data=self._serialize_transfer(transfer),
            status=201,
            message=_("调拨申请已创建。"),
        )

    @route("/api/suppliers", type="json", auth="user", methods=["GET"])
    def list_suppliers(self, **params):
        domain = []
        company = params.get("company_id")
        rating = params.get("rating")
        include_blacklist = params.get("include_blacklist", False)
        try:
            if company:
                company_rec = self._resolve_record("res.company", company)
                domain.append(("company_id", "=", company_rec.id))
            if rating:
                domain.append(("rating", "=", rating))
            if not include_blacklist:
                domain.append(("is_blacklisted", "=", False))
        except ValueError as error:
            return self._json_response(status=400, message=str(error))

        Supplier = request.env["store.supplier"].sudo()
        suppliers = Supplier.search(domain)
        data = [self._serialize_supplier(record) for record in suppliers]
        return self._json_response(data=data)

    @route("/store_inventory/batches/export", type="http", auth="user", methods=["GET"], csrf=False)
    def export_batches(self, ids=None, **kwargs):  # pylint: disable=unused-argument
        env = request.env["store.inventory.batch"]
        domain = []
        if ids:
            try:
                id_list = [int(value) for value in ids.split(",") if value]
            except ValueError:
                return request.make_response("", headers=[("Status", "400 Bad Request")])
            domain.append(("id", "in", id_list))
        batches = env.search(domain)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow([
            "name",
            "product",
            "company",
            "warehouse",
            "location",
            "qty_initial",
            "qty_available",
            "aging_stage",
            "aging_days",
            "attention",
        ])
        for batch in batches:
            writer.writerow(
                [
                    batch.name,
                    batch.product_id.display_name,
                    batch.company_id.display_name if batch.company_id else "",
                    batch.warehouse_id.display_name if batch.warehouse_id else "",
                    batch.location_id.display_name if batch.location_id else "",
                    batch.qty_initial,
                    batch.qty_available,
                    batch.aging_stage,
                    batch.aging_days,
                    "Y" if batch.attention_flag else "N",
                ]
            )
        csv_content = buffer.getvalue()
        filename = "inventory_batches.csv"
        headers = [
            ("Content-Type", "text/csv; charset=utf-8"),
            ("Content-Disposition", f"attachment; filename={filename}"),
        ]
        return request.make_response(csv_content, headers=headers)
