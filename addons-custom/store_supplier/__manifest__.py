{
    "name": "门店供应商管理",
    "summary": "供应商档案、评分与采购历史分析（Team B）",
    "description": """
提供门店级供应商档案管理、评分黑名单与采购历史报表：
- 维护多公司独立的 store.supplier 档案，记录评分、黑名单与联系人。
- 汇总采购订单历史，输出供应商绩效报表。
- 为库存与调拨流程提供供应商画像接口。
    """,
    "version": "16.0.1.0.0",
    "category": "Inventory/Supply Chain",
    "author": "Team B",
    "website": "https://example.com",
    "license": "LGPL-3",
    "depends": ["purchase", "mail", "store_inventory"],
    "data": [
        # 1. 安全：组、规则、权限
        "security/store_supplier_security.xml",
        "security/ir.model.access.csv",
        # 2. 视图定义（必须在菜单之前，因为菜单会引用动作）
        "views/store_supplier_profile_views.xml",
        # 3. 菜单（最后加载，因为菜单引用动作）
        "views/store_supplier_menu.xml",
        # 4. 演示数据
        "data/store_supplier_demo.xml",
    ],
    "demo": [],
    "installable": True,
    "application": False,
}
