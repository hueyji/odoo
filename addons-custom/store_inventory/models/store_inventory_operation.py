from datetime import timedelta

from odoo import Command, api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class StoreInventoryOperation(models.Model):
    _name = "store.inventory.operation"
    _description = "库存批次操作"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"

    name = fields.Char(string="操作编号", required=True, copy=False, default=lambda self: _("新建操作"))
    batch_id = fields.Many2one(
        "store.inventory.batch",
        string="陈化批次",
        required=True,
        ondelete="cascade",
        tracking=True,
        domain="[('company_id', 'in', user.company_ids.ids)]",
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
        string="所属公司",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="币种",
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    requested_qty = fields.Float(
        string="操作数量",
        digits="Product Unit of Measure",
        required=True,
        tracking=True,
    )
    counted_qty = fields.Float(
        string="盘点数量",
        digits="Product Unit of Measure",
        help="盘点操作时记录的实物数量。",
    )
    operation_type = fields.Selection(
        [
            ("incoming", "入库"),
            ("inventory", "盘点"),
            ("loss", "报损"),
            ("transfer", "调拨"),
        ],
        string="操作类型",
        required=True,
        tracking=True,
    )
    state = fields.Selection(
        [
            ("draft", "草稿"),
            ("submitted", "已提交"),
            ("approved", "已审批"),
            ("done", "已执行"),
            ("cancelled", "已取消"),
        ],
        string="状态",
        default="draft",
        tracking=True,
    )
    source_location_id = fields.Many2one(
        "stock.location",
        string="来源库位",
        domain="[('usage', 'in', ('internal', 'transit', 'production', 'vendor'))]",
        tracking=True,
    )
    dest_location_id = fields.Many2one(
        "stock.location",
        string="目标库位",
        domain="[('usage', 'in', ('internal', 'transit', 'production', 'customer'))]",
        tracking=True,
    )
    scrap_location_id = fields.Many2one(
        "stock.location",
        string="报损库位",
        domain="[('scrap_location', '=', True)]",
        tracking=True,
        help="报损操作时用于记录损耗的库位。",
    )
    scheduled_date = fields.Datetime(
        string="计划执行时间",
        default=lambda self: fields.Datetime.now() + timedelta(hours=1),
        tracking=True,
    )
    picking_id = fields.Many2one(
        "stock.picking",
        string="关联拣货单",
        readonly=True,
        copy=False,
    )
    approver_id = fields.Many2one(
        "res.users",
        string="审批人",
        readonly=True,
        copy=False,
    )
    note = fields.Text(string="备注")
    unit_cost = fields.Monetary(
        string="参考单价",
        currency_field="currency_id",
        help="用于与 Team D 对齐的成本同步字段，默认为批次进货价。",
    )

    _sql_constraints = [
        ("name_company_unique", "unique(name, company_id)", "操作编号在同一公司必须唯一。"),
    ]

    def _ensure_sequence(self):
        for rec in self:
            if rec.name == _("新建操作") or not rec.name:
                rec.name = self.env["ir.sequence"].next_by_code("store.inventory.operation") or _("新建操作")

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._ensure_sequence()
        for rec in records:
            if rec.batch_id.company_id != rec.company_id:
                rec.company_id = rec.batch_id.company_id
            if rec.company_id:
                rec.currency_id = rec.company_id.currency_id
            if rec.batch_id and not rec.unit_cost:
                rec.unit_cost = rec.batch_id.purchase_price
        return records

    def write(self, vals):
        res = super().write(vals)
        self._ensure_sequence()
        return res

    def _check_permissions(self):
        if not self.env.user.has_group("store_inventory.group_store_inventory_user"):
            raise UserError(_("当前用户无权执行该操作。"))

    def action_submit(self):
        self._check_permissions()
        for rec in self:
            if rec.state != "draft":
                raise UserError(_("仅草稿状态可以提交。"))
            rec._validate_fields_on_submit()
            rec.state = "submitted"
            rec.message_post(body=_("库存操作已提交审批。"))
            rec._schedule_manager_activity()
        return True

    def _schedule_manager_activity(self):
        activity_type = self.env.ref("mail.mail_activity_data_todo")
        manager_group = self.env.ref("store_inventory.group_store_inventory_manager")
        for rec in self:
            managers = manager_group.users.filtered(lambda u: rec.company_id in u.company_ids)
            if not managers:
                continue
            for user in managers:
                rec.activity_schedule(
                    activity_type_id=activity_type.id,
                    user_id=user.id,
                    summary=_("审批库存操作"),
                    note=_("请审批库存批次操作：%s") % rec.name,
                )

    def _validate_fields_on_submit(self):
        for rec in self:
            if rec.operation_type == "incoming":
                if not rec.dest_location_id and rec.batch_id.location_id:
                    rec.dest_location_id = rec.batch_id.location_id
                if not rec.dest_location_id:
                    raise ValidationError(_("入库操作必须指定目标库位。"))
            elif rec.operation_type == "transfer":
                if not rec.source_location_id and rec.batch_id.location_id:
                    rec.source_location_id = rec.batch_id.location_id
                if not rec.source_location_id or not rec.dest_location_id:
                    raise ValidationError(_("调拨操作必须同时指定来源与目标库位。"))
            elif rec.operation_type == "loss":
                if not rec.source_location_id and rec.batch_id.location_id:
                    rec.source_location_id = rec.batch_id.location_id
                if not rec.source_location_id:
                    raise ValidationError(_("报损操作必须指定来源库位。"))
                if not rec.scrap_location_id:
                    rec.scrap_location_id = self.env.ref("stock.location_scrapped")
            elif rec.operation_type == "inventory":
                if not rec.dest_location_id and rec.batch_id.location_id:
                    rec.dest_location_id = rec.batch_id.location_id
                if rec.counted_qty <= 0:
                    raise ValidationError(_("盘点操作必须填写盘点数量。"))
            if rec.requested_qty <= 0:
                raise ValidationError(_("操作数量必须大于 0。"))

    def action_approve(self):
        if not self.env.user.has_group("store_inventory.group_store_inventory_manager"):
            raise UserError(_("仅库存负责人可以审批。"))
        for rec in self:
            if rec.state != "submitted":
                raise UserError(_("仅已提交的操作可审批。"))
            rec._ensure_sequence()
            rec.approver_id = self.env.user
            rec.state = "approved"
            rec.message_post(body=_("库存操作已审批通过。"))
            if rec.operation_type in {"incoming", "transfer", "loss"}:
                rec._create_or_update_picking()
            rec.activity_feedback(self.env.ref("mail.mail_activity_data_todo").id)
        return True

    def _create_or_update_picking(self):
        StockPicking = self.env["stock.picking"]
        for rec in self:
            if rec.picking_id:
                continue
            warehouse = self._get_company_warehouse(rec.company_id)
            if not warehouse:
                raise UserError(_("请为公司配置仓库后再执行库存操作。"))
            if rec.operation_type == "incoming":
                picking_type = warehouse.in_type_id
                source_location = rec.source_location_id or picking_type.default_location_src_id
                dest_location = rec.dest_location_id or picking_type.default_location_dest_id
            elif rec.operation_type == "transfer":
                picking_type = warehouse.int_type_id
                source_location = rec.source_location_id or picking_type.default_location_src_id
                dest_location = rec.dest_location_id or picking_type.default_location_dest_id
            else:  # loss
                picking_type = warehouse.int_type_id
                source_location = rec.source_location_id or picking_type.default_location_src_id
                dest_location = rec.scrap_location_id or self.env.ref("stock.location_scrapped")
            if not picking_type:
                raise UserError(_("未配置相应的拣货类型，无法生成拣货单。"))

            picking_vals = {
                "origin": rec.name,
                "picking_type_id": picking_type.id,
                "company_id": rec.company_id.id,
                "scheduled_date": rec.scheduled_date,
                "location_id": source_location.id,
                "location_dest_id": dest_location.id,
                "move_ids_without_package": [
                    Command.create(
                        {
                            "name": "%s - %s" % (rec.batch_id.name, rec.operation_type),
                            "product_id": rec.product_id.id,
                            "product_uom_qty": rec.requested_qty,
                            "product_uom": rec.product_id.uom_id.id,
                            "company_id": rec.company_id.id,
                            "location_id": source_location.id,
                            "location_dest_id": dest_location.id,
                            "store_batch_id": rec.batch_id.id,
                            "store_reservation_token": rec.name,
                            "store_unit_cost": rec.unit_cost or rec.batch_id.purchase_price,
                        }
                    )
                ],
            }
            picking = StockPicking.create(picking_vals)
            rec.picking_id = picking

    def _get_company_warehouse(self, company):
        return (
            self.env["stock.warehouse"]
            .sudo()
            .search([("company_id", "=", company.id)], limit=1, order="id")
        )

    def action_execute(self):
        for rec in self:
            if rec.state not in {"approved"}:
                raise UserError(_("只有已审批的操作才可以执行。"))
            if rec.operation_type in {"incoming", "transfer", "loss"}:
                rec._execute_with_picking()
            else:
                rec._execute_inventory_adjustment()
            rec.state = "done"
            rec.message_post(body=_("库存操作已执行完成。"))
            rec.batch_id.message_post_with_view(
                "mail.message_origin_link",
                values={"self": rec.batch_id, "origin": rec},
                subtype_id=self.env.ref("mail.mt_note").id,
            )
        return True

    def _execute_with_picking(self):
        for rec in self:
            if not rec.picking_id:
                rec._create_or_update_picking()
            picking = rec.picking_id
            picking.action_confirm()
            picking.action_assign()
            # 填写 move line 的实际执行数量
            for move in picking.move_ids_without_package:
                for line in move.move_line_ids:
                    line.qty_done = rec.requested_qty
                if not move.move_line_ids:
                    move.write(
                        {
                            "quantity_done": rec.requested_qty,
                        }
                    )
            picking.with_context(store_inventory_batch_id=rec.batch_id.id)._action_done()
            rec._assign_quant_batch(picking)
            for move in picking.move_ids_without_package:
                if move.store_batch_id:
                    move.stock_valuation_layer_ids.write(
                        {
                            "store_batch_id": move.store_batch_id.id,
                            "store_reservation_token": rec.name,
                            "store_unit_cost": move.store_unit_cost or rec.unit_cost or rec.batch_id.purchase_price,
                        }
                    )
            if rec.operation_type == "incoming" and rec.batch_id.state == "draft":
                rec.batch_id.state = "in_stock"
            if rec.operation_type == "loss":
                rec.batch_id.message_post(body=_("批次发生报损，数量：%s") % rec.requested_qty)

    def _assign_quant_batch(self, picking):
        Quant = self.env["stock.quant"]
        for move in picking.move_ids_without_package:
            batch = move.store_batch_id
            if not batch:
                continue
            for line in move.move_line_ids:
                location = line.location_dest_id
                quants = Quant._gather(
                    product=move.product_id,
                    location=location,
                    lot_id=line.lot_id,
                    package_id=line.package_id,
                    owner_id=line.owner_id,
                    strict=False,
                )
                quants.sudo().write({"store_batch_id": batch.id})
            if not move.move_line_ids:
                location = move.location_dest_id
                quants = Quant._gather(
                    product=move.product_id,
                    location=location,
                    lot_id=False,
                    package_id=False,
                    owner_id=False,
                    strict=False,
                )
                quants.sudo().write({"store_batch_id": batch.id})

    def _execute_inventory_adjustment(self):
        Quant = self.env["stock.quant"]
        for rec in self:
            # 盘点时 counted_qty 为实物数量
            location = rec.dest_location_id or rec.batch_id.location_id
            if not location:
                raise UserError(_("盘点操作需要目标/原始库位信息。"))
            batch_quants = rec.batch_id.quant_ids.filtered(lambda q: q.location_id == location)
            current_qty = sum(batch_quants.mapped("quantity"))
            difference = rec.counted_qty - current_qty
            if difference == 0:
                continue
            Quant.with_context(store_inventory_batch_id=rec.batch_id.id)._update_available_quantity(
                rec.product_id,
                location,
                difference,
            )

    def action_cancel(self):
        for rec in self:
            if rec.state == "done":
                raise UserError(_("已执行的操作无法取消，可创建冲销操作。"))
            rec.state = "cancelled"
            if rec.picking_id and rec.picking_id.state not in {"done", "cancel"}:
                rec.picking_id.action_cancel()
            rec.activity_unlink()
            rec.message_post(body=_("库存操作已取消。"))
        return True

    def unlink(self):
        if any(rec.state == "done" for rec in self):
            raise UserError(_("已执行的库存操作不可删除。"))
        return super().unlink()
