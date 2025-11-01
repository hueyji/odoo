# Team C 提成字段适配记录（Odoo 16）

## 核心差异
- `sale.order` 在 Odoo 16 中仍以 `user_id` 作为销售人员字段，未内置提成责任员工，需要与 `hr.employee` 映射。
- POS 端需依赖 `pos_hr` 扩展才能在 `pos.order` 上获取 `employee_id`，默认仅保存 `user_id`。
- `hr.employee` 支持多公司记录，需限定在当前公司或共享员工。

## 适配策略
- 新增统一字段 `commission_employee_id`，类型为 `hr.employee`，并在 `sale.order`/`pos.order` 强制要求。
- 自动从操作用户推导责任员工，缺失关联时阻止创建订单，确保提成规则依赖稳定。
- 同步 POS 订单的 `employee_id` 与销售订单的 `user_id`，保证报表与实时提醒可共用责任员工字段。 
