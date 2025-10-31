from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class StoreInventoryTransfer(models.Model):
    _name = "store.inventory.transfer"
    _description = "库存调拨申请"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "request_date desc, id desc"
    _check_company_auto = True

    STATE_SELECTION = [
        ("draft", "草稿"),
        ("to_approve", "待审批"),
        ("approved", "已审批"),
        ("done", "已完成"),
        ("rejected", "已驳回"),
        ("cancel", "已取消"),
    ]

    name = fields.Char(
        string="调拨编号",
        required=True,
        readonly=True,
        copy=False,
        default=lambda self: _("新调拨"),
        tracking=True,
    )
    batch_id = fields.Many2one(
        "store.inventory.batch",
        string="来源批次",
        required=True,
        domain="[('state', 'in', ('in_stock', 'transit')), ('company_id', '=', company_id)]",
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="来源公司",
        related="batch_id.company_id",
        store=True,
        readonly=True,
    )
    source_company_id = fields.Many2one(
        "res.company",
        string="来源公司",
        related="batch_id.company_id",
        store=True,
        readonly=True,
    )
    target_company_id = fields.Many2one(
        "res.company",
        string="目标公司",
        required=True,
        tracking=True,
    )
    target_warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="目标仓库",
        domain="[('company_id', '=', target_company_id)]",
        tracking=True,
    )
    target_location_id = fields.Many2one(
        "stock.location",
        string="目标库位",
        domain="[('usage', '=', 'internal'), ('company_id', 'in', (False, target_company_id))]",
        tracking=True,
    )
    qty = fields.Float(
        string="调拨数量",
        required=True,
        digits="Product Unit of Measure",
        tracking=True,
    )
    unit_price = fields.Monetary(
        string="调拨成本",
        currency_field="currency_id",
        tracking=True,
        default=0.0,
        help="用于调拨财务结算的内部成本价格，默认为来源批次进货价。",
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="币种",
        required=True,
        default=lambda self: self.env.company.currency_id.id,
    )
    link_group_id = fields.Many2one(
        "store.link.group",
        string="互通组",
        readonly=True,
        tracking=True,
    )
    reason = fields.Char(string="申请理由", tracking=True)
    note = fields.Text(string="备注")
    requester_id = fields.Many2one(
        "res.users",
        string="申请人",
        default=lambda self: self.env.user.id,
        tracking=True,
        readonly=True,
    )
    approver_id = fields.Many2one(
        "res.users",
        string="审批人",
        tracking=True,
        readonly=True,
    )
    approval_date = fields.Datetime(string="审批时间", readonly=True)
    request_date = fields.Datetime(
        string="申请时间",
        default=fields.Datetime.now,
        readonly=True,
    )
    completion_date = fields.Datetime(string="完成时间", readonly=True)
    state = fields.Selection(
        selection=STATE_SELECTION,
        string="状态",
        default="draft",
        tracking=True,
    )
    out_move_id = fields.Many2one(
        "store.inventory.move",
        string="发出动作",
        readonly=True,
    )
    in_move_id = fields.Many2one(
        "store.inventory.move",
        string="接收动作",
        readonly=True,
    )
    new_batch_id = fields.Many2one(
        "store.inventory.batch",
        string="生成批次",
        readonly=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals.get("name") == _("新调拨"):
                vals["name"] = (
                    self.env["ir.sequence"].next_by_code("store.inventory.transfer")
                    or _("新调拨")
                )
            if not vals.get("currency_id"):
                vals["currency_id"] = self.env.company.currency_id.id
            if not vals.get("unit_price") and vals.get("batch_id"):
                batch = self.env["store.inventory.batch"].browse(vals["batch_id"])
                vals["unit_price"] = batch.purchase_price or 0.0
        return super().create(vals_list)

    def action_submit(self):
        for record in self:
            record._ensure_submit_ready()
            record.link_group_id = record._find_link_group()
            record.state = "to_approve"
            approval_user = record._get_approval_user()
            if approval_user:
                record.activity_schedule(
                    "mail.mail_activity_data_todo",
                    user_id=approval_user.id,
                    summary=_("库存调拨待审批"),
                    note=record.reason or record.note or "",
                )
        return True

    def action_approve(self):
        approval_user = self.env.user
        if not approval_user.has_group("stock.group_stock_manager"):
            raise AccessError(_("只有库存经理可以审批调拨。"))
        for record in self:
            if record.state != "to_approve":
                continue
            record.activity_unlink()
            record._perform_transfer()
            record.write(
                {
                    "state": "done",
                    "approver_id": approval_user.id,
                    "approval_date": fields.Datetime.now(),
                    "completion_date": fields.Datetime.now(),
                }
            )
            record.message_post(body=_("调拨已完成，库存与财务同步更新。"))
        return True

    def action_reject(self, note=None):
        approval_user = self.env.user
        if not approval_user.has_group("stock.group_stock_manager"):
            raise AccessError(_("只有库存经理可以驳回调拨。"))
        for record in self:
            if record.state != "to_approve":
                continue
            record.activity_unlink()
            record.write(
                {
                    "state": "rejected",
                    "approver_id": approval_user.id,
                    "approval_date": fields.Datetime.now(),
                    "note": note or record.note,
                }
            )
            record.message_post(body=_("调拨申请已驳回。"))
        return True

    def action_cancel(self):
        for record in self:
            if record.state != "draft":
                raise ValidationError(_("仅草稿状态可取消。"))
            record.state = "cancel"
        return True

    def action_reset_to_draft(self):
        for record in self:
            if record.state not in {"cancel", "rejected"}:
                raise ValidationError(_("仅已取消或驳回的调拨可重置为草稿。"))
            record.write({"state": "draft"})
        return True

    def _ensure_submit_ready(self):
        for record in self:
            if record.state != "draft":
                raise ValidationError(_("仅草稿状态可提交审批。"))
            if record.qty <= 0:
                raise ValidationError(_("调拨数量必须大于 0。"))
            if record.target_company_id == record.source_company_id:
                raise ValidationError(_("目标公司必须不同于来源公司。"))
            if record.qty > record.batch_id.qty_available:
                raise ValidationError(_("当前批次库存不足，无法发起调拨。"))

    def _get_approval_user(self):
        stock_manager_group = self.env.ref("stock.group_stock_manager", raise_if_not_found=False)
        if not stock_manager_group:
            return False
        managers = stock_manager_group.users.filtered(lambda u: self.env.company in u.company_ids)
        return managers[:1] or stock_manager_group.users[:1]

    def _find_link_group(self):
        self.ensure_one()
        Group = self.env["store.link.group"]
        domain = [
            ("state", "=", "active"),
            ("share_inventory", "=", True),
            ("member_company_ids", "in", self.source_company_id.id),
            ("member_company_ids", "in", self.target_company_id.id),
        ]
        group = Group.search(domain, limit=1)
        if not group:
            raise ValidationError(
                _("两家公司不在同一可共享库存的互通组内，无法调拨。")
            )
        return group

    def _perform_transfer(self):
        self.ensure_one()
        unit_price = self.unit_price or self.batch_id.purchase_price or 0.0

        out_move = self.env["store.inventory.move"].create(
            {
                "batch_id": self.batch_id.id,
                "move_type": "transfer_out",
                "quantity": self.qty,
                "unit_price": unit_price,
                "transfer_id": self.id,
                "note": self.reason or self.note or "",
            }
        )
        out_move.with_context(skip_approval_activity=True).action_submit()
        out_move.with_context(bypass_inventory_approval=True).action_approve()

        supplier_record = getattr(self.batch_id, "supplier_record_id", False)
        if supplier_record and getattr(supplier_record, "company_id", False) != self.target_company_id:
            supplier_record = False

        new_batch_vals = {
            "product_id": self.batch_id.product_id.id,
            "qty_initial": self.qty,
            "qty_available": self.qty,
            "aging_start_date": self.batch_id.aging_start_date,
            "purchase_price": unit_price,
            "supplier_id": self.batch_id.supplier_id.id,
            "company_id": self.target_company_id.id,
            "warehouse_id": self.target_warehouse_id.id,
            "location_id": self.target_location_id.id,
        }
        if self.env["store.inventory.batch"]._fields.get("supplier_record_id"):
            new_batch_vals["supplier_record_id"] = supplier_record.id if supplier_record else False
        target_batch = (
            self.env["store.inventory.batch"].with_company(self.target_company_id).sudo().create(new_batch_vals)
        )

        in_move = (
            self.env["store.inventory.move"].with_company(self.target_company_id).sudo().create(
                {
                    "batch_id": target_batch.id,
                    "move_type": "transfer_in",
                    "quantity": self.qty,
                    "unit_price": unit_price,
                    "transfer_id": self.id,
                    "note": self.reason or self.note or "",
                }
            )
        )
        in_move.with_context(skip_approval_activity=True).action_submit()
        in_move.with_context(bypass_inventory_approval=True).action_approve()

        self.write(
            {
                "out_move_id": out_move.id,
                "in_move_id": in_move.id,
                "new_batch_id": target_batch.id,
            }
        )
