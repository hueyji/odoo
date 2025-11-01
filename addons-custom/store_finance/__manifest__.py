{
    "name": "门店财务管理",
    "summary": "财务流水与科目映射（Team D）",
    "description": """
提供门店财务流水管理、支付渠道配置与会计科目映射：
- 定义 store.account.transaction 模型，覆盖销售、充值、退款、调拨补差、众筹等业务。
- 支持按支付渠道配置会计科目与日记账映射，确保与 Odoo 16 科目体系一致。
- 预置示例数据、菜单与中文界面，便于 Team D 后续深度开发。
    """,
    "version": "16.0.1.0.0",
    "category": "Accounting/Accounting",
    "author": "Team D",
    "website": "https://example.com",
    "license": "LGPL-3",
    "depends": ["account"],
    "data": [
        "security/store_finance_security.xml",
        "security/ir.model.access.csv",
        "data/store_finance_sequence.xml",
        "data/store_finance_clearing_sequence.xml",
        "data/store_finance_payment_channel_data.xml",
        "data/store_finance_account_map_data.xml",
        "views/store_finance_menu.xml",
        "views/store_account_transaction_views.xml",
        "views/store_finance_payment_channel_views.xml",
        "views/store_finance_account_map_views.xml",
        "views/store_finance_clearing_views.xml",
        "views/store_finance_report_views.xml",
    ],
    "demo": [
        "data/store_finance_demo_transaction.xml",
    ],
    "installable": True,
    "application": True,
}
