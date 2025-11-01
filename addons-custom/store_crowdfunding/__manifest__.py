# -*- coding: utf-8 -*-
{
    "name": "众筹与品牌洞察",
    "summary": "众筹项目、投资与分红管理（Team G）",
    "description": """
为雪茄威士忌品牌提供众筹项目全流程管理能力：
- 定义 store.crowdfunding.project / investment / dividend 模型与审批状态机。
- 集成合同附件水印校验、mail.activity 审批提醒、品牌门户展示。
- 打通 store_finance 财务流水与会员投资记录，提供示例数据与 API。
    """,
    "version": "16.0.1.0.0",
    "category": "Customization",
    "author": "Team G",
    "website": "https://example.com",
    "license": "LGPL-3",
    "depends": ["mail", "portal", "website", "store_finance", "brand_core"],
    "data": [
        "security/store_crowdfunding_security.xml",
        "security/ir.model.access.csv",
        "data/store_crowdfunding_sequence.xml",
        # "data/store_crowdfunding_demo.xml",  # 临时禁用 demo 数据
        "views/store_crowdfunding_investment_views.xml",
        "views/store_crowdfunding_dividend_views.xml",
        "views/store_crowdfunding_project_views.xml",
        "views/store_crowdfunding_portal_templates.xml",
        "views/store_crowdfunding_menus.xml",
    ],
    "installable": True,
    "application": True,
}
