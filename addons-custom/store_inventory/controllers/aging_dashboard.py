import io

from odoo import fields, http
from odoo.http import request, content_disposition

import xlsxwriter


class StoreInventoryDashboardController(http.Controller):
    @http.route("/store_inventory/aging_dashboard/data", type="json", auth="user")
    def get_dashboard_data(self):
        metrics = request.env["store.inventory.batch"].sudo().get_aging_dashboard_metrics()
        return metrics

    @http.route("/store_inventory/aging_dashboard/export", type="http", auth="user")
    def export_dashboard(self, **kwargs):
        metrics = request.env["store.inventory.batch"].sudo().get_aging_dashboard_metrics()
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})

        header_format = workbook.add_format({
            "bold": True,
            "bg_color": "#2C7BE5",
            "font_color": "#FFFFFF",
            "border": 1,
        })
        text_format = workbook.add_format({"border": 1})
        number_format = workbook.add_format({"border": 1, "num_format": "#,##0.00"})
        int_format = workbook.add_format({"border": 1, "num_format": "#,##0"})

        summary_sheet = workbook.add_worksheet("陈化汇总")
        summary_headers = [
            "陈化区间",
            "批次数",
            "现存数量",
            "平均陈化天数",
        ]
        for col, title in enumerate(summary_headers):
            summary_sheet.write(0, col, title, header_format)
        for row, item in enumerate(metrics.get("summary", []), start=1):
            summary_sheet.write(row, 0, item["bucket_label"], text_format)
            summary_sheet.write(row, 1, item["batch_count"], int_format)
            summary_sheet.write(row, 2, item["qty_available"], number_format)
            summary_sheet.write(row, 3, item["avg_aging_days"], number_format)
        summary_sheet.set_column(0, 0, 18)
        summary_sheet.set_column(1, 1, 12)
        summary_sheet.set_column(2, 3, 18)
        summary_sheet.freeze_panes(1, 0)

        detail_sheet = workbook.add_worksheet("批次明细")
        detail_headers = [
            "陈化区间",
            "批次编号",
            "商品",
            "供应商",
            "所属公司",
            "库位",
            "库存数量",
            "陈化天数",
            "状态",
        ]
        for col, title in enumerate(detail_headers):
            detail_sheet.write(0, col, title, header_format)
        row = 1
        for bucket in metrics.get("bucket_defs", []):
            key = bucket["key"]
            label = bucket["label"]
            for record in metrics.get("all_batches", {}).get(key, []):
                detail_sheet.write(row, 0, label, text_format)
                detail_sheet.write(row, 1, record["name"], text_format)
                detail_sheet.write(row, 2, record["product"], text_format)
                detail_sheet.write(row, 3, record.get("supplier") or "", text_format)
                detail_sheet.write(row, 4, record.get("company") or "", text_format)
                detail_sheet.write(row, 5, record.get("location") or "", text_format)
                detail_sheet.write(row, 6, record["qty_available"], number_format)
                detail_sheet.write(row, 7, record.get("aging_days") or 0, int_format)
                detail_sheet.write(row, 8, record.get("state") or "", text_format)
                row += 1
        detail_sheet.set_column(0, 1, 18)
        detail_sheet.set_column(2, 5, 24)
        detail_sheet.set_column(6, 7, 14)
        detail_sheet.set_column(8, 8, 12)
        detail_sheet.freeze_panes(1, 0)

        workbook.close()
        output.seek(0)
        filename = "陈化看板-%s.xlsx" % fields.Date.today()
        headers = [
            ("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            ("Content-Disposition", content_disposition(filename)),
        ]
        return request.make_response(output.getvalue(), headers=headers)
