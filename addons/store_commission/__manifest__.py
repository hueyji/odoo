{
    "name": "门店提成管理",
    "summary": "门店提成规则与责任员工管理",
    "version": "16.0.1.0.0",
    "application": False,
    "author": "Team C",
    "website": "https://example.com",
    "category": "Sales/Commission",
    "depends": [
        "sale_management",
        "point_of_sale",
        "pos_hr",
        "hr",
        "mail",
        "brand_core",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/store_commission_rule_data.xml",
    ],
    "demo": [
        "demo/store_commission_demo.xml",
    ],
    "installable": True,
    "license": "LGPL-3",
}
