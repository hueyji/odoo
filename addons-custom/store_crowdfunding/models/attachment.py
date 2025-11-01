# -*- coding: utf-8 -*-
from odoo import fields, models


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    crowdfunding_watermarked = fields.Boolean(string="众筹水印已生成", default=False)
    crowdfunding_watermark_method = fields.Selection(
        [
            ("manual", "人工确认"),
            ("auto", "系统水印"),
            ("sign", "Odoo Sign"),
        ],
        string="众筹水印方式",
    )
    crowdfunding_watermark_date = fields.Datetime(string="水印生成时间")
