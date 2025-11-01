# -*- coding: utf-8 -*-
{
    "name": "品牌平台基建",
    "version": "16.0.1.0.0",
    "summary": "多门店互通权限与门户骨架",
    "category": "Customization",
    "author": "Team A",
    "website": "https://example.com/brand",
    "license": "LGPL-3",
    "depends": ["base", "mail", "portal"],
    "post_init_hook": "post_init_hook",
    "data": [
        "security/brand_core_groups.xml",
        "security/ir.model.access.csv",
        "security/brand_core_rules.xml",
        "data/brand_core_mail_data.xml",
        "views/brand_core_menus.xml",
        "views/brand_core_cellar_views.xml",
        "views/store_link_group_views.xml",
        "views/brand_company_init_wizard.xml",
        "data/brand_core_import_templates.xml",
        "data/brand_core_health_checks.xml",
    ],
    "demo": [
        "demo/brand_core_demo.xml",
    ],
    "application": True,
}
