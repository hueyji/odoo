from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class StoreBarTable(models.Model):
    _name = "store.bar.table"
    _description = "门店桌台"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _check_company_auto = True

    name = fields.Char(string="桌台名称", required=True, tracking=True)
    company_id = fields.Many2one(
        "res.company",
        string="所属公司",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    capacity = fields.Integer(string="可容纳人数", default=2)
    state = fields.Selection(
        [
            ("free", "空闲"),
            ("reserved", "已预定"),
            ("occupied", "使用中"),
            ("billing", "结账中"),
        ],
        string="状态",
        default="free",
        tracking=True,
        index=True,
    )
    current_order_id = fields.Many2one(
        "store.bar.order",
        string="当前订单",
        readonly=True,
        copy=False,
    )
    order_ids = fields.One2many(
        "store.bar.order",
        "table_id",
        string="历史订单",
    )
    reservation_partner_id = fields.Many2one(
        "res.partner",
        string="预定会员",
        domain="['|', ('company_id', '=', company_id), ('company_id', '=', False)]",
    )
    reservation_phone = fields.Char(string="联系电话")
    reservation_datetime = fields.Datetime(string="预定时间")
    note = fields.Text(string="备注")
    active = fields.Boolean(default=True, string="启用")

    @api.constrains("current_order_id", "state")
    def _check_current_order_state(self):
        for table in self:
            if table.current_order_id and table.state not in ("occupied", "billing"):
                raise ValidationError(_("有订单关联时桌台状态必须为“使用中”或“结账中”。"))

    def action_mark_free(self):
        for table in self:
            table.write(
                {
                    "state": "free",
                    "current_order_id": False,
                    "reservation_partner_id": False,
                    "reservation_phone": False,
                    "reservation_datetime": False,
                }
            )
        return True

    def action_mark_reserved(self, partner=None, phone=None, reserve_dt=None):
        for table in self:
            vals = {"state": "reserved"}
            if partner:
                vals["reservation_partner_id"] = partner.id
            if phone:
                vals["reservation_phone"] = phone
            if reserve_dt:
                vals["reservation_datetime"] = reserve_dt
            table.write(vals)
        return True

    def action_attach_order(self, order):
        self.ensure_one()
        if self.current_order_id and self.current_order_id != order:
            raise ValidationError(_("桌台已有进行中的订单，无法重复分配。"))
        self.write({"current_order_id": order.id, "state": "occupied"})
        return True

    def action_detach_order(self, order):
        self.ensure_one()
        if self.current_order_id == order:
            next_state = "reserved" if (self.reservation_partner_id or self.reservation_phone) else "free"
            self.write({"current_order_id": False, "state": next_state})
        return True
