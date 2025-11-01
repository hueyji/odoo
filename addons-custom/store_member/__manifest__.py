{
    "name": "会员互通管理",
    "summary": "品牌门店会员档案、余额与门户互通能力（Team E）",
    "description": """
为雪茄威士忌门店提供统一会员档案与余额管理能力：
- 扩展 res.partner 以承载会员等级、偏好、来源门店与投资人标记。
- 定义会员余额帐户与变动日志，支撑储值充值 / 扣减流程。
- 预留门户互通字段，用于品牌终端与多门店共享场景。
    """,
    "version": "16.0.1.0.0",
    "category": "Sales/CRM",
    "author": "Team E",
    "website": "https://example.com",
    "license": "LGPL-3",
    "depends": [
        "contacts",
        "mail",
        "portal",
        "auth_signup",
    ],
    "data": [
        "security/store_member_security.xml",
        "security/ir.model.access.csv",
        "data/store_member_sequence.xml",
        "data/store_member_level_data.xml",
        "views/store_member_preference_views.xml",
        "views/store_member_menu.xml",
        "views/res_partner_views.xml",
        "views/store_member_level_views.xml",
        "views/store_member_wallet_views.xml",
        "views/store_member_portal_templates.xml",
    ],
    "demo": [
        "data/store_member_demo.xml",
    ],
    "installable": True,
    "application": True,
}
