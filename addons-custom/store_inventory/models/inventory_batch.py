from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class StoreInventoryBatch(models.Model):
    _name = "store.inventory.batch"
    _description = "门店库存批次"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "aging_start_date desc, id desc"
    _check_company_auto = True

    STATE_SELECTION = [
        ("draft", "草稿"),
        ("in_stock", "在库"),
        ("transit", "调拨中"),
        ("lost", "报损"),
        ("sold_out", "售罄"),
    ]

    AGING_STAGE_SELECTION = [
        ("lt_30", "<30 天"),
        ("31_90", "31-90 天"),
        ("91_180", "91-180 天"),
        ("181_365", "181-365 天"),
        ("gt_365", ">365 天"),
    ]

    AGING_STAGE_COLOR = {
        "lt_30": 10,
        "31_90": 2,
        "91_180": 3,
        "181_365": 6,
        "gt_365": 1,
    }

    name = fields.Char(
        string="批次编号",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _("新批次"),
        tracking=True,
    )
    product_id = fields.Many2one(
        "product.product",
        string="商品",
        required=True,
        tracking=True,
        domain="[('type', 'in', ('product', 'consu'))]",
    )
    product_uom_id = fields.Many2one(
        "uom.uom",
        string="计量单位",
        related="product_id.uom_id",
        readonly=True,
    )
    supplier_id = fields.Many2one(
        "res.partner",
        string="供应商",
        domain="[('is_company', '=', True)]",
        tracking=True,
        help="关联本批次的进货供应商。",
    )
    purchase_price = fields.Monetary(
        string="进货单价",
        tracking=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="币种",
        required=True,
        default=lambda self: self.env.company.currency_id.id,
    )
    qty_initial = fields.Float(
        string="初始数量",
        required=True,
        tracking=True,
        digits="Product Unit of Measure",
    )
    qty_available = fields.Float(
        string="当前库存",
        tracking=True,
        digits="Product Unit of Measure",
        help="当前批次剩余可售数量。",
    )
    location_id = fields.Many2one(
        "stock.location",
        string="所在库位",
        tracking=True,
        domain="[('usage', '=', 'internal'), ('company_id', 'in', (False, company_id))]",
    )
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="所属仓库",
        tracking=True,
        domain="[('company_id', 'in', (False, company_id))]",
    )
    aging_start_date = fields.Date(
        string="陈化开始日期",
        required=True,
        tracking=True,
        default=fields.Date.context_today,
    )
    aging_days = fields.Integer(
        string="已陈化天数",
        compute="_compute_aging_fields",
        store=True,
    )
    aging_stage = fields.Selection(
        selection=AGING_STAGE_SELECTION,
        string="陈化分层",
        compute="_compute_aging_fields",
        store=True,
    )
    aging_stage_label = fields.Char(
        string="陈化阶段",
        compute="_compute_aging_fields",
        store=True,
    )
    color = fields.Integer(
        string="标记色",
        compute="_compute_aging_fields",
        store=True,
    )
    attention_flag = fields.Boolean(
        string="关注批次",
        tracking=True,
        help="手动标记需要额外关注的批次，例如临期或需加快售卖。",
    )
    state = fields.Selection(
        selection=STATE_SELECTION,
        string="状态",
        default="draft",
        tracking=True,
    )
    note = fields.Text(string="备注")
    company_id = fields.Many2one(
        "res.company",
        string="公司",
        required=True,
        default=lambda self: self.env.company.id,
    )
    move_ids = fields.One2many(
        "store.inventory.move",
        "batch_id",
        string="库存动作",
    )
    last_move_id = fields.Many2one(
        "store.inventory.move",
        string="最近动作",
        compute="_compute_last_move",
        store=True,
    )
    # 供应商档案关联（继承自store_supplier模块）
    supplier_record_id = fields.Many2one(
        "store.supplier",
        string="供应商档案",
        tracking=True,
        help="与门店供应商档案建立关联，便于统计采购表现。",
    )

    @api.onchange("supplier_record_id")
    def _onchange_supplier_record_id(self):
        for record in self:
            if record.supplier_record_id:
                record.supplier_id = record.supplier_record_id.partner_id

    def write(self, vals):
        res = super().write(vals)
        if "supplier_record_id" in vals:
            for record in self:
                if record.supplier_record_id and record.supplier_record_id.partner_id:
                    record.supplier_id = record.supplier_record_id.partner_id
        return res

    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "unique_batch_name_company",
            "unique(name, company_id)",
            "同一公司下批次编号不可重复。",
        )
    ]

    @api.constrains("qty_initial", "qty_available")
    def _check_quantities(self):
        for record in self:
            if record.qty_initial <= 0:
                raise ValidationError(_("初始数量必须大于 0。"))
            if record.qty_available < 0:
                raise ValidationError(_("当前库存不能为负数。"))

    @api.constrains("aging_start_date")
    def _check_aging_start(self):
        today = date.today()
        for record in self:
            if record.aging_start_date and record.aging_start_date > today:
                raise ValidationError(_("陈化开始日期不能晚于今天。"))

    @api.depends("aging_start_date", "state")
    def _compute_aging_fields(self):
        today = date.today()
        stage_dict = dict(self.AGING_STAGE_SELECTION)
        for record in self:
            if record.aging_start_date and record.state not in {"draft", "lost"}:
                delta = (today - record.aging_start_date).days
                record.aging_days = max(delta, 0)
            else:
                record.aging_days = 0
            stage = record._categorize_aging(record.aging_days)
            record.aging_stage = stage
            record.aging_stage_label = stage_dict.get(stage)
            record.color = self.AGING_STAGE_COLOR.get(stage, 0)

    @api.depends("move_ids.state", "move_ids.date")
    def _compute_last_move(self):
        for record in self:
            done_moves = record.move_ids.filtered(lambda m: m.state == "done")
            ordered = done_moves.sorted(
                key=lambda m: m.date or fields.Datetime.from_string("1970-01-01"),
                reverse=True,
            )
            record.last_move_id = ordered[:1]

    def _categorize_aging(self, aging_days):
        if aging_days < 30:
            return "lt_30"
        if aging_days <= 90:
            return "31_90"
        if aging_days <= 180:
            return "91_180"
        if aging_days <= 365:
            return "181_365"
        return "gt_365"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals.get("name") == _("新批次"):
                vals["name"] = (
                    self.env["ir.sequence"].next_by_code("store.inventory.batch")
                    or _("新批次")
                )
            if "company_id" not in vals:
                vals["company_id"] = self.env.company.id
            if "currency_id" not in vals:
                vals["currency_id"] = self.env.company.currency_id.id
            if "qty_available" not in vals and vals.get("qty_initial"):
                vals["qty_available"] = vals["qty_initial"]
        batches = super().create(vals_list)
        for batch in batches:
            if batch.state == "draft":
                batch.action_mark_in_stock()
        return batches

    def write(self, vals):
        return super().write(vals)

    def action_mark_in_stock(self):
        self.write({"state": "in_stock"})

    def action_mark_transit(self):
        self.write({"state": "transit"})

    def action_mark_lost(self):
        self.write({"state": "lost"})

    def action_mark_sold_out(self):
        self.write({"state": "sold_out", "qty_available": 0})

    def action_toggle_attention(self):
        for record in self:
            record.attention_flag = not record.attention_flag

    def action_view_moves(self):
        self.ensure_one()
        action = self.env.ref("store_inventory.action_store_inventory_move").read()[0]
        action.setdefault("domain", [])
        action["domain"] += [("batch_id", "=", self.id)]
        action["context"] = dict(self.env.context, default_batch_id=self.id)
        return action

    def action_open_board(self):
        return {
            "type": "ir.actions.client",
            "tag": "store_inventory_batch_board",
            "name": "库存陈化看板",
        }

    @api.model
    def cron_update_aging(self):
        batches = self.search([
            ("state", "in", ["in_stock", "transit"]),
            ("active", "=", True),
        ])
        batches._compute_aging_fields()
        return True

    @api.model
    def action_get_aging_metrics(self):
        stage_dict = dict(self.AGING_STAGE_SELECTION)
        metrics = []
        for stage, label in self.AGING_STAGE_SELECTION:
            domain = [
                ("state", "in", ["in_stock", "transit"]),
                ("aging_stage", "=", stage),
            ]
            stage_batches = self.search(domain)
            qty = sum(stage_batches.mapped("qty_available"))
            attention = stage_batches.filtered("attention_flag")
            metrics.append(
                {
                    "stage": stage,
                    "label": label,
                    "count": len(stage_batches),
                    "qty": qty,
                    "color": self.AGING_STAGE_COLOR.get(stage, 0),
                    "attention_count": len(attention),
                }
            )
        return {
            "metrics": metrics,
            "generated_at": fields.Datetime.now(),
        }

    def action_export_csv(self):
        active_ids = self.env.context.get("active_ids") or self.ids
        url = "/store_inventory/batches/export"
        if active_ids:
            joined = ",".join(str(batch_id) for batch_id in active_ids)
            url = f"{url}?ids={joined}"
        return {
            "type": "ir.actions.act_url",
            "url": url,
            "target": "self",
        }
