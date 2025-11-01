# Odoo 16.0 Postman 环境变量说明

> 适用范围：`dev_document/postman_collection/env_odoo16_template.postman_environment.json`。所有变量均由 `dev_document/scripts/seed_interface_data.py` 或手动操作生成，使用前请先运行种子脚本并记录返回的 ID。字段默认中文注释，便于跨团队对齐。

| 变量 | 说明 | 数据来源 | 关联接口 |
| --- | --- | --- | --- |
| `base_url` | Odoo 实例基础地址 | 手动设置 | 全部 |
| `db` | 数据库名称 | 手动设置 | 认证请求 |
| `brand_admin_login` / `brand_admin_password` | 品牌管理员账号 | 种子脚本创建 | 00-认证/品牌管理员登录 |
| `store_manager_login` / `store_manager_password` | 上海门店店长账号 | 种子脚本创建 | 00-认证/门店店长登录 |
| `session_id` | 品牌管理员 Session，会随登录刷新 | 品牌管理员登录测试脚本写入 | Team A/D/G 接口 |
| `store_session_id` | 门店 Session，用于库存/点单/会员接口 | 门店店长登录测试脚本写入 | Team A/B/C/E/F 接口 |
| `link_group_id` | 互通组 ID（示例：旗舰店 ↔ 总部） | 在 Odoo 后台查看或脚本输出 | Team A、Team G |
| `store_company_id` | 当前操作门店公司 ID | 脚本输出 | Team A/B/D/E/F/G |
| `target_company_id` | 互通目标门店公司 ID | 脚本输出或手动查询 | Team A/B |
| `member_id` | 演示会员（陈雅婷）ID | 脚本输出 | Team E/F |
| `member_bind_phone` | 会员绑定接口示例手机号 | 脚本输出 | Team E |
| `member_bind_name` / `member_bind_email` | 绑定接口示例会员姓名/邮箱 | 脚本输出 | Team E |
| `member_list_keyword` | 会员列表查询关键字（示例：姓氏） | 手动或脚本输出 | Team E |
| `inventory_product_id` | 演示雪茄产品 ID | 脚本输出 | Team B/F |
| `inventory_batch_id` | 演示库存批次 ID | 脚本输出 | Team B/F |
| `supplier_partner_id` | 供应商合作伙伴 ID | 脚本输出 | Team B |
| `supplier_record_id` | 供应商档案记录 ID | 脚本输出 | Team B |
| `finance_channel_cash` | 现金渠道 ID | 财务模块配置或脚本输出 | Team D/F |
| `finance_channel_stored` | 储值渠道 ID | 财务模块配置或脚本输出 | Team D/E/F |
| `commission_employee_id` | 调酒师提成员工 ID | 脚本输出 | Team C/F |
| `sale_order_id` | 演示销售订单 ID（吧台订单生成） | 调用吧台下单接口返回 | Team C |
| `bar_table_id` | 桌台 ID | 脚本输出 | Team F |
| `bartender_employee_id` | 负责调酒员工 ID | 脚本输出 | Team F |
| `bar_order_id` | 吧台订单 ID | 创建吧台订单接口返回 | Team D/F |
| `crowdfunding_project_id` | 众筹项目 ID | 创建众筹项目接口返回 | Team G |
| `crowdfunding_investment_id` | 众筹投资记录 ID | 投资接口返回 | Team G |

> 变量值更新后请记得在 Postman 中同步环境并在 `PLAN.md` 备注记录关键信息，避免跨团队调试时出现 ID 不一致问题。
