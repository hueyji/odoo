from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class StoreInventoryMove(models.Model):
    _name = "store.inventory.move"
    _description = "库存动作"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"
    _check_company_auto = True

    MOVE_TYPE_SELECTION = [
        ("incoming", "入库"),
        ("outgoing", "出库"),
        ("adjustment", "盘点调整"),
        ("scrap", "报损"),
        ("transfer_out", "调拨发出"),
        ("transfer_in", "调拨接收"),
    ]

    STATE_SELECTION = [
        ("draft", "草稿"),
        ("to_approve", "待审批"),
        ("done", "已完成"),
        ("rejected", "已驳回"),
        ("cancel", "已取消"),
    ]

    name = fields.Char(
        string="动作编号",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _("新动作"),
        tracking=True,
    )
    date = fields.Datetime(
        string="操作时间",
        required=True,
        default=fields.Datetime.now,
        tracking=True,
    )
    move_type = fields.Selection(
        selection=MOVE_TYPE_SELECTION,
        string="动作类型",
        required=True,
        default="incoming",
        tracking=True,
    )
    batch_id = fields.Many2one(
        "store.inventory.batch",
        string="关联批次",
        required=True,
        tracking=True,
        domain="[('company_id', '=', company_id)]",
    )
    product_id = fields.Many2one(
        "product.product",
        string="商品",
        related="batch_id.product_id",
        store=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="公司",
        required=True,
        default=lambda self: self.env.company.id,
    )
    quantity = fields.Float(
        string="数量",
        required=True,
        digits="Product Unit of Measure",
        tracking=True,
    )
    unit_price = fields.Monetary(
        string="单价",
        currency_field="currency_id",
        required=True,
        tracking=True,
    )
    amount_total = fields.Monetary(
        string="金额",
        currency_field="currency_id",
        compute="_compute_amount_total",
        store=True,
        tracking=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="币种",
        required=True,
        default=lambda self: self.env.company.currency_id.id,
    )
    state = fields.Selection(
        selection=STATE_SELECTION,
        string="状态",
        default="draft",
        tracking=True,
    )
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
    approval_date = fields.Datetime(
        string="审批时间",
        readonly=True,
    )
    approval_note = fields.Text(string="审批备注")
    reason = fields.Char(string="原因")
    transaction_id = fields.Many2one(
        "store.account.transaction",
        string="财务流水",
        readonly=True,
        copy=False,
    )
    transfer_id = fields.Many2one(
        "store.inventory.transfer",
        string="调拨单",
        index=True,
    )
    note = fields.Text(string="备注")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals.get("name") == _("新动作"):
                vals["name"] = (
                    self.env["ir.sequence"].next_by_code("store.inventory.move")
                    or _("新动作")
                )
            if not vals.get("company_id") and vals.get("batch_id"):
                batch = self.env["store.inventory.batch"].browse(vals["batch_id"])
                if batch:
                    vals["company_id"] = batch.company_id.id
            if not vals.get("currency_id"):
                vals["currency_id"] = self.env.company.currency_id.id
            if not vals.get("unit_price") and vals.get("batch_id"):
                batch = self.env["store.inventory.batch"].browse(vals["batch_id"])
                vals["unit_price"] = batch.purchase_price or 0.0
            if not vals.get("requester_id"):
                vals["requester_id"] = self.env.user.id
        return super().create(vals_list)

    @api.depends("quantity", "unit_price")
    def _compute_amount_total(self):
        for record in self:
            record.amount_total = record.quantity * record.unit_price

    def action_submit(self):
        for record in self:
            if record.state != "draft":
                continue
            if record.quantity <= 0:
                raise ValidationError(_("数量必须大于 0。"))
            record.state = "to_approve"
            approval_user = record._get_approval_user()
            if approval_user and not self.env.context.get("skip_approval_activity"):
                record.activity_schedule(
                    "mail.mail_activity_data_todo",
                    user_id=approval_user.id,
                    summary=_("库存动作待审批"),
                    note=record.note or "",
                )
        return True

    def action_approve(self):
        approval_user = self.env.user
        if not (self.env.context.get("bypass_inventory_approval") or approval_user.has_group("stock.group_stock_manager")):
            raise AccessError(_("只有库存经理可以审批库存动作。"))
        for record in self:
            if record.state != "to_approve":
                continue
            record._validate_before_done()
            record.activity_unlink()
            record._apply_inventory_impact()
            transaction = record._create_finance_transaction()
            record.write(
                {
                    "state": "done",
                    "approver_id": approval_user.id,
                    "approval_date": fields.Datetime.now(),
                    "transaction_id": transaction.id if transaction else False,
                }
            )
            record.message_post(
                body=_(
                    "库存动作已审批，生成财务流水 %(name)s。",
                    name=transaction.name if transaction else _("无"),
                )
            )
        return True

    def action_reject(self, approval_note=None):
        approval_user = self.env.user
        if not (self.env.context.get("bypass_inventory_approval") or approval_user.has_group("stock.group_stock_manager")):
            raise AccessError(_("只有库存经理可以驳回库存动作。"))
        for record in self:
            if record.state != "to_approve":
                continue
            record.activity_unlink()
            record.write(
                {
                    "state": "rejected",
                    "approver_id": approval_user.id,
                    "approval_date": fields.Datetime.now(),
                    "approval_note": approval_note,
                }
            )
            record.message_post(body=_("库存动作已被驳回。"))
        return True

    def action_reset_to_draft(self):
        for record in self:
            if record.state not in {"rejected", "cancel"}:
                raise ValidationError(_("仅驳回或取消的动作可重置为草稿。"))
            record.write({"state": "draft", "approval_note": False})
        return True

    def action_cancel(self):
        for record in self:
            if record.state != "draft":
                raise ValidationError(_("仅草稿状态可取消。"))
            record.state = "cancel"
        return True

    def _get_approval_user(self):
        stock_manager_group = self.env.ref("stock.group_stock_manager", raise_if_not_found=False)
        if not stock_manager_group:
            return False
        managers = stock_manager_group.users.filtered(lambda u: self.env.company in u.company_ids)
        return managers[:1] or stock_manager_group.users[:1]

    def _validate_before_done(self):
        for record in self:
            if record.quantity <= 0:
                raise ValidationError(_("数量必须大于 0。"))
            if record.move_type in {"outgoing", "scrap", "transfer_out"} and record.quantity > record.batch_id.qty_available:
                raise ValidationError(_("当前批次库存不足，无法执行该操作。"))

    def _apply_inventory_impact(self):
        self.ensure_one()
        batch = self.batch_id
        if self.move_type in {"incoming", "transfer_in"}:
            batch.qty_available += self.quantity
            if batch.state in {"draft", "transit"}:
                batch.action_mark_in_stock()
        elif self.move_type in {"outgoing", "scrap", "transfer_out"}:
            batch.qty_available -= self.quantity
            if batch.qty_available <= 0:
                batch.action_mark_sold_out()
            elif self.move_type == "transfer_out":
                batch.action_mark_transit()
        elif self.move_type == "adjustment":
            batch.qty_available = self.quantity
            if batch.state == "draft":
                batch.action_mark_in_stock()
        batch.message_post(
            body=_(
                "库存动作 %(move)s 更新库存，当前库存 %(qty)s",
                move=self.name,
                qty=batch.qty_available,
            )
        )

    def _create_finance_transaction(self):
        self.ensure_one()
        if self.move_type == "adjustment":
            return False

        transaction_model = self.env["store.account.transaction"]
        channel = transaction_model._find_default_channel(
            self.company_id.id,
            preferred_type="internal",
            allow_create=True,
        )
        transaction_vals = {
            "transaction_type": self._map_transaction_type(),
            "amount": self._get_finance_amount(),
            "company_id": self.company_id.id,
            "currency_id": self.currency_id.id,
            "reference": "%s,%s" % (self._name, self.id),
            "description": self.note or "",
        }
        if channel:
            transaction_vals["channel_id"] = channel.id
        if self.transfer_id and self.transfer_id.link_group_id:
            transaction_vals["link_group_id"] = self.transfer_id.link_group_id.id
        transaction = transaction_model.create(transaction_vals)
        transaction.action_confirm()
        return transaction

    def _map_transaction_type(self):
        self.ensure_one()
        if self.move_type == "incoming":
            return "purchase"
        if self.move_type == "outgoing":
            return "sale"
        if self.move_type == "scrap":
            return "inventory_loss"
        if self.move_type in {"transfer_in", "transfer_out"}:
            return "transfer"
        return "other"

    def _get_finance_amount(self):
        self.ensure_one()
        amount = abs(self.amount_total)
        if self.move_type in {"incoming", "scrap", "transfer_out"}:
            return -amount
        return amount
