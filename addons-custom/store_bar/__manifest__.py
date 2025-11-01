{
    "name": "门店吧台前台",
    "summary": "桌台管理与点单引擎（Team F）",
    "description": """
提供雪茄威士忌门店的桌台管理、点单基础模型与接口支撑：
- 定义 store.bar.table / store.bar.order 等核心业务模型。
- 预留接口权限、菜单与视图结构，支撑 Team F 前台体验开发。
    """,
    "version": "16.0.1.0.0",
    "category": "Sales/Point Of Sale",
    "author": "Team F",
    "license": "LGPL-3",
    "depends": [
        "base",
        "mail",
        "product",
        "hr",
        "store_inventory",
        "sales_team",
    ],
    "data": [
        "data/store_bar_sequence.xml",
        "security/store_bar_security.xml",
        "security/store_bar_rule.xml",
        "security/ir.model.access.csv",
        "views/store_bar_table_views.xml",
        "views/store_bar_order_views.xml",
        "views/store_bar_combo_views.xml",
        "views/store_bar_menu.xml",
    ],
    "demo": [
        "demo/store_bar_demo.xml",
    ],
    "installable": True,
    "application": True,
}
