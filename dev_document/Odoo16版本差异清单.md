# Odoo 16.0 版本差异清单（对比《项目开发说明》原 18.0 方案）

| 序号 | 模块 / 主题 | Odoo 18.0 预设行为 | Odoo 16.0 现状 | 调整动作 |
| --- | --- | --- | --- | --- |
| 1 | 基础运行环境 | 官方文档默认 Python 3.11、PostgreSQL 14 起步 | Odoo 16.0 需使用 Python 3.10 与 PostgreSQL 13/14（`requirements.txt` 与 `setup` 同步验证） | 在 `.venv` 固定 `python==3.10.*`，并在环境指南中标注最低数据库版本 |
| 2 | Web 后台界面 | Redwood 2.0 UI（Tabs 置顶、命令面板） | 仍为 16 经典 WebClient（菜单横向 + 看板按钮），OWL 组件运行在旧样式表上 | 所有后端自定义动作用 `web.assets_backend` 注入，页面布局按经典界面设计，必要时提供额外 SCSS |
| 3 | OWL 前端框架 | OWL 3 + `@odoo/hoot` 测试工具链 | Odoo 16 仅内置 OWL 2，未内置 `hoot` 包 | 自研前端沿用 OWL 2 API（`useState` / `useEnv`），测试改用 QUnit + MockServer；禁止引用 `@odoo/hoot` |
| 4 | JS 资产打包 | `web.assets_backend`/`web.assets_frontend` + 动态 bundle | 16 仍使用 `__manifest__.py` 中 `assets` 键静态罗列文件 | 在清单中显式列出 OWL 组件、SCSS，保留 `web.assets_backend` 与 `web.assets_frontend` 键 |
| 5 | REST 控制器装饰器 | `auth='public'` 新增 `csrf=False, cors='*'` 缺省 | Odoo 16 仅支持 `type='json'/'http'` + `csrf=False` 参数，不支持 `cors` 缺省 | 控制器使用 `@http.route(..., type='json', auth='user', csrf=False)` 并自行处理跨域 |
| 6 | 支付登记接口 | `account.payment.register` 含批量支付优化与 `action_post_entries` | 16 中向导主要通过 `action_create_payments()`，批量付款多依赖自研逻辑 | 财务模块调用向导后接管凭证生成，必要时拓展 wizard 以写入自定义字段 |
| 7 | 讨论/活动实时性 | 18 默认启用全局总线 + 即时通知 | 16 中 `bus.bus` 需确保服务端开启 longpolling (`--longpolling-port`) | 在部署说明中增加 `odoo-bin gevent --longpolling-port` 指南，并在脚本里校验配置 |
| 8 | Portal 主题 | Redwood Portal + Tailwind 组件 | 16 Portal 基于 Bootstrap 4 + QWeb | Portal 自定义模板使用 QWeb/Bootstrap，提供中文标签与帮助文案 |
| 9 | 邮件模板设计器 | 新 builder 支持块拖拽 | 16 使用经典编辑器 + `mail.template` | 模板编写沿用 QWeb 片段，必要时引入 `website_mail` 组件 |
|10 | 报表引擎 | Spreadsheet 2.0（Pivot 强化） | 16 Pivot/Spreadsheet 功能稳定但 API 不含 `spreadsheet_dashboard_*` 模块 | 报表采用标准 Pivot + XLSX 导出，自研复杂报表用 `report_xlsx` |

> 更新人：平台基建组（2025-11-01）  
> 若后续 Odoo 16 官方补丁影响上述差异，请在评审会上同步并更新本清单。
