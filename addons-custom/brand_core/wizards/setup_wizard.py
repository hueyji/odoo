from odoo import _, fields, models
from odoo.exceptions import UserError


class BrandCoreSetupWizard(models.TransientModel):
    _name = "brand.core.setup.wizard"
    _description = "品牌多公司初始化向导"

    brand_name = fields.Char(
        string="品牌总部名称",
        required=True,
        default="雪茄威士忌品牌总部",
    )
    store_names = fields.Text(
        string="示例门店名称列表",
        required=True,
        default="雪茄威士忌·上海旗舰店\n雪茄威士忌·外滩会所",
        help="每行填写一个门店名称，系统会自动为其创建公司并挂载至品牌总部。",
    )
    investor_name = fields.Char(
        string="投资人虚拟公司名称",
        required=True,
        default="雪茄投资合伙人",
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="默认币种",
        default=lambda self: self.env.ref("base.CNY", raise_if_not_found=False),
        help="初始化过程中会将品牌总部及门店的默认币种统一为该币种。",
    )
    ensure_sequences = fields.Boolean(
        string="同步基础序列",
        default=True,
        help="若勾选，系统会为互通组与配置检查器准备基础序列。",
    )

    def action_initialize(self):
        self.ensure_one()
        if not self.currency_id:
            raise UserError(_("请先在系统中启用人民币（CNY）币种，再执行初始化。"))

        company_model = self.env["res.company"]
        created_companies = []
        updated_companies = []

        brand_company = company_model.search(
            [("name", "=", self.brand_name)], limit=1
        )
        if brand_company:
            brand_company.write(
                {
                    "company_role": "brand",
                    "is_brand_template": True,
                    "currency_id": self.currency_id.id,
                    "parent_id": False,
                }
            )
            updated_companies.append(brand_company.display_name)
        else:
            brand_company = company_model.create(
                {
                    "name": self.brand_name,
                    "company_role": "brand",
                    "is_brand_template": True,
                    "currency_id": self.currency_id.id,
                }
            )
            created_companies.append(brand_company.display_name)

        store_names = [
            name.strip() for name in (self.store_names or "").splitlines() if name.strip()
        ]
        for store_name in store_names:
            store_company = company_model.search(
                [("name", "=", store_name)], limit=1
            )
            values = {
                "company_role": "store",
                "currency_id": self.currency_id.id,
                "parent_id": brand_company.id,
            }
            if store_company:
                store_company.write(values)
                updated_companies.append(store_company.display_name)
            else:
                values["name"] = store_name
                store_company = company_model.create(values)
                created_companies.append(store_company.display_name)

        investor_company = company_model.search(
            [("name", "=", self.investor_name)], limit=1
        )
        investor_values = {
            "company_role": "investor",
            "currency_id": self.currency_id.id,
            "parent_id": brand_company.id,
        }
        if investor_company:
            investor_company.write(investor_values)
            updated_companies.append(investor_company.display_name)
        else:
            investor_values["name"] = self.investor_name
            investor_company = company_model.create(investor_values)
            created_companies.append(investor_company.display_name)

        if self.ensure_sequences:
            self._ensure_sequences(brand_company)

        message_parts = []
        if created_companies:
            message_parts.append(
                _("新增公司：%s") % ", ".join(created_companies)
            )
        if updated_companies:
            message_parts.append(
                _("更新公司：%s") % ", ".join(updated_companies)
            )
        if not message_parts:
            message_parts.append(_("所有目标公司均已存在，无需更新。"))

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("初始化完成"),
                "message": "\n".join(message_parts),
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    def _ensure_sequences(self, brand_company):
        sequence_model = self.env["ir.sequence"]
        sequence_data = [
            {
                "code": "store.link.group",
                "name": "互通组编号",
                "prefix": "LG%(y)s%(month)s",
                "padding": 4,
                "company_id": brand_company.id,
            },
            {
                "code": "brand.config.check",
                "name": "配置检查任务",
                "prefix": "CHK%(y)s%(month)s",
                "padding": 4,
                "company_id": brand_company.id,
            },
        ]
        for seq_vals in sequence_data:
            existing = sequence_model.search(
                [("code", "=", seq_vals["code"]), ("company_id", "=", seq_vals["company_id"])],
                limit=1,
            )
            if existing:
                existing.write(
                    {
                        key: seq_vals[key]
                        for key in ("name", "prefix", "padding")
                    }
                )
            else:
                sequence_model.create(seq_vals)
