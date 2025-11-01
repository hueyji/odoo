# Team C 提成触发与财务确认时序

## POS 点单 / Team F → Team C → Team D
1. 调酒师在前台提交订单（POS），`store_bar` 触发 `pos.order` 创建与支付。
2. `store_commission` 捕获 `action_pos_order_paid`，生成提成日志（状态：待确认），并通过 `bus.bus` 发布 `commission.notify.<company_id>` 事件。
3. Team F 工作台监听事件，实时刷新调酒师提醒界面。
4. Team D 在收款完成后调用 `POST /api/v1/commissions/logs/confirm`，将日志状态更新为“已确认”，同步推送确认事件。
5. `store_performance` 随日志状态更新，月度/日度业绩看板同步调整。

## 销售订单 / Team B → Team C → Team D
1. 销售员确认 `sale.order`，`store_commission` 自动绑定责任员工并生成提成日志（状态：待确认）。
2. 日志通过实时事件推送至 Team F/品牌端面板，显示待确认提成。
3. 财务完成收款或核销，调用确认接口完成提成发放；若产生退款，触发 `action_cancel`，日志标记为“已回滚”。
4. 业绩模块自动调整对应周期的销售额、提成额与达成率。

## 退款回滚
1. POS 退款或销售订单作废时，`store_commission` 在原单日志上执行 `action_cancel`，发布 `commission.notify` 回滚事件。
2. Team D 同步撤销相关财务流水并记录原因。
3. `store_performance` 将待确认或已确认金额扣减，实现实时回滚。
