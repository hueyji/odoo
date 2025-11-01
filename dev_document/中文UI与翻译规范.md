# 中文 UI 与翻译规范（Odoo 16.0）

> 目标：确保后台、Portal、报表、接口文案均以中文呈现，并为多团队协作提供统一术语。

## 1. 通用原则

- 默认语言：简体中文（`zh_CN`）。安装 Odoo 后立即启用中文，并将“语言条目自动导入”设为开启。  
- 所有新增字段、菜单、消息、报表标题必须提供中文标签；如需保留原文，请以“中文（英文）”格式标注。  
- 避免机翻：使用约定术语表，未收录的新词先在群内确认后再落库。  
- 接口错误码与提示文本必须使用中文，必要时可在括号内附英文关键字以便排查。

## 2. 模块翻译目录结构

- 每个自研模块创建 `i18n/zh_CN.po`，初次生成命令：
  ```bash
  ./odoo-bin --config=odoo.conf.local -d brand_multistore_dev --i18n-export=addons-custom/store_inventory/i18n/zh_CN.po --modules=store_inventory --language=zh_CN
  ```
- `po` 文件提交前运行 `msgfmt` 校验：
  ```bash
  msgfmt addons-custom/store_inventory/i18n/zh_CN.po -o /tmp/store_inventory.mo
  ```
- 新增字段务必在 Python 或 XML 中添加 `_` 翻译钩子或 `string=_(...)`。

## 3. 字段/菜单命名规范

- 字段标签使用「名词 + 补充说明」，例如：`互通范围`、`陈化天数（天）`。  
- 帮助信息 `help` 字段采用完整句子，结尾加句号：“互通组激活后才能同步库存。”  
- 菜单名称建议 2~6 个汉字，层级从品牌→门店→业务模块。示例：
  - 品牌平台 / 互通管理 / 互通申请
  - 门店运营 / 批次库存 / 调拨单
  - 财务结算 / 流水中心 / 互通清算

## 4. 场景术语表（持续补充）

| 英文 | 中文约定 | 备注 |
| --- | --- | --- |
| Link Group | 互通组 | Team A 模块主名称 |
| Aging Batch | 陈化批次 | Team B 主要数据对象 |
| Commission | 提成 | Team C |
| Clearing | 清算 | Team D |
| Member Balance | 会员余额 | Team E |
| Bar Order | 吧台订单 | Team F |
| Crowdfunding Project | 众筹项目 | Team G |

- 新增术语请在 PR 中更新本表并 @ 各团队确认；通过后同步至 `i18n` 文件。

## 5. Portal / 前端翻译

- Portal 模板位于 `views/portal_*.xml`，使用 `t-translate="off"` 控制不需翻译的代码片段。  
- 文案统一使用中文，若需双语，结构为 `<span>中文 <small class="text-muted">English</small></span>`。  
- 前端 JS（OWL）中的提示可使用 `env._t('中文提示')`，并在模块初始化时导入 `_t`。

## 6. 报表与打印

- QWeb 报表标题、列头必须为中文；对外报表保留英文时，使用 `中文（English）` 形式。  
- `report_xlsx` 文件头通过 `workbook.add_worksheet('报表名称')` 写中文。  
- 确保 `wkhtmltopdf` 安装后可渲染中文字体，必要时在 `/usr/share/fonts` 加入 `NotoSansSC` 并在模板中引用。

## 7. 测试与验收

- 单元测试中，对关键模型字段 `name_get()`、`display_name` 的断言使用中文。  
- QA 验收 checklist 中增加“中文翻译完整性”项，由各团队 Tech Lead 签字确认。  
- 若发现英文残留，提交修复 PR 前需补充 `i18n` 条目并更新此文档的术语表。
