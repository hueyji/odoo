from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class StoreSupplier(models.Model):
    _name = "store.supplier"
    _description = "门店供应商档案"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _check_company_auto = True
    _order = "rating desc, id desc"

    RATING_SELECTION = [
        ("excellent", "五星"),
        ("good", "四星"),
        ("normal", "三星"),
        ("warning", "二星"),
        ("blocked", "一星"),
    ]

    name = fields.Char(
        string="供应商名称",
        required=True,
        tracking=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="关联联系人",
        required=True,
        tracking=True,
        domain="[('is_company', '=', True)]",
    )
    company_id = fields.Many2one(
        "res.company",
        string="所属公司",
        required=True,
        default=lambda self: self.env.company.id,
    )
    rating = fields.Selection(
        selection=RATING_SELECTION,
        string="合作评级",
        default="normal",
        tracking=True,
    )
    payment_term_id = fields.Many2one(
        "account.payment.term",
        string="结算周期",
        tracking=True,
    )
    delivery_lead_days = fields.Integer(
        string="平均交期（天）",
        tracking=True,
        default=0,
    )
    last_purchase_date = fields.Date(
        string="最近采购日期",
        tracking=True,
    )
    last_purchase_amount = fields.Monetary(
        string="最近采购金额",
        tracking=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="币种",
        required=True,
        default=lambda self: self.env.company.currency_id.id,
    )
    cooperation_note = fields.Html(
        string="合作记录",
        sanitize=True,
    )
    is_blacklisted = fields.Boolean(
        string="黑名单",
        tracking=True,
        help="标记存在严重质量或结算问题的供应商。",
    )
    contract_attachment_ids = fields.Many2many(
        "ir.attachment",
        "store_supplier_attachment_rel",
        "supplier_id",
        "attachment_id",
        string="合同附件",
        help="上传与供应商签署的合同、证照等附件。",
    )
    purchase_batch_ids = fields.One2many(
        "store.inventory.batch",
        "supplier_record_id",
        string="关联批次",
    )
    total_purchase_amount = fields.Monetary(
        string="累计采购金额",
        currency_field="currency_id",
        compute="_compute_purchase_metrics",
    )
    total_purchase_qty = fields.Float(
        string="累计采购数量",
        digits="Product Unit of Measure",
        compute="_compute_purchase_metrics",
    )
    average_purchase_price = fields.Monetary(
        string="平均采购单价",
        currency_field="currency_id",
        compute="_compute_purchase_metrics",
    )
    purchase_order_count = fields.Integer(
        string="完成采购次数",
        compute="_compute_purchase_metrics",
    )
    kpi_score = fields.Integer(
        string="供应商评分",
        help="基于准时率与合作评价计算的综合得分。",
        compute="_compute_kpi_score",
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "unique_partner_company",
            "unique(partner_id, company_id)",
            "同一公司内已存在该供应商档案。",
        )
    ]

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        for record in self:
            if record.partner_id:
                record.name = record.partner_id.name or record.name

    @api.constrains("delivery_lead_days")
    def _check_delivery_lead_days(self):
        for record in self:
            if record.delivery_lead_days < 0:
                raise ValidationError(_("平均交期不能为负数。"))

    def action_view_batches(self):
        self.ensure_one()
        action = self.env.ref("store_inventory.action_store_inventory_batch").read()[0]
        action.setdefault("domain", [])
        action["domain"] += [("supplier_record_id", "=", self.id)]
        action["context"] = dict(self.env.context, default_supplier_record_id=self.id)
        return action

    def _compute_purchase_metrics(self):
        Move = self.env["store.inventory.move"].sudo()
        for record in self:
            domain = [
                ("state", "=", "done"),
                ("move_type", "in", ["incoming", "transfer_in"]),
                "|",
                ("batch_id.supplier_record_id", "=", record.id),
                (
                    "&",
                    ("batch_id.supplier_record_id", "=", False),
                    ("batch_id.supplier_id", "=", record.partner_id.id),
                ),
            ]
            moves = Move.search(domain)
            total_qty = sum(moves.mapped("quantity"))
            total_amount = sum(m.quantity * m.unit_price for m in moves)
            record.total_purchase_qty = total_qty
            record.total_purchase_amount = total_amount
            record.average_purchase_price = total_amount / total_qty if total_qty else 0.0
            record.purchase_order_count = len(moves)

    def _compute_kpi_score(self):
        for record in self:
            base_score = 60
            rating_map = {
                "excellent": 95,
                "good": 85,
                "normal": 75,
                "warning": 60,
                "blocked": 30,
            }
            score = rating_map.get(record.rating, base_score)
            if record.total_purchase_qty > 0 and record.delivery_lead_days:
                if record.delivery_lead_days <= 7:
                    score += 5
                elif record.delivery_lead_days > 30:
                    score -= 5
            if record.is_blacklisted:
                score = 0
            record.kpi_score = max(0, min(100, score))
