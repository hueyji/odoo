# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class BrandCoreCellar(models.Model):
    """品牌陈化仓信息，供演示和健康检查使用。"""

    _name = "brand.core.cellar"
    _description = "品牌陈化仓"
    _check_company_auto = True

    name = fields.Char(string="陈化仓名称", required=True)
    company_id = fields.Many2one(
        "res.company",
        string="所属公司",
        required=True,
        default=lambda self: self.env.company,
        help="陈化仓所在的品牌公司或门店。",
    )
    manager_id = fields.Many2one(
        "res.users",
        string="负责人",
        help="负责陈化仓巡检的人员。",
    )
    temperature_target = fields.Float(
        string="目标温度(°C)",
        default=18.0,
        help="示例温度指标，可根据实际设备填入。",
    )
    humidity_target = fields.Float(
        string="目标湿度(%)",
        default=68.0,
        help="示例湿度指标，可根据实际设备填入。",
    )
    note = fields.Text(string="备注说明")

    @api.constrains("temperature_target", "humidity_target")
    def _check_environment_targets(self):
        for record in self:
            if record.temperature_target <= 0:
                raise ValidationError(_("目标温度必须大于 0 摄氏度。"))
            if not 0 < record.humidity_target <= 100:
                raise ValidationError(_("目标湿度需在 0 到 100 之间。"))
