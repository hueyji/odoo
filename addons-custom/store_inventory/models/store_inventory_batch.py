from datetime import date

from collections import defaultdict

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


AGING_BUCKETS = [
    ("0_30", 0, 30, "0-30 天"),
    ("31_90", 31, 90, "31-90 天"),
    ("91_180", 91, 180, "91-180 天"),
    ("181_365", 181, 365, "181-365 天"),
    ("gt_365", 366, None, "超过 365 天"),
]

class StoreInventoryBatch(models.Model):
    _name = "store.inventory.batch"
    _description = "陈化批次"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "aging_start_date desc, id desc"
    _check_company_auto = True

    name = fields.Char(
        string="批次编号",
        required=True,
        copy=False,
        default=_("新建批次"),
        tracking=True,
    )
    product_id = fields.Many2one(
        "product.product",
        string="商品",
        required=True,
        tracking=True,
        domain=[("type", "!=", "service")],
    )
    product_uom_id = fields.Many2one(
        "uom.uom",
        string="计量单位",
        required=True,
    )
    supplier_id = fields.Many2one(
        "res.partner",
        string="供应商",
        domain=[("is_company", "=", True)],
        help="采购该批次的供应商信息，用于后续供应商模块对接。",
        tracking=True,
    )
    purchase_price = fields.Monetary(
        string="进货单价",
        currency_field="currency_id",
        help="记录含税进货单价，供成本核算与补差参考。",
        tracking=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="币种",
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    qty_initial = fields.Float(
        string="进货数量",
        help="批次的初始进货数量。",
        digits="Product Unit of Measure",
        default=0.0,
        tracking=True,
    )
    qty_available = fields.Float(
        string="现存数量",
        compute="_compute_qty_available",
        digits="Product Unit of Measure",
        store=True,
        readonly=True,
        help="同步 stock.quant 批次库存；盘点/报损/调拨同步更新。",
    )
    reservation_qty = fields.Float(
        string="锁定数量",
        compute="_compute_qty_available",
        digits="Product Unit of Measure",
        store=True,
        readonly=True,
        help="已被订单或调拨占用但尚未出库的数量。",
    )
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="所属仓库",
        tracking=True,
        help="批次当前所在仓库，用于门店调拨与审批。",
    )
    location_id = fields.Many2one(
        "stock.location",
        string="库位",
        domain=[("usage", "=", "internal")],
        tracking=True,
    )
    aging_start_date = fields.Date(
        string="陈化开始日期",
        required=True,
        tracking=True,
    )
    aging_days = fields.Integer(
        string="陈化天数",
        compute="_compute_aging_days",
        store=True,
    )
    best_before_date = fields.Date(
        string="建议售罄日期",
        help="结合陈化计划的建议售罄日期，供门店管理使用。",
    )
    state = fields.Selection(
        [
            ("draft", "草稿"),
            ("in_stock", "在库"),
            ("transit", "调拨中"),
            ("loss", "报损"),
            ("done", "售罄"),
        ],
        string="状态",
        default="draft",
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="所属公司",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    picking_ids = fields.Many2many(
        "stock.picking",
        string="相关拣货",
        compute="_compute_related_records",
        compute_sudo=True,
        readonly=True,
    )
    move_ids = fields.One2many(
        "stock.move",
        "store_batch_id",
        string="库存移动",
        readonly=True,
    )
    quant_ids = fields.One2many(
        "stock.quant",
        "store_batch_id",
        string="库存明细",
        readonly=True,
    )
    picking_count = fields.Integer(
        string="拣货单数量",
        compute="_compute_related_records",
    )
    quant_count = fields.Integer(
        string="库存明细数量",
        compute="_compute_related_records",
    )
    operation_ids = fields.One2many(
        "store.inventory.operation",
        "batch_id",
        string="库存操作",
        readonly=True,
    )
    operation_count = fields.Integer(
        string="操作次数",
        compute="_compute_related_records",
    )
    lot_ids = fields.One2many(
        "stock.lot",
        "store_batch_id",
        string="序列批号",
        readonly=True,
    )
    lot_count = fields.Integer(
        string="批号数量",
        compute="_compute_related_records",
    )
    note = fields.Text(
        string="备注",
        help="补充陈化要求、质检记录等信息。",
    )
    active = fields.Boolean(default=True, string="启用")
    last_alert_date = fields.Date(string="上次提醒日期")

    _sql_constraints = [
        (
            "name_company_unique",
            "unique(name, company_id)",
            "批次编号在同一公司内必须唯一。",
        )
    ]

    @api.constrains("warehouse_id", "location_id")
    def _check_location_company(self):
        for batch in self:
            if batch.location_id and batch.location_id.company_id:
                if batch.location_id.company_id != batch.company_id:
                    raise ValidationError(_("库位所属公司必须与批次一致。"))
            if batch.warehouse_id and batch.warehouse_id.company_id:
                if batch.warehouse_id.company_id != batch.company_id:
                    raise ValidationError(_("仓库所属公司必须与批次一致。"))

    @api.depends("aging_start_date")
    def _compute_aging_days(self):
        today = date.today()
        for batch in self:
            if batch.aging_start_date:
                batch.aging_days = max((today - batch.aging_start_date).days, 0)
            else:
                batch.aging_days = 0

    @api.depends("quant_ids.quantity", "quant_ids.reserved_quantity")
    def _compute_qty_available(self):
        for batch in self:
            quantities = batch.quant_ids.mapped("quantity")
            reserved = batch.quant_ids.mapped("reserved_quantity")
            batch.qty_available = sum(quantities)
            batch.reservation_qty = sum(reserved)

    @api.depends("move_ids", "move_ids.picking_id", "quant_ids", "operation_ids", "lot_ids")
    def _compute_related_records(self):
        for batch in self:
            picking_set = batch.move_ids.mapped("picking_id")
            batch.picking_ids = picking_set
            batch.picking_count = len(picking_set)
            batch.quant_count = len(batch.quant_ids)
            batch.operation_count = len(batch.operation_ids)
            batch.lot_count = len(batch.lot_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == _("新建批次"):
                vals["name"] = self.env["ir.sequence"].next_by_code("store.inventory.batch") or _("新建批次")
            if vals.get("product_id") and not vals.get("product_uom_id"):
                product = self.env["product.product"].browse(vals["product_id"])
                vals["product_uom_id"] = product.uom_id.id
            if vals.get("warehouse_id") and not vals.get("company_id"):
                warehouse = self.env["stock.warehouse"].browse(vals["warehouse_id"])
                vals["company_id"] = warehouse.company_id.id
                if not vals.get("location_id"):
                    vals["location_id"] = warehouse.lot_stock_id.id
            elif vals.get("warehouse_id") and not vals.get("location_id"):
                warehouse = self.env["stock.warehouse"].browse(vals["warehouse_id"])
                vals["location_id"] = warehouse.lot_stock_id.id
            if vals.get("location_id") and not vals.get("company_id"):
                location = self.env["stock.location"].browse(vals["location_id"])
                vals["company_id"] = location.company_id.id
        batches = super().create(vals_list)
        return batches

    def action_set_in_stock(self):
        for batch in self:
            batch.state = "in_stock"
        return True

    def action_mark_transit(self):
        for batch in self:
            batch.state = "transit"
        return True

    def action_mark_loss(self):
        for batch in self:
            batch.state = "loss"
        return True

    def action_mark_done(self):
        for batch in self:
            batch.state = "done"
        return True

    def action_open_pickings(self):
        self.ensure_one()
        action = self.env.ref("stock.action_picking_tree_all").read()[0]
        action["domain"] = [("id", "in", self.picking_ids.ids)]
        action["context"] = {
            "default_company_id": self.company_id.id,
        }
        return action

    def action_open_quants(self):
        self.ensure_one()
        action = self.env.ref("stock.action_stock_quant_tree").read()[0]
        action["domain"] = [("store_batch_id", "=", self.id)]
        action["context"] = {
            "default_store_batch_id": self.id,
            "search_default_store_batch_id": self.id,
        }
        return action

    def action_open_operations(self):
        self.ensure_one()
        action = self.env.ref("store_inventory.action_store_inventory_operation").read()[0]
        action["domain"] = [("batch_id", "=", self.id)]
        action["context"] = {
            "default_batch_id": self.id,
            "default_company_id": self.company_id.id,
        }
        return action

    def action_view_aging_dashboard(self):
        return self.env.ref("store_inventory.action_store_inventory_aging_dashboard").read()[0]

    def action_open_lots(self):
        self.ensure_one()
        action = self.env.ref("stock.action_production_lot_form").read()[0]
        action["domain"] = [("store_batch_id", "=", self.id)]
        action.setdefault("context", {})
        action["context"].update({
            "default_store_batch_id": self.id,
            "search_default_store_batch_id": self.id,
        })
        return action

    @api.model
    def _get_bucket_definitions(self):
        _ = self.env._
        return [
            {
                "key": key,
                "label": _(label),
                "start": start,
                "end": end,
            }
            for key, start, end, label in AGING_BUCKETS
        ]

    @api.model
    def _match_bucket(self, aging_days):
        for key, start, end, _label in AGING_BUCKETS:
            if aging_days is None:
                continue
            if aging_days < start:
                continue
            if end is None or aging_days <= end:
                return key
        return AGING_BUCKETS[-1][0]

    @api.model
    def get_aging_dashboard_metrics(self, company_ids=None):
        user_company_ids = company_ids or self.env.user.company_ids.ids
        domain = [
            ("company_id", "in", user_company_ids),
            ("active", "=", True),
        ]
        batches = self.search(domain)
        bucket_defs = self._get_bucket_definitions()
        summary = {bucket["key"]: defaultdict(float) for bucket in bucket_defs}
        detail = {bucket["key"]: [] for bucket in bucket_defs}

        for batch in batches:
            bucket_key = self._match_bucket(batch.aging_days)
            info = summary[bucket_key]
            info["batch_count"] += 1
            info["qty_available"] += batch.qty_available
            info["total_days"] += batch.aging_days or 0
            detail[bucket_key].append(
                {
                    "name": batch.name,
                    "product": batch.product_id.display_name,
                    "supplier": batch.supplier_id.display_name,
                    "qty_available": batch.qty_available,
                    "aging_days": batch.aging_days,
                    "company": batch.company_id.display_name,
                    "location": batch.location_id.display_name or "",
                    "state": batch.state,
                }
            )

        summary_list = []
        total_qty = 0.0
        total_batches = 0
        for bucket in bucket_defs:
            key = bucket["key"]
            data = summary[key]
            avg_days = 0.0
            if data["batch_count"]:
                avg_days = data["total_days"] / data["batch_count"]
            total_qty += data["qty_available"]
            total_batches += data["batch_count"]
            summary_list.append(
                {
                    "bucket_key": key,
                    "bucket_label": bucket["label"],
                    "batch_count": int(data["batch_count"]),
                    "qty_available": data["qty_available"],
                    "avg_aging_days": round(avg_days, 1) if avg_days else 0,
                }
            )

        # 对明细按照库存量排序，取前 10 条用于展示
        sorted_detail = {}
        top_batches = {}
        for key, records in detail.items():
            ordered = sorted(records, key=lambda r: (r["qty_available"], r["aging_days"]), reverse=True)
            sorted_detail[key] = ordered
            top_batches[key] = ordered[:10]

        return {
            "summary": summary_list,
            "top_batches": top_batches,
            "all_batches": sorted_detail,
            "total_qty": total_qty,
            "total_batches": total_batches,
            "bucket_defs": bucket_defs,
            "generated_on": fields.Date.context_today(self),
        }

    @api.model
    def cron_post_aging_alert(self):
        today = fields.Date.context_today(self)
        alert_threshold = 180
        batches = self.search(
            [
                ("aging_days", ">=", alert_threshold),
                ("qty_available", ">", 0),
                "|",
                ("last_alert_date", "=", False),
                ("last_alert_date", "!=", today),
            ]
        )
        if not batches:
            return
        note_subtype = self.env.ref("mail.mt_note")
        for batch in batches:
            bucket_key = self._match_bucket(batch.aging_days)
            bucket_label = next(
                (b[3] for b in AGING_BUCKETS if b[0] == bucket_key),
                "陈化批次",
            )
            message = _(
                "批次 %(name)s 已陈化 %(days)s 天（分组：%(label)s），当前库存 %(qty)s。",
                name=batch.name,
                days=batch.aging_days,
                label=self.env._(bucket_label),
                qty=batch.qty_available,
            )
            batch.message_post(body=message, subtype_id=note_subtype.id)
            manager_group = self.env.ref("store_inventory.group_store_inventory_manager")
            managers = manager_group.users.filtered(lambda u: batch.company_id in u.company_ids)
            activity_type = self.env.ref("mail.mail_activity_data_warning")
            if managers:
                for user in managers:
                    batch.activity_schedule(
                        activity_type_id=activity_type.id,
                        user_id=user.id,
                        summary=_("陈化批次超期提醒"),
                        note=message,
                    )
            batch.last_alert_date = today
