# Team B ↔ Team D 库存成本联调指引

> 更新日期：2025-11-05，责任人：Team B

## 1. 联调目标

- 验证 `store.inventory.operation` 在调拨/报损执行后，是否正确回写 `stock.move` 与 `stock.valuation.layer` 的批次、成本字段。
- 校验 Team D 的 `store.account.transaction` 生成逻辑可读取以下字段并生成补差流水：
  - `move.store_batch_id`
  - `move.store_reservation_token`
  - `move.store_unit_cost`
  - `valuation_layer.store_batch_id`
  - `valuation_layer.store_unit_cost`

## 2. 准备数据

1. 安装 `store_inventory` 与 `store_supplier` 模块，加载演示数据：
   - 品牌总部批次：`PB2024…`（参考 `store_inventory_batch_demo_01`）。
   - 演示门店公司：`演示雪茄门店`，仓库 `湾区旗舰仓`，批次 `WHISKY-B001`。
2. 确保 Team D 模块已安装，且 `store.account.transaction` 允许外部接口写入。

## 3. API 调用示例

### 3.1 创建批次

```json
POST /api/v1/inventory/batches
{
  "product_id":  ref("store_inventory.product_product_whisky_batch"),
  "supplier_id": ref("store_inventory.store_inventory_supplier_branch"),
  "company_id": ref("store_inventory.store_inventory_company_branch"),
  "warehouse_id": ref("store_inventory.store_inventory_branch_warehouse"),
  "qty_initial": 150,
  "purchase_price": 455,
  "aging_start_date": "2025-01-10"
}
```

响应字段 `data.store_batch_id` 可传递给后续调拨操作。

### 3.2 发起互通调拨

```json
POST /api/v1/inventory/transfers
{
  "batch_id": 123,
  "quantity": 20,
  "dest_location_id": ref("stock.stock_location_customers"),
  "unit_cost": 470,
  "scheduled_date": "2025-01-12T10:00:00",
  "note": "门店互通调拨测试"
}
```

成功后，响应体包含：
- `operation_id` / `operation_name`
- `picking_id` / `picking_name`

Team D 需读取 `stock.move` 和 `stock.valuation.layer` 中的 `store_reservation_token` 字段，将其映射到补差流水。

## 4. SQL 校验模板

```sql
-- 查询最新调拨对应的库存移动
SELECT
    sm.id,
    sm.store_batch_id,
    sm.store_reservation_token,
    sm.store_unit_cost,
    svl.value,
    svl.store_unit_cost AS svl_unit_cost
FROM stock_move sm
JOIN stock_valuation_layer svl ON svl.stock_move_id = sm.id
WHERE sm.store_reservation_token = 'IO2025...';
```

预期：`store_unit_cost` 与 `svl.store_unit_cost` 均为 470，`store_batch_id` 对应调拨批次。

## 5. Team D 集成要点

- 在生成 `store.account.transaction` 时，将 `store_reservation_token` 映射为交易 `reference` 字段。
- 若遇到报损 (`operation_type='loss'`)，从 `stock.quant` 读取 `store_batch_id` 以同步成本。
- 互通清算时，`store_unit_cost` 作为默认成本基础；若 Team D 需要调整，可在财务模块中记录补差明细，并更新 `store.account.transaction.adjustment_amount`（见 Team D 模块说明）。

## 6. 回归清单

| 序号 | 场景 | 预期 |
| --- | --- | --- |
| 1 | 品牌总部批次调拨 | 生成拣货、SVL 带批次和成本 | 
| 2 | 演示门店批次报损 | `store_unit_cost` 回写，Team D 生成报损流水 |
| 3 | 多公司权限校验 | 未加入公司的用户访问接口返回 403 |

## 7. 后续动作

- Team D 在完成补差实现后，需更新本文件第 5 节“集成要点”并附上补差流水示例。
- Team B 将在自动化测试中补充调拨和报损的端到端脚本（计划编号：TB-FIN-2025-02）。
