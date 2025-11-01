{
    "name": "门店库存管理",
    "summary": "门店批次库存与陈化管理（Team B）",
    "description": """
提供雪茄威士忌品牌门店的批次库存、陈化跟踪与供应链基础能力：
- 定义 store.inventory.batch 模型，记录批次、陈化信息与状态。
- 为 stock.move、stock.quant、stock.picking 扩展批次关联字段。
- 预置审批、菜单与视图结构，支撑 Team B 后续开发。
    """,
    "version": "16.0.1.0.0",
    "category": "Inventory/Inventory",
    "author": "Team B",
    "website": "https://example.com",
    "license": "LGPL-3",
    "depends": ["stock", "mail"],
    "data": [
        "security/store_inventory_security.xml",
        "security/ir.model.access.csv",
        "data/store_inventory_sequence.xml",
        "data/store_inventory_cron.xml",
        "data/store_inventory_company_setup.xml",
        "views/store_inventory_batch_views.xml",
        "views/store_inventory_operation_views.xml",
        "views/store_inventory_dashboard_views.xml",
        "views/store_inventory_menu.xml",
    ],
    "demo": [
        "data/store_inventory_batch_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "addons-custom/store_inventory/static/src/js/aging_dashboard.js",
            "addons-custom/store_inventory/static/src/xml/aging_dashboard.xml",
        ],
    },
    "installable": True,
    "application": True,
}
