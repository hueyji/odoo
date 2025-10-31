from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class StoreBarOrder(models.Model):
    _name = "store.bar.order"
    _description = "吧台订单"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"
    _check_company_auto = True

    STATE_SELECTION = [
        ("draft", "草稿"),
        ("confirmed", "已确认"),
        ("preparing", "调制中"),
        ("serving", "上酒中"),
        ("billing", "结账中"),
        ("done", "已完成"),
        ("cancelled", "已取消"),
    ]

    name = fields.Char(
        string="订单编号",
        required=True,
        copy=False,
        default=lambda self: _("新订单"),
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="公司",
        required=True,
        default=lambda self: self.env.company.id,
        index=True,
    )
    table_id = fields.Many2one(
        "store.bar.table",
        string="桌台",
        domain="[('company_id', '=', company_id)]",
        tracking=True,
    )
    state = fields.Selection(
        selection=STATE_SELECTION,
        string="状态",
        required=True,
        default="draft",
        tracking=True,
    )
    responsible_employee_id = fields.Many2one(
        "hr.employee",
        string="责任员工",
        domain="[('company_id', '=', company_id)]",
        tracking=True,
    )
    assistant_employee_ids = fields.Many2many(
        "hr.employee",
        "store_bar_order_employee_rel",
        "order_id",
        "employee_id",
        string="协同员工",
        domain="[('company_id', '=', company_id)]",
    )
    member_id = fields.Many2one(
        "res.partner",
        string="消费会员",
        tracking=True,
        domain="[('member_balance', '!=', False)]",
    )
    payment_channel_id = fields.Many2one(
        "store.finance.channel",
        string="结账渠道",
        domain="[('company_id', '=', company_id)]",
        tracking=True,
    )
    channel_type = fields.Selection(
        related="payment_channel_id.channel_type",
        string="渠道类型",
        store=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="币种",
        required=True,
        default=lambda self: self.env.company.currency_id.id,
    )
    line_ids = fields.One2many(
        "store.bar.order.line",
        "order_id",
        string="点单明细",
        copy=True,
    )
    amount_subtotal = fields.Monetary(
        string="小计",
        currency_field="currency_id",
        compute="_compute_amounts",
        store=True,
    )
    amount_service = fields.Monetary(
        string="服务费",
        currency_field="currency_id",
        default=0.0,
        tracking=True,
    )
    amount_total = fields.Monetary(
        string="合计金额",
        currency_field="currency_id",
        compute="_compute_amounts",
        store=True,
        tracking=True,
    )
    task_ids = fields.One2many(
        "store.bar.task",
        "order_id",
        string="调酒任务",
    )
    pending_task_count = fields.Integer(
        string="待完成任务数",
        compute="_compute_pending_task",
        store=False,
    )
    commission_log_ids = fields.One2many(
        "store.commission.log",
        "bar_order_id",
        string="提成日志",
    )
    commission_total_amount = fields.Monetary(
        string="提成合计",
        currency_field="currency_id",
        compute="_compute_commission_totals",
        store=False,
    )
    transaction_id = fields.Many2one(
        "store.account.transaction",
        string="财务流水",
        readonly=True,
        copy=False,
    )
    member_balance_log_id = fields.Many2one(
        "store.member.balance.log",
        string="储值日志",
        readonly=True,
        copy=False,
    )
    inventory_move_ids = fields.Many2many(
        "store.inventory.move",
        "store_bar_order_inventory_move_rel",
        "order_id",
        "move_id",
        string="库存动作",
        readonly=True,
        copy=False,
    )
    billing_requested_at = fields.Datetime(string="请求结账时间")
    closed_at = fields.Datetime(string="完成时间", tracking=True)
    note = fields.Text(string="备注")
    bus_channel_token = fields.Char(
        string="通知通道",
        help="用于前端实时推送，格式 `store.bar.order:<id>`。",
    )

    _sql_constraints = [
        ("name_company_unique", "unique(name, company_id)", "同一公司下订单编号必须唯一。"),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env.ref("store_bar.seq_store_bar_order", raise_if_not_found=False)
        for vals in vals_list:
            if (not vals.get("name")) or vals.get("name") in ("/", _("新订单")):
                vals["name"] = sequence.next_by_id() if sequence else _("新订单")
            if not vals.get("company_id") and vals.get("table_id"):
                table = self.env["store.bar.table"].browse(vals["table_id"])
                vals["company_id"] = table.company_id.id
            if not vals.get("responsible_employee_id"):
                employee = self.env.user.employee_id
                if employee and (not vals.get("company_id") or employee.company_id.id == vals.get("company_id")):
                    vals["responsible_employee_id"] = employee.id
            if vals.get("responsible_employee_id"):
                vals.setdefault("assistant_employee_ids", [(4, vals["responsible_employee_id"])])
        orders = super().create(vals_list)
        for order in orders:
            if not order.bus_channel_token:
                order.bus_channel_token = f"store.bar.order:{order.id}"
        return orders

    def write(self, vals):
        res = super().write(vals)
        if "responsible_employee_id" in vals:
            for order in self:
                if (
                    order.responsible_employee_id
                    and order.responsible_employee_id not in order.assistant_employee_ids
                ):
                    order.assistant_employee_ids = [(4, order.responsible_employee_id.id)]
        return res

    @api.depends("line_ids.price_subtotal", "amount_service")
    def _compute_amounts(self):
        for order in self:
            subtotal = sum(order.line_ids.mapped("price_subtotal"))
            order.amount_subtotal = subtotal
            order.amount_total = subtotal + (order.amount_service or 0.0)

    def _compute_pending_task(self):
        for order in self:
            order.pending_task_count = len(order.task_ids.filtered(lambda t: t.state in ("pending", "in_progress")))

    def _compute_commission_totals(self):
        for order in self:
            order.commission_total_amount = sum(order.commission_log_ids.mapped("commission_amount"))

    def _get_commission_participants(self):
        self.ensure_one()
        participants = self.responsible_employee_id | self.assistant_employee_ids
        return participants.filtered(lambda emp: emp.company_id == self.company_id or not emp.company_id)

    def action_confirm(self):
        for order in self:
            if order.state != "draft":
                continue
            if not order.line_ids:
                raise ValidationError(_("请先添加点单明细。"))
            order._ensure_table_available()
            order._validate_line_stock()
            order.write(
                {
                    "state": "preparing",
                }
            )
            if order.table_id:
                order.table_id.action_assign_order(order)
            order._create_bartender_tasks()
            order.message_post(body=_("订单已确认，正在调制。"))
        return True

    def action_set_serving(self):
        self.filtered(lambda o: o.state == "preparing").write({"state": "serving"})

    def action_request_bill(self):
        for order in self:
            if order.state not in {"serving", "preparing"}:
                continue
            order.write({"state": "billing", "billing_requested_at": fields.Datetime.now()})
            if order.table_id:
                order.table_id.action_mark_billing()
            order.message_post(body=_("顾客已请求结账，请及时处理。"))

    def action_reset_to_draft(self):
        for order in self:
            if order.state not in {"cancelled"}:
                raise ValidationError(_("仅已取消的订单可重置为草稿。"))
            order.write({"state": "draft"})

    def action_cancel(self, reason=None):
        for order in self:
            if order.state in {"done"}:
                raise ValidationError(_("已完成订单不可取消。"))
            order._cancel_tasks()
            order.write({"state": "cancelled"})
            if order.table_id and order.table_id.current_order_id == order:
                order.table_id.action_release()
            if reason:
                order.message_post(body=_("订单已取消：%s") % reason)
        return True

    def action_close(self):
        for order in self:
            if order.state not in {"billing", "serving"}:
                raise ValidationError(_("仅结账中或上酒中的订单可完成。"))
            order._ensure_tasks_done()
            order._apply_inventory_deduction()
            order._generate_commission_logs()
            order._create_finance_transaction()
            order._consume_member_balance_if_needed()
            order.write(
                {
                    "state": "done",
                    "closed_at": fields.Datetime.now(),
                }
            )
            if order.table_id:
                order.table_id.write({"last_checkout_at": order.closed_at})
                order.table_id.action_release()
            order.message_post(body=_("订单已结账完成。"))
        return True

    # --- 内部辅助逻辑 ---

    def _ensure_table_available(self):
        for order in self:
            table = order.table_id
            if not table:
                continue
            if table.company_id != order.company_id:
                raise ValidationError(_("订单与桌台必须属于同一公司。"))
            if table.state not in {"available", "reserved", "seated"}:
                raise ValidationError(_("桌台 %s 当前不可安排新订单。") % table.display_name)
            if (
                table.state == "seated"
                and table.current_order_id
                and table.current_order_id != order
            ):
                raise ValidationError(_("桌台 %s 已有进行中的订单。") % table.display_name)

    def _validate_line_stock(self):
        for order in self:
            for line in order.line_ids:
                line._check_stock_available()

    def _create_bartender_tasks(self):
        Task = self.env["store.bar.task"]
        sequence = 10
        for order in self:
            to_create = []
            for line in order.line_ids.filtered("requires_preparation"):
                to_create.append(
                    {
                        "name": line.product_id.display_name,
                        "order_id": order.id,
                        "order_line_id": line.id,
                        "table_id": order.table_id.id if order.table_id else False,
                        "company_id": order.company_id.id,
                        "sequence": sequence,
                        "responsible_employee_id": order.responsible_employee_id.id
                        if order.responsible_employee_id
                        else False,
                        "note": line.note or "",
                        "expected_commission_amount": line._estimate_commission_share(),
                    }
                )
                sequence += 10
            if to_create:
                Task.create(to_create)

    def _cancel_tasks(self):
        for order in self:
            order.task_ids.filtered(lambda t: t.state in {"pending", "in_progress"}).write({"state": "cancelled"})

    def _ensure_tasks_done(self):
        for order in self:
            pending = order.task_ids.filtered(lambda t: t.state not in {"done", "cancelled"})
            if pending:
                raise ValidationError(
                    _("仍有 %(count)s 条调酒任务未完成，请在工作台确认后再结账。") % {"count": len(pending)}
                )

    def _apply_inventory_deduction(self):
        InventoryMove = self.env["store.inventory.move"]
        for order in self:
            if not order.line_ids or order.inventory_move_ids:
                continue
            move_ids = []
            for line in order.line_ids.filtered(lambda l: l.batch_id and not l.inventory_move_id):
                move = InventoryMove.create(
                    {
                        "batch_id": line.batch_id.id,
                        "move_type": "outgoing",
                        "quantity": line.quantity,
                        "unit_price": line.batch_id.purchase_price or line.price_unit,
                        "company_id": order.company_id.id,
                        "date": fields.Datetime.now(),
                        "note": _("来自吧台订单 %s 的出库") % order.name,
                    }
                )
                move.action_confirm()
                line.inventory_move_id = move.id
                move_ids.append(move.id)
            if move_ids:
                move_names = ", ".join(self.env["store.inventory.move"].browse(move_ids).mapped("name"))
                order.message_post(body=_("已为订单生成库存出库单：%s") % move_names)
                order.write({"inventory_move_ids": [(4, move_id) for move_id in move_ids]})

    def _generate_commission_logs(self):
        Rule = self.env["store.commission.rule"]
        CommissionLog = self.env["store.commission.log"]
        for order in self:
            existing_drafts = order.commission_log_ids.filtered(lambda l: l.state == "draft")
            if existing_drafts:
                existing_drafts.unlink()
            rules = Rule.search(
                [
                    ("company_id", "=", order.company_id.id),
                    ("is_effective", "=", True),
                    ("state", "=", "active"),
                    ("active", "=", True),
                ],
                order="sequence asc, id desc",
            )
            if not rules:
                continue
            line_results = []
            order_results = []
            for rule in rules:
                if rule.rule_type == "order":
                    order_results.extend(rule.compute_order_commission(order))
                    continue
                for line in order.line_ids.filtered(lambda l: not l.display_type):
                    line_results.extend(rule.compute_line_commission(line))
            all_results = line_results + order_results
            if not all_results:
                continue

            grouped = defaultdict(lambda: {"amount": 0.0, "base": 0.0, "qty": 0.0, "line_id": False, "ladder": False})
            for vals in all_results:
                key = (
                    vals.get("employee_id"),
                    vals.get("rule_id"),
                    vals.get("sale_order_line_id"),
                    vals.get("ladder_line_id"),
                )
                grouped[key]["amount"] += vals.get("commission_amount", 0.0)
                grouped[key]["base"] = vals.get("base_amount") or grouped[key]["base"]
                grouped[key]["qty"] = vals.get("quantity") or grouped[key]["qty"]
                grouped[key]["line_id"] = vals.get("sale_order_line_id")
                grouped[key]["ladder"] = vals.get("ladder_line_id")

            to_create = []
            total_qty = sum(order.line_ids.filtered(lambda l: not l.display_type).mapped("quantity"))
            for key, data in grouped.items():
                employee_id, rule_id, line_id, ladder_line_id = key
                line = order.line_ids.filtered(lambda l: l.id == line_id)[:1] if line_id else False
                base_amount = data["base"] or (line.price_subtotal if line else order.amount_total)
                quantity = data["qty"] or (line.quantity if line else total_qty)
                to_create.append(
                    {
                        "bar_order_id": order.id,
                        "sale_order_id": False,
                        "sale_order_line_id": line.id if line else False,
                        "employee_id": employee_id,
                        "rule_id": rule_id,
                        "ladder_line_id": ladder_line_id,
                        "base_amount": base_amount,
                        "quantity": quantity,
                        "commission_amount": data["amount"],
                        "company_id": order.company_id.id,
                        "currency_id": order.currency_id.id,
                    }
                )
            if to_create:
                CommissionLog.create(to_create)

    def _create_finance_transaction(self):
        self.ensure_one()
        if self.transaction_id:
            return
        channel = self.payment_channel_id or self.env["store.account.transaction"]._find_default_channel(
            self.company_id.id
        )
        txn_vals = {
            "transaction_type": "sale",
            "amount": self.amount_total,
            "company_id": self.company_id.id,
            "currency_id": self.currency_id.id,
            "channel_id": channel.id if channel else False,
            "member_id": self.member_id.id if self.member_id else False,
            "reference": f"{self._name},{self.id}",
            "description": self.note or _("吧台订单结账"),
        }
        transaction = self.env["store.account.transaction"].create(txn_vals)
        transaction.action_confirm()
        self.transaction_id = transaction.id

    def _consume_member_balance_if_needed(self):
        self.ensure_one()
        if self.member_balance_log_id:
            return
        if self.channel_type != "stored_value":
            return
        if not self.member_id:
            raise ValidationError(_("请选择消费会员以使用储值余额支付。"))
        log = self.member_id.action_member_consume(
            self.amount_total,
            company=self.company_id,
            note=_("吧台订单 %s 结账") % self.name,
            reference=self,
        )
        self.member_balance_log_id = log.id

    def action_bus_notification(self, payload=None):
        """向前端推送订单状态，可被语音/视觉提醒订阅。"""
        Bus = self.env["bus.bus"]
        payload = payload or {}
        for order in self:
            channel = order.bus_channel_token or f"store.bar.order:{order.id}"
            Bus.sendone(channel, {"id": order.id, "state": order.state, **payload})

    def action_open_task_list(self):
        self.ensure_one()
        return {
            "name": _("调酒任务"),
            "type": "ir.actions.act_window",
            "res_model": "store.bar.task",
            "view_mode": "list,form",
            "domain": [("order_id", "=", self.id)],
            "context": {
                "default_order_id": self.id,
                "search_default_order_id": self.id,
            },
        }

    def action_preview_commission(self):
        self.ensure_one()
        Rule = self.env["store.commission.rule"]
        rules = Rule.search(
            [
                ("company_id", "=", self.company_id.id),
                ("is_effective", "=", True),
                ("state", "=", "active"),
                ("active", "=", True),
            ],
            order="sequence asc, id desc",
        )
        line_results = []
        order_results = []
        for rule in rules:
            if rule.rule_type == "order":
                order_results.extend(rule.compute_order_commission(self))
                continue
            for line in self.line_ids:
                line_results.extend(rule.compute_line_commission(line))
        results = line_results + order_results
        summary = defaultdict(float)
        for item in results:
            summary[item["employee_id"]] += item["commission_amount"]
        employees = self.env["hr.employee"].browse(summary.keys())
        return [
            {
                "employee_id": emp.id,
                "employee_name": emp.display_name,
                "commission_amount": self.currency_id.round(summary[emp.id]),
            }
            for emp in employees
        ]


class StoreBarOrderLine(models.Model):
    _name = "store.bar.order.line"
    _description = "吧台订单行"
    _order = "sequence, id"
    _check_company_auto = True

    order_id = fields.Many2one(
        "store.bar.order",
        string="订单",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(string="排序", default=10)
    display_type = fields.Selection(
        [
            ("line_section", "小计标题"),
            ("line_note", "备注"),
        ],
        string="显示类型",
    )
    product_id = fields.Many2one(
        "product.product",
        string="商品",
        domain="[('type', 'in', ('product', 'consu'))]",
    )
    product_uom_id = fields.Many2one(
        "uom.uom",
        string="单位",
        related="product_id.uom_id",
        readonly=True,
    )
    batch_id = fields.Many2one(
        "store.inventory.batch",
        string="出库批次",
        domain="[('product_id', '=', product_id), ('company_id', '=', company_id)]",
        required=False,
    )
    quantity = fields.Float(
        string="数量",
        required=True,
        default=1.0,
        digits="Product Unit of Measure",
    )
    price_unit = fields.Monetary(
        string="单价",
        currency_field="currency_id",
        required=True,
    )
    price_subtotal = fields.Monetary(
        string="小计",
        currency_field="currency_id",
        compute="_compute_subtotal",
        store=True,
    )
    currency_id = fields.Many2one(
        related="order_id.currency_id",
        string="币种",
        store=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        related="order_id.company_id",
        string="公司",
        store=True,
        readonly=True,
    )
    requires_preparation = fields.Boolean(
        string="需要调制",
        default=True,
        help="标记该商品是否需要调酒师准备。",
    )
    prep_state = fields.Selection(
        [
            ("pending", "待调制"),
            ("in_progress", "调制中"),
            ("done", "已完成"),
            ("cancelled", "已取消"),
        ],
        string="调制状态",
        default="pending",
    )
    note = fields.Char(string="备注")
    participant_employee_ids = fields.Many2many(
        "hr.employee",
        "store_bar_order_line_employee_rel",
        "line_id",
        "employee_id",
        string="参与员工",
        domain="[('company_id', '=', company_id)]",
    )
    inventory_move_id = fields.Many2one(
        "store.inventory.move",
        string="关联库存动作",
        readonly=True,
        copy=False,
    )

    @api.onchange("product_id")
    def _onchange_product_id_setup_price(self):
        if self.product_id:
            self.price_unit = self.product_id.lst_price
            if self.product_id.detailed_type == "service":
                self.requires_preparation = False

    @api.depends("quantity", "price_unit")
    def _compute_subtotal(self):
        for line in self:
            line.price_subtotal = line.quantity * line.price_unit

    @api.constrains("quantity")
    def _check_quantity(self):
        for line in self:
            if line.display_type:
                continue
            if line.quantity <= 0:
                raise ValidationError(_("数量必须大于 0。"))

    @api.constrains("display_type", "product_id")
    def _check_product_required(self):
        for line in self:
            if not line.display_type and not line.product_id:
                raise ValidationError(_("请选择具体商品。"))

    def _get_commission_participants(self):
        self.ensure_one()
        employees = self.participant_employee_ids
        if not employees and self.order_id:
            employees = self.order_id._get_commission_participants()
        return employees.filtered(lambda emp: emp.company_id == self.company_id or not emp.company_id)

    def _check_stock_available(self):
        for line in self:
            if line.display_type:
                continue
            if not line.batch_id:
                continue
            if line.batch_id.company_id != line.company_id:
                raise ValidationError(_("批次与订单行不属于同一公司。"))
            if line.batch_id.product_id != line.product_id:
                raise ValidationError(_("批次商品与订单行商品不一致。"))
            if line.quantity > line.batch_id.qty_available:
                raise ValidationError(
                    _("批次 %(batch)s 库存不足，剩余 %(qty)s。")
                    % {"batch": line.batch_id.display_name, "qty": line.batch_id.qty_available}
                )

    def action_mark_preparing(self):
        self.filtered(lambda l: l.requires_preparation).write({"prep_state": "in_progress"})

    def action_mark_ready(self):
        self.filtered(lambda l: l.requires_preparation).write({"prep_state": "done"})

    def _estimate_commission_share(self):
        self.ensure_one()
        order = self.order_id
        Rule = self.env["store.commission.rule"]
        rules = Rule.search(
            [
                ("company_id", "=", order.company_id.id),
                ("is_effective", "=", True),
                ("state", "=", "active"),
                ("active", "=", True),
            ],
            order="sequence asc, id desc",
        )
        amount = 0.0
        for rule in rules:
            if rule.rule_type == "order":
                continue
            for vals in rule.compute_line_commission(self):
                amount += vals.get("commission_amount", 0.0)
        return order.currency_id.round(amount)


class StoreBarTask(models.Model):
    _name = "store.bar.task"
    _description = "调酒任务"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "state, sequence, id"
    _check_company_auto = True

    STATE_SELECTION = [
        ("pending", "待调制"),
        ("in_progress", "调制中"),
        ("done", "已完成"),
        ("cancelled", "已取消"),
    ]

    name = fields.Char(string="任务名称", required=True, default=lambda self: _("新任务"))
    order_id = fields.Many2one(
        "store.bar.order",
        string="关联订单",
        ondelete="cascade",
        required=True,
        index=True,
    )
    order_line_id = fields.Many2one(
        "store.bar.order.line",
        string="订单行",
        ondelete="set null",
    )
    table_id = fields.Many2one(
        "store.bar.table",
        string="桌台",
        related="order_id.table_id",
        store=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="公司",
        related="order_id.company_id",
        store=True,
        readonly=True,
    )
    state = fields.Selection(
        selection=STATE_SELECTION,
        string="状态",
        default="pending",
        tracking=True,
    )
    sequence = fields.Integer(string="顺序", default=10)
    responsible_employee_id = fields.Many2one(
        "hr.employee",
        string="责任员工",
        tracking=True,
        domain="[('company_id', '=', company_id)]",
    )
    assigned_employee_id = fields.Many2one(
        "hr.employee",
        string="当前执行人",
        tracking=True,
        domain="[('company_id', '=', company_id)]",
    )
    start_time = fields.Datetime(string="开始时间")
    complete_time = fields.Datetime(string="完成时间")
    expected_commission_amount = fields.Monetary(
        string="预计提成",
        currency_field="currency_id",
        readonly=True,
    )
    currency_id = fields.Many2one(
        related="order_id.currency_id",
        string="币种",
        store=True,
        readonly=True,
    )
    note = fields.Char(string="备注")

    def action_start(self):
        for task in self.filtered(lambda t: t.state in {"pending", "in_progress"}):
            task.write(
                {
                    "state": "in_progress",
                    "start_time": task.start_time or fields.Datetime.now(),
                    "assigned_employee_id": task.assigned_employee_id
                    or self.env.user.employee_id.id,
                }
            )
            if task.order_line_id:
                task.order_line_id.action_mark_preparing()

    def action_done(self):
        for task in self.filtered(lambda t: t.state in {"pending", "in_progress"}):
            task.write({"state": "done", "complete_time": fields.Datetime.now()})
            if task.order_line_id:
                task.order_line_id.action_mark_ready()
            task.order_id.action_bus_notification({"task_id": task.id, "task_state": "done"})

    def action_reset(self):
        for task in self:
            task.write({"state": "pending", "start_time": False, "complete_time": False})
            if task.order_line_id:
                task.order_line_id.write({"prep_state": "pending"})

    def action_cancel(self):
        for task in self.filtered(lambda t: t.state != "done"):
            task.write({"state": "cancelled"})
            if task.order_line_id:
                task.order_line_id.write({"prep_state": "cancelled"})
