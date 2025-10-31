from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class StoreCommissionLog(models.Model):
    _name = "store.commission.log"
    _description = "提成日志"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"
    _check_company_auto = True

    STATE_SELECTION = [
        ("draft", "草稿"),
        ("confirmed", "已确认"),
        ("refunded", "已回滚"),
        ("cancelled", "已取消"),
    ]

    name = fields.Char(
        string="编号",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _("新提成"),
    )
    date = fields.Datetime(
        string="记录时间",
        default=fields.Datetime.now,
        required=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="公司",
        required=True,
        default=lambda self: self.env.company.id,
        index=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="币种",
        required=True,
        default=lambda self: self.env.company.currency_id.id,
    )
    sale_order_id = fields.Many2one(
        "sale.order",
        string="销售订单",
        ondelete="set null",
        index=True,
    )
    sale_order_line_id = fields.Many2one(
        "sale.order.line",
        string="订单行",
        ondelete="set null",
        index=True,
    )
    employee_id = fields.Many2one(
        "hr.employee",
        string="员工",
        required=True,
        index=True,
    )
    employee_job_id = fields.Many2one(
        "hr.job",
        string="所属职务",
        related="employee_id.job_id",
        store=True,
        readonly=True,
    )
    rule_id = fields.Many2one(
        "store.commission.rule",
        string="提成规则",
        required=True,
        ondelete="restrict",
    )
    ladder_line_id = fields.Many2one(
        "store.commission.rule.ladder",
        string="阶梯",
        ondelete="set null",
    )
    base_amount = fields.Monetary(string="基准金额", tracking=True)
    quantity = fields.Float(string="数量", digits="Product Unit of Measure", tracking=True)
    commission_amount = fields.Monetary(string="提成金额", tracking=True)
    state = fields.Selection(
        selection=STATE_SELECTION,
        string="状态",
        default="draft",
        tracking=True,
    )
    adjustment_reason = fields.Text(string="调整原因")
    approved_by_id = fields.Many2one("res.users", string="审核人")
    transaction_id = fields.Many2one(
        "store.account.transaction",
        string="财务流水",
        readonly=True,
        copy=False,
    )
    is_refund = fields.Boolean(string="是否冲减", default=False)

    _sql_constraints = [
        (
            "commission_amount_not_zero",
            "CHECK(commission_amount IS NULL OR commission_amount != 0)",
            "提成金额不能为 0。",
        )
    ]

    @api.model
    def create(self, vals):
        if not vals.get("name") or vals.get("name") == _("新提成"):
            vals["name"] = self.env["ir.sequence"].next_by_code("store.commission.log") or _("新提成")
        if vals.get("sale_order_id") and not vals.get("company_id"):
            order = self.env["sale.order"].browse(vals["sale_order_id"])
            vals["company_id"] = order.company_id.id
            vals["currency_id"] = order.currency_id.id
        return super().create(vals)

    def action_confirm(self):
        for log in self:
            if log.state != "draft":
                continue
            if not log.commission_amount:
                raise ValidationError(_("提成金额必须填写。"))
            transaction = log._create_finance_transaction()
            write_vals = {"state": "confirmed", "transaction_id": transaction.id if transaction else False}
            if transaction:
                write_vals["approved_by_id"] = self.env.user.id
            log.write(write_vals)

    def action_cancel(self):
        for log in self:
            if log.state == "confirmed":
                raise ValidationError(_("已确认的提成请通过回滚功能处理。"))
            log.write({"state": "cancelled"})

    def action_refund(self, reason=None, factor=1.0):
        """Mark commission as refunded and create negative finance entry if needed."""
        for log in self:
            if log.state != "confirmed":
                continue
            factor = max(factor, 0.0)
            if not factor:
                continue
            reverse_vals = {
                "name": False,
                "sale_order_id": log.sale_order_id.id,
                "sale_order_line_id": log.sale_order_line_id.id,
                "employee_id": log.employee_id.id,
                "rule_id": log.rule_id.id,
                "ladder_line_id": log.ladder_line_id.id if log.ladder_line_id else False,
                "company_id": log.company_id.id,
                "currency_id": log.currency_id.id,
                "base_amount": -log.base_amount * factor,
                "quantity": -log.quantity * factor,
                "commission_amount": -log.commission_amount * factor,
                "state": "draft",
                "is_refund": True,
                "adjustment_reason": reason or _("关联订单退款/赊销回滚"),
            }
            credit_log = self.create(reverse_vals)
            if credit_log.commission_amount:
                credit_log.action_confirm()
            else:
                credit_log.unlink()
                continue
            log.write(
                {
                    "state": "refunded",
                    "adjustment_reason": reason or _("已生成冲减提成：%s" % credit_log.name),
                }
            )

    def _create_finance_transaction(self):
        self.ensure_one()
        amount = -abs(self.commission_amount or 0.0)
        if not amount:
            return False
        transaction_model = self.env["store.account.transaction"]
        channel = transaction_model._find_default_channel(
            self.company_id.id, preferred_type="internal", allow_create=True
        )
        transaction_vals = {
            "transaction_type": "commission",
            "amount": amount,
            "company_id": self.company_id.id,
            "currency_id": self.currency_id.id,
            "channel_id": channel.id if channel else False,
            "description": self.adjustment_reason or "",
            "reference": "%s,%s" % (self._name, self.id),
            "date": self.date,
        }
        transaction = transaction_model.create(transaction_vals)
        transaction.action_confirm()
        return transaction

    def unlink(self):
        if any(log.state == "confirmed" for log in self):
            raise ValidationError(_("无法删除已确认的提成日志，请先回滚。"))
        return super().unlink()
