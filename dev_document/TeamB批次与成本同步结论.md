# Team B 批次与成本同步评审结论（Odoo 16.0）

> 更新日期：2025-11-05，责任人：Team B

## 1. 批次与标准批号模型的关联策略

- **委派关系**：保持 `stock.production.lot`（标准批号/序列号）模型不变，新增字段 `stock.production.lot.store_batch_id` 以指向 `store.inventory.batch`。
- **批次模型增强**：
  - `store.inventory.batch` 新增 `lot_ids` 及统计按钮，支持从陈化批次直接跳转到关联的序列批号列表。
  - 通过 One2many 关系维持映射，避免重写核心批号逻辑，也不引入继承冲突。
- **操作流程**：库存操作完成后自动将新生成的批号（如入库时扫描）与陈化批次绑定，保证追溯链路完整。

## 2. 库存估值与成本同步

- **`stock.move` 扩展字段**：
  - `store_reservation_token`：跨团队调拨/结算使用的锁定令牌，默认取库存操作编号。
  - `store_unit_cost`：批次成本单价，默认同步陈化批次进货价，可由接口覆盖。
  - `store_cost_currency_id`：派生自公司币种，确保金额核算一致。
- **`stock.valuation.layer` 扩展字段**：
  - `store_batch_id`、`store_reservation_token`、`store_unit_cost`，用于 Team D 读取库存估值并计算补差。
- **执行路径**：`store.inventory.operation` 在拣货完成后为相关 `stock.move` 与 `stock.valuation.layer` 回写上述字段，确保财务流水可溯源至批次。

## 3. 接口与多公司

- 新增 `/api/v1/inventory/batches`、`/api/v1/inventory/transfers`、`/api/v1/suppliers` 接口，所有请求均校验 `company_id` 是否在当前用户可见范围。
- Demo 数据增加 `store_inventory_company_branch` 与对应供应商 `store_supplier_profile_branch`，便于多公司联调与权限校验。

## 4. 风险与后续动作

| 项目 | 风险说明 | 对策 |
| --- | --- | --- |
| 批次 & 批号手工绑定 | 需要业务流程中显式创建/关联批号 | 在入库作业指引中补充扫描批号 → 选择批次操作步骤 |
| 成本同步准确性 | 接口覆盖范围需与 Team D 再确认（含报损/盘点） | 已在字段层预留，后续根据 Team D 结算脚本补充 case test |
| 多公司配置 | 新公司需补齐仓库/科目 | 当前仅用于演示，实际部署由平台组统一初始化 |

> 以上结论已在 2025-11-05 日常同步会上评审通过，可作为 Team D 对接与后续联调基线。
