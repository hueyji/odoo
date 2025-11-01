{
    "name": "门店库存与陈化管理",
    "summary": "为雪茄威士忌门店提供批次库存与陈化管理功能。",
    "version": "1.0.0",
    "category": "Inventory",
    "sequence": 20,
    "author": "多门店项目组",
    "website": "https://example.com",
    "license": "LGPL-3",
    "depends": [
        "web",
        "stock",
        "product",
        "mail",
        "brand_core",
    ],
    "data": [
        "security/store_inventory_security.xml",
        "security/ir.model.access.csv",
        "data/sequence_data.xml",
        "data/cron.xml",
        "views/inventory_batch_views.xml",
        "views/inventory_move_views.xml",
        "views/inventory_transfer_views.xml",
        "views/inventory_menu.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "store_inventory/static/src/components/batch_board/batch_board.js",
            "store_inventory/static/src/components/batch_board/batch_board.scss",
            "store_inventory/static/src/xml/batch_board_templates.xml",
        ],
    },
    "demo": [
        "demo/demo_inventory.xml",
    ],
    "installable": True,
    "application": True,
}
