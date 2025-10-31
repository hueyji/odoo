{
    "name": "门店业绩看板",
    "summary": "同步提成日志生成个人业绩记录，为调酒师与店长提供实时看板。",
    "version": "1.0.0",
    "category": "Human Resources",
    "sequence": 40,
    "author": "多门店项目组",
    "website": "https://example.com",
    "license": "LGPL-3",
    "depends": [
        "store_commission",
        "mail",
        "hr",
    ],
    "data": [
        "security/store_performance_security.xml",
        "security/ir.model.access.csv",
        "views/store_performance_views.xml",
    ],
    "demo": [
        "data/performance_demo.xml",
    ],
    "installable": True,
    "application": True,
}
