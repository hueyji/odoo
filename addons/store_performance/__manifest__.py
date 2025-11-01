{
    "name": "门店业绩看板",
    "summary": "个人业绩统计与目标管理",
    "version": "16.0.1.0.0",
    "category": "Sales/Commission",
    "author": "Team C",
    "website": "https://example.com",
    "depends": [
        "store_commission",
        "hr",
        "mail",
        "web",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/store_performance_record_views.xml",
        "views/store_performance_target_views.xml",
        "views/store_performance_menus.xml",
    ],
    "demo": [
        "demo/store_performance_demo.xml",
    ],
    "application": False,
    "installable": True,
    "license": "LGPL-3",
}
