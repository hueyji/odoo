import io
import xlsxwriter

from odoo import _, fields, http
from odoo.exceptions import AccessError, ValidationError
from odoo.http import content_disposition, request


class StoreFinanceAPI(http.Controller):
    @staticmethod
    def _ensure_group(xmlid):
        if not request.env.user.has_group(xmlid):
            raise AccessError(_("您没有权限访问该接口。"))

    @staticmethod
    def _parse_company_id(company_id):
        if company_id:
            return int(company_id)
        return request.env.company.id

    @staticmethod
    def _transaction_to_dict(record):
        return {
            "id": record.id,
            "name": record.name,
            "date": fields.Datetime.to_string(record.date),
            "transaction_type": record.transaction_type,
            "amount": record.amount,
            "currency": record.currency_id.name,
            "payment_channel_id": record.payment_channel_id.id,
            "payment_channel_name": record.payment_channel_id.display_name,
            "state": record.state,
            "account_id": record.account_id.id if record.account_id else False,
            "journal_id": record.journal_id.id if record.journal_id else False,
            "company_id": record.company_id.id,
            "company_name": record.company_id.display_name,
            "amount_company_currency": record.amount_company_currency,
            "clearing_id": record.clearing_id.id if record.clearing_id else False,
            "description": record.description,
            "reference": record.reference,
        }

    @staticmethod
    def _clearing_to_dict(record):
        return {
            "id": record.id,
            "name": record.name,
            "date": fields.Date.to_string(record.date),
            "state": record.state,
            "company_id": record.company_id.id,
            "company_name": record.company_id.display_name,
            "total_amount_company_currency": record.total_amount_company_currency,
            "total_transaction_count": record.total_transaction_count,
            "approved_by": record.approved_by.id if record.approved_by else False,
            "approved_by_name": record.approved_by.display_name if record.approved_by else False,
            "approved_date": fields.Datetime.to_string(record.approved_date) if record.approved_date else False,
            "line_ids": [
                {
                    "transaction_id": line.transaction_id.id,
                    "transaction_name": line.transaction_id.display_name,
                    "amount_company_currency": line.amount_company_currency,
                    "amount_currency": line.amount_currency,
                    "currency": line.currency_id.name,
                }
                for line in record.line_ids
            ],
        }

    @http.route(
        "/api/v1/finance/transactions",
        auth="user",
        methods=["GET"],
        type="http",
        csrf=False,
    )
    def list_transactions(self, **params):
        self._ensure_group("store_finance.group_store_finance_user")

        env = request.env["store.account.transaction"].with_user(request.env.user)
        domain = []
        company_id = self._parse_company_id(params.get("company_id"))
        domain.append(("company_id", "=", company_id))

        if params.get("state"):
            domain.append(("state", "=", params["state"]))
        if params.get("transaction_type"):
            domain.append(("transaction_type", "=", params["transaction_type"]))
        if params.get("payment_channel_id"):
            domain.append(("payment_channel_id", "=", int(params["payment_channel_id"])))
        if params.get("payment_channel_code"):
            channel = request.env["store.finance.payment.channel"].sudo().search(
                [
                    ("code", "=", params["payment_channel_code"]),
                    ("company_id", "=", company_id),
                ],
                limit=1,
            )
            if channel:
                domain.append(("payment_channel_id", "=", channel.id))
            else:
                domain.append(("payment_channel_id", "=", 0))
        date_from = params.get("date_from")
        date_to = params.get("date_to")
        if date_from:
            domain.append(("date", ">=", date_from))
        if date_to:
            domain.append(("date", "<=", date_to))

        limit = int(params.get("limit", 80))
        offset = int(params.get("offset", 0))
        order = params.get("order", "date desc, id desc")

        records = env.with_context(force_company=company_id).search(
            domain, limit=limit, offset=offset, order=order
        )
        data = [self._transaction_to_dict(rec) for rec in records]
        total_count = env.with_context(force_company=company_id).search_count(domain)
        response = {
            "data": data,
            "paging": {"offset": offset, "limit": limit, "total": total_count},
        }
        return request.make_json_response(response)

    @http.route(
        "/api/v1/finance/transactions",
        auth="user",
        methods=["POST"],
        type="json",
        csrf=False,
    )
    def create_transaction(self, **payload):
        self._ensure_group("store_finance.group_store_finance_user")
        required_fields = ["transaction_type", "amount"]
        missing = [field for field in required_fields if field not in payload]
        if missing:
            raise ValidationError(_("缺少必填字段：%s") % ", ".join(missing))

        company_id = self._parse_company_id(payload.get("company_id"))
        env = request.env["store.account.transaction"].with_user(request.env.user).with_context(
            force_company=company_id
        )

        vals = {
            "transaction_type": payload["transaction_type"],
            "amount": float(payload["amount"]),
            "company_id": company_id,
        }

        if payload.get("payment_channel_id"):
            vals["payment_channel_id"] = int(payload["payment_channel_id"])
        elif payload.get("payment_channel_code"):
            channel = request.env["store.finance.payment.channel"].sudo().search(
                [
                    ("code", "=", payload["payment_channel_code"]),
                    ("company_id", "=", company_id),
                ],
                limit=1,
            )
            if not channel:
                raise ValidationError(_("未找到对应的支付渠道：%s") % payload["payment_channel_code"])
            vals["payment_channel_id"] = channel.id

        if payload.get("currency_id"):
            vals["currency_id"] = int(payload["currency_id"])
        elif payload.get("currency_code"):
            currency = request.env["res.currency"].sudo().search(
                [("name", "=", payload["currency_code"])], limit=1
            )
            if not currency:
                raise ValidationError(_("未找到对应币种：%s") % payload["currency_code"])
            vals["currency_id"] = currency.id

        if payload.get("date"):
            vals["date"] = payload["date"]
        if payload.get("reference"):
            vals["reference"] = payload["reference"]
        if payload.get("description"):
            vals["description"] = payload["description"]
        if payload.get("related_model"):
            related = payload["related_model"]
            if isinstance(related, str) and "," in related:
                model, record_id = related.split(",", 1)
                vals["related_model"] = "%s,%s" % (model.strip(), int(record_id))
            elif isinstance(related, dict):
                model = related.get("model")
                record_id = related.get("id")
                if not model or not record_id:
                    raise ValidationError(_("关联记录格式不正确。"))
                vals["related_model"] = "%s,%s" % (model, int(record_id))
            else:
                raise ValidationError(_("关联记录格式不正确。"))

        transaction = env.create(vals)
        if payload.get("auto_confirm", True):
            transaction.action_confirm()

        return {"data": self._transaction_to_dict(transaction)}

    @http.route(
        "/api/v1/finance/clearing",
        auth="user",
        methods=["POST"],
        type="json",
        csrf=False,
    )
    def create_clearing(self, **payload):
        self._ensure_group("store_finance.group_store_finance_manager")
        transaction_ids = payload.get("transaction_ids") or []
        if not transaction_ids:
            raise ValidationError(_("请提供需要清算的流水 ID 列表。"))

        company_id = self._parse_company_id(payload.get("company_id"))
        env = request.env["store.finance.clearing"].with_user(request.env.user).with_context(
            force_company=company_id
        )
        lines = [(0, 0, {"transaction_id": int(tid)}) for tid in transaction_ids]

        vals = {
            "company_id": company_id,
            "line_ids": lines,
        }

        if payload.get("note"):
            vals["note"] = payload["note"]
        if payload.get("date"):
            vals["date"] = payload["date"]

        clearing = env.create(vals)
        if payload.get("auto_confirm", True):
            clearing.action_confirm()
        if payload.get("auto_approve"):
            clearing.action_approve()

        return {"data": self._clearing_to_dict(clearing)}

    @http.route(
        "/api/v1/finance/clearing/<int:clearing_id>/approve",
        auth="user",
        methods=["POST"],
        type="json",
        csrf=False,
    )
    def approve_clearing(self, clearing_id, **payload):
        self._ensure_group("store_finance.group_store_finance_manager")
        clearing = request.env["store.finance.clearing"].with_user(request.env.user).browse(
            clearing_id
        )
        if not clearing.exists():
            raise ValidationError(_("未找到对应的清算单。"))
        clearing.ensure_one()
        clearing.check_access_rights("write")
        clearing.check_access_rule("write")
        clearing.action_approve()
        return {"data": self._clearing_to_dict(clearing)}

    @http.route(
        "/api/v1/finance/clearing/<int:clearing_id>/export",
        auth="user",
        methods=["GET"],
        type="http",
        csrf=False,
    )
    def export_clearing(self, clearing_id, **params):
        self._ensure_group("store_finance.group_store_finance_manager")
        clearing = request.env["store.finance.clearing"].with_user(request.env.user).browse(
            clearing_id
        )
        if not clearing.exists():
            raise ValidationError(_("未找到对应的清算单。"))
        clearing.ensure_one()
        clearing.check_access_rights("read")
        clearing.check_access_rule("read")

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        worksheet = workbook.add_worksheet("清算明细")

        header_format = workbook.add_format({"bold": True, "bg_color": "#EFEFEF"})
        money_format = workbook.add_format({"num_format": "#,##0.00"})

        headers = [
            "流水编号",
            "流水类型",
            "原币金额",
            "本币金额",
            "币种",
            "支付渠道",
            "状态",
            "审核状态",
            "备注",
        ]
        for col, title in enumerate(headers):
            worksheet.write(0, col, title, header_format)

        row = 1
        for line in clearing.line_ids:
            transaction = line.transaction_id
            worksheet.write(row, 0, transaction.name or "")
            worksheet.write(row, 1, dict(transaction.TRANSACTION_TYPES).get(transaction.transaction_type, transaction.transaction_type))
            worksheet.write_number(row, 2, line.amount_currency, money_format)
            worksheet.write_number(row, 3, line.amount_company_currency, money_format)
            worksheet.write(row, 4, line.currency_id.name or "")
            worksheet.write(row, 5, transaction.payment_channel_id.display_name if transaction.payment_channel_id else "")
            worksheet.write(row, 6, transaction.state)
            worksheet.write(row, 7, dict(clearing._fields["state"].selection).get(clearing.state, clearing.state))
            worksheet.write(row, 8, transaction.description or "")
            row += 1

        worksheet.write(row, 1, "合计", header_format)
        worksheet.write_number(row, 2, sum(clearing.line_ids.mapped("amount_currency")), money_format)
        worksheet.write_number(row, 3, clearing.total_amount_company_currency, money_format)
        worksheet.set_column(0, 0, 18)
        worksheet.set_column(1, 1, 14)
        worksheet.set_column(2, 3, 12)
        worksheet.set_column(4, 5, 14)
        worksheet.set_column(8, 8, 30)

        info_sheet = workbook.add_worksheet("清算信息")
        info_sheet.write(0, 0, "清算编号", header_format)
        info_sheet.write(0, 1, clearing.name or "")
        info_sheet.write(1, 0, "清算日期", header_format)
        info_sheet.write(1, 1, fields.Date.to_string(clearing.date))
        info_sheet.write(2, 0, "公司", header_format)
        info_sheet.write(2, 1, clearing.company_id.display_name)
        info_sheet.write(3, 0, "审核状态", header_format)
        info_sheet.write(3, 1, dict(clearing._fields["state"].selection).get(clearing.state, clearing.state))
        info_sheet.write(4, 0, "审核人", header_format)
        info_sheet.write(4, 1, clearing.approved_by.display_name if clearing.approved_by else "")
        info_sheet.write(5, 0, "审核时间", header_format)
        info_sheet.write(5, 1, fields.Datetime.to_string(clearing.approved_date) if clearing.approved_date else "")
        info_sheet.write(6, 0, "备注", header_format)
        info_sheet.write(6, 1, clearing.note or "")

        workbook.close()
        output.seek(0)
        filename = "%s.xlsx" % (clearing.name or "clearing")
        headers = [
            ("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            ("Content-Disposition", content_disposition(filename)),
        ]
        return request.make_response(output.getvalue(), headers=headers)
