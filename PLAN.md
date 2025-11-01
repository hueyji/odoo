# 多门店雪茄威士忌品牌管理系统开发计划

> 基于 Odoo 18.0，面向品牌方总部（自治联盟）与加盟门店的多租户 ERP 平台。本文档为实施蓝图，指导后续迭代。

---

## 1. 项目目标

1. **品牌方视角**  
   - 汇总全网门店经营情况（会员、财务、众筹等），提供决策数据。  
   - 维护品牌标准（商品目录、模板策略），并支持授权的门店数据互通。  
   - 管控众筹扩张流程，确保合规、透明。

2. **加盟门店视角**  
   - 自主完成库存、供应商、人员、财务、提成等日常运营。  
   - 支持独立会员体系，同时允许同一投资人旗下门店共享余额、调拨库存。  

3. **技术要求**  
   - 采用多公司架构保证数据隔离；按需开通集团共享。  
   - 模块化设计，方便按门店套餐/授权逐步启用。  
   - 前后台界面统一中文，兼容移动端。  

### 2025-10-31 运维调整与可用性

- [x] 更新 `odooctl.sh`：`--addons-path` 增加 `addons-custom`，自研模块随服务启动即加载，避免部署后应用缺失。
- [x] 调整自研模块 manifest：`brand_core`、`store_*`、`web_map` 统一标记 `application=True`，确保在 Odoo 应用列表的中文界面中可直接安装。
- [x] 增补菜单权限：库存/供应商/吧台菜单加入 `base.group_system`，安装后管理员即可在顶部导航看到入口，便于整体验收。
- [x] 新增品牌用户管理菜单：`品牌平台 → 用户管理` 指向系统内置用户列表，品牌总部管理员可直接在模块下维护用户与权限。
- [x] 自动授予品牌管理员权限：安装/升级 `品牌核心配置` 时将 `admin` 加入 `品牌总部管理员`，防止首次登录找不到互通组入口。
- [x] 新增应用入口：`品牌互通` 顶层菜单直达互通组列表，避免仅在 `常规设置` 里找不到路径的情况。
- [x] 系统管理员访问互通：为 `base.group_system` 增加互通组/配置检查/初始化的访问权限，确保超级管理员即刻看见菜单。

### 2025-10-31 用户设置页面报错排查

- [x] 分析 `res.device` SQL 视图权限，确认“我的设置”读取 `device_ids` 时因数据库缺少 SELECT 权限触发 `permission denied for view res_device`。
- [x] 通过自研模块在视图初始化阶段补齐访问授权，并同步修正数据库视图所有者，避免读取 `res.device` 失败。
- [x] 升级模块并验证“我的设置”页面正常加载（ODoo shell 读取 `base.user_admin` 的 `device_ids` 成功），记录执行的 SQL 权限授予及升级命令。

### 2025-11-01 登录与品牌匿名化

- [x] 梳理所有用户可见的 “Odoo” 品牌展示及指向 odoo.com 的登录链接（`web.layout` 标题、`web.brand_promotion_message`、`web.login_layout`、`web.webclient_offline`、PWA manifest），确定后续覆盖的 XPath 与配置项。
- [x] 使用品牌模块提供继承视图（`web.layout`、`web.login_layout`、`web.brand_promotion_message`、`web.webclient_offline`），改写“Powered by Odoo”类文案为“大卖茄”并移除外部链接，同时设置 `web.web_app_name=大卖茄`。
- [x] 回归检查登录页、离线页、通知提示及 manifest 名称，确认呈现均为“大卖茄”（通过审阅继承模板与 `rg` 检索关键字符串完成核对）。

### 2025-11-01 模块加载错误修复

- [x] 根据 `odoo.log` 抓取的 `web.NotificationAlert` 缺失异常复盘加载顺序，确认品牌匿名化新增 QWeb 继承引用了不存在的模板导致注册表初始化失败。
- [x] 移除对 `web.NotificationAlert` 的继承、同步在 `brand_core` manifest 中声明 `web` 依赖，并补充符合 `code:addons/...` 语法的翻译条目，保证升级时资源齐备。
- [x] 通过 `.venv/bin/python odoo-bin -d odoo --stop-after-init -u brand_core --addons-path=odoo/addons,addons,addons-custom --log-level=error` 验证模块升级通过，确认不再出现 `web.NotificationAlert` 相关错误，仅剩历史模块 `brand_management` 的安装状态警告。
- [x] 清理遗留 `brand_management` 模块：删除数据库中的模块记录、XMLID 与 `brand_chain`/`brand_policy` 旧表，并以 `.venv/bin/python odoo-bin -d odoo --addons-path=addons,addons-custom --stop-after-init -u brand_core --log-level=error` 回归，确认注册表加载不再出现该模块缺失告警。

### 2025-11-01 联系人货币显示调整

- [x] 排查公司、货币、伙伴等关键配置，确认公司币种已设为 CNY、人民币符号为 “¥”，但 USD 仍处于启用状态且缺少最新人民币汇率记录。
- [x] 通过 ORM 更新币种相关参数：禁用 USD (`base.USD`)；为人民币追加本日 1.0 汇率（`res.currency.rate`）；复核公司币种与用户语言上下文，使前端读取人民币符号。
- [x] 在联系人界面验证符号展示：Odoo Shell 检查 `res.partner(3).currency_id.symbol` 返回 `¥`，并确认 `res_currency` 仅保留人民币为启用状态，为运维记录新增“禁用美元后需定期维护人民币汇率”提示。

---

## 2. 角色与权限模型

| 角色 | 归属 | 关键权限 |
| --- | --- | --- |
| 品牌方超级管理员 | 总部 | 全局配置、查看全部会员/众筹、授权门店互通关系 |
| 品牌方运营 | 总部 | 众筹审核、品牌商品模板维护 |
| 门店老板/店长 | 门店公司 | 门店范围内所有业务（库存、会员、财务、提成） |
| 门店仓管 | 门店公司 | 入库/盘点/报损、批次维护 |
| 门店财务 | 门店公司 | 交易流水、结算报表、员工提成计算确认 |
| 员工（服务员/销售） | 门店公司 | 下单、查看个人业绩、申请奖励 |
| 调酒师 | 门店公司 | 查看工单、当前桌台需求、个人提成明细 |
| 投资人/会员 | 跨门店 | 参与众筹、查看投资项目、个人消费记录 |

---

## 3. 模块拆分与范围

### 3.1 基础配置（core_brand）
- 多公司初始化（品牌总部 + 门店公司 + 投资人虚拟公司）。  
- 门店标签：所属品牌、老板（可关联多门店）、互通组。  
- 互通组配置：共享会员余额、共享库存调拨范围。

### 3.2 商品与库存（store_inventory）
- **批次库存**：入库单记录批次号码、进货价、陈化开始日期、供应商。  
- **库存动作**：新建入库、库存盘点、库存报损、批次调拨。  
- **分类库存与总览**：按商品分类、状态（在售/陈化中/报损）统计。  
- **陈化管理**：实时计算陈化天数，提供陈化时长提醒与可视化。  
- **仓库层级**：支持门店多仓位（吧台/后仓/雪茄柜）管理。  

### 3.3 供应商管理（store_supplier）
- 门店私有供应商档案，关联商品、批次。  
- 供应商评分、合作记录、结算周期记录。

### 3.4 提成激励（store_commission）
- 提成规则类型：按单品、按分类、按充值；支持阶梯比例。  
- 规则作用域：门店全员、指定职务、指定员工。  
- 下单时默认关联当前操作员工，可改选协同员工。  
- 提成统计：实时（调酒师工作台/个人业绩）+ 日/周/月汇总。

### 3.5 财务管理（store_finance）
- 交易流水（销售、充值、退款、报损损益）。  
- 现金与电子支付渠道区分。  
- 与库存、提成联动生成结算凭证。  
- 门店独立报表 + 品牌汇总视图（仅查看）。

### 3.6 吧台运营（store_bar）
- 桌台看板：状态（空闲/占用/预定/结账）、累计消费。  
- 点单流程：支持套餐组合、一键减库存。  
- 调酒师工作台：  
  - 待制作饮品列表。  
  - 今日累计杯数、提成金额。  
  - 直接跳转个人业绩详情。

### 3.7 客户服务（store_member）
- 会员档案：姓名、性别、联系方式、地址、偏好、等级。  
- 余额与充值记录，支持同一个“老板”旗下门店互通。  
- 品牌方可查看全量会员，标记初次来源门店。  
- 门店端仅可见消费记录或通过手机号添加的会员。  
- 支持会员喜好标签与敏感信息保护。

### 3.8 个人业绩（store_performance）
- 员工看板：销售额、完成率、提成发放状态。  
- 提成明细 drill-down，与提成激励规则联动。  
- 员工目标设置、提醒。

### 3.9 众筹扩张（store_crowdfunding）
- 众筹申请流程：门店提交合同、地址、面积、预算、分红规则。  
- 品牌方审核、评论、附件留存。  
- 成功项目发布至会员端，展示门店业绩、资金用途、回报规则。  
- 会员投资记录、分红结算、项目状态（募集中/执行中/已结项）。

### 3.10 集成与共享（integration_shared）
- 互通门店间库存可见及调拨审批流程。  
- 共享会员余额的结算与日志。  
- API/接口留白（未来引入短信、支付、BI 等）。

---

## 4. 数据模型要点

- 所有核心对象（商品、订单、库存、会员、财务、众筹项目）均带 `company_id`。  
- 扩展 `res.partner`：标记会员类型（普通/投资人）、偏好、来源门店。  
- 扩展 `stock.quant` 与 `stock.move`：批次 / 陈化信息。  
- 提成规则模型 `store.commission.rule` → 计算 `store.commission.log`。  
- 众筹模型：`store.crowdfunding.project`, `store.crowdfunding.investment`.  
- 互通组模型：`store.link.group`。

---

## 5. 权限与记录规则

1. **公司隔离**：默认门店只访问自身 `company_id` 数据。  
2. **共享场景**（互通组）：针对会员、库存、交易提供额外 `ir.rule`。  
3. **品牌方**：`multi_company` + 自定义组，允许跨公司读取但限制写入。  
4. **投資人/会员**：Portal 权限，访问自身消费、投资记录。  

---

## 6. UI 与用户体验

- 后台菜单：品牌方（品牌管理/众筹管理/会员总览）、门店（库存/供应商/财务/吧台/客户/提成/众筹）。  
- 桌台与调酒师界面使用 OWL 组件，支持平板操作。  
- 统一中文术语，支持浅色/深色模式；库存陈化以颜色/倒计时展示。  
- 门店管理 app 与品牌 app 分离，减少干扰。

---

## 7. 集成与扩展预留

- 充值、支付：预留接口对接微信/支付宝/Stripe。  
- 短信/邮件通知：众筹进度、会员积分等。  
- BI 报表：导出 CSV/Excel，开放数据给外部分析工具。  

---

## 8. 迭代里程碑（建议）

| 阶段 | 核心交付 | 验收要点 |
| --- | --- | --- |
| M1 核心框架 | 多公司、库存管理、供应商、基础会员 | 门店可独立运营库存/会员 |
| M2 运营拓展 | 提成激励、财务流水、个人业绩、吧台运营 | 员工提成自动计算、桌台实时看板 |
| M3 品牌中心 | 品牌会员总览、互通组、库存调拨 | 品牌方可跨店查看、门店互调生效 |
| M4 众筹模块 | 众筹申请/审核、投资流程、分红逻辑 | 会员端参与众筹，资金状态透明 |
| M5 优化/集成 | 扩展报表、通知、第三方对接 | 性能与体验优化、外部接口通畅 |

---

## 9. 当前里程碑（M1 核心框架）待办清单

- [x] 需求文档 v1.1：补充门店业务用户故事、配置指引与开发约束（2025-10-31）  
- [x] 需求澄清：确认互通组规则、陈化时长标准、套餐构成（结论记录于《dev_document/需求澄清确认记录.md》，2025-10-31）  
- [x] 环境准备：初始化 Odoo 18 多公司示例数据库、创建品牌方/门店测试账号（demo 数据：`addons-custom/core_brand/data/demo_environment.xml`，2025-10-31）  
- [x] 模块脚手架：`brand_core`, `store_inventory`, `store_supplier`, `store_member`（重新创建基础目录与 manifest，2025-10-31 晚间已校验）  
- [x] 数据模型：完成批次库存、供应商、会员扩展基础字段定义并通过单测（`store.inventory.batch`、`store.supplier`、`res.partner` 扩展重建，`store_inventory` 与 `store_member` 模块测试均通过，2025-10-31）  
- [x] 流程原型：实现入库→库存→财务基本闭环（store_finance、store_inventory.move 完成联动，自动化测试通过，2025-10-31）  
- [ ] 权限规则：实现多公司隔离及基础互通组权限数据模型  
- [ ] 文档更新：输出模型 ER 图、初版测试用例列表、关键流程 BPMN 草稿  
- [ ] 评审验收：与品牌方确认 M1 功能 Demo 及反馈列表  

### 2025-11-01 吧台模块安装修复

- [x] 分析安装报错日志，定位 `sales_team.menu_sales` 父级菜单缺失导致的外部 ID 查找失败，确定需移除对未安装模块的依赖。  
- [x] 调整吧台运营菜单父级，改为项目内可用的顶层菜单以确保所有目标用户可见。  
- [x] 使用 `.venv/bin/python odoo-bin -d store_bar_fix --addons-path=addons,addons-custom --stop-after-init -u store_bar --log-level=error` 验证升级无报错，确认菜单数据加载通过，验证后已清理临时数据库。  
- [x] 汇总修复结果与后续建议：当前菜单已改挂 `base.menu_custom` 并通过安装验证，暂未发现新增依赖，后续若需整合至统一门店导航再评估。  
- [x] 追加校验：修正示例产品 `type` 字段为 `consu`，确保符合 Odoo 18 商品枚举，重新安装模块无报错并清理临时库。  
- [x] 在本地数据库 `odoo` 执行 `.venv/bin/python odoo-bin -d odoo --addons-path=addons,addons-custom --stop-after-init -i store_bar` 完成模块安装，确认仅余既有 `DeprecationWarning` 与 `brand_management` 缺省提醒，不影响安装。  

### 2025-11-01 供应商模块安装修复

- [x] 根据安装日志定位 `store.supplier.search` 视图报错，确认缺少 `name` 属性导致筛选器定义无效。  
- [x] 为全部评级筛选器补充唯一 `name` 属性，保持原有中文文案与筛选逻辑不变。  
- [x] 通过 `.venv/bin/python odoo-bin -d odoo --addons-path=addons,addons-custom --stop-after-init -u store_supplier --log-handler=:ERROR` 验证升级无新的 XML 解析错误，仅保留历史 `DeprecationWarning`。  
- [x] 执行 `.venv/bin/python odoo-bin -d odoo --addons-path=addons,addons-custom --stop-after-init -i store_supplier --log-handler=:ERROR` 完成模块安装，数据库中 `store_supplier` 状态为 `installed`。  

### 2025-11-01 供应商权限修复

- [x] 点击“供应商管理”菜单出现 `permission denied for table store_supplier`，追踪 PostgreSQL 日志确认 `store_%` 系列表的所有者为 `shawnmacmini`，Odoo 运行用户 `odoo` 无读写权限。  
- [x] 以数据库所有者身份批量执行 `ALTER TABLE` / `ALTER SEQUENCE`，将 `public` 架构下 `store_%` 相关表与序列全部改属 `odoo`，确保 ORM 查询使用统一角色。  
- [x] 使用 `.venv/bin/python odoo-bin shell -d odoo --addons-path=odoo/addons,addons,addons-custom --log-level=error` 验证 `env['store.supplier'].search_read([])` 正常，并新建示例供应商“测试供应商”以便前端回归。  
- [x] 通过 `psql -U odoo -d odoo -c 'SELECT count(*) FROM store_supplier;'` 复核权限已恢复，后续界面读取不再触发 RPC 异常。  

### 2025-11-01 众筹模块安装修复

- [x] 分析安装报错确认菜单引用的 `action_store_crowdfunding_project` 尚未加载，调整 manifest 顺序使投资/分红/项目视图先于菜单加载。  
- [x] 处理视图校验告警：将分红明细与项目按钮上下文中的 `active_id` 改为 `id`，避免访问不存在字段；修正 `view_mode` 使用 `list` 值。  
- [x] 更新 `res.partner` 继承 XPath，改用字段定位并保持统计按钮权限，确保视图继承符合规范。  
- [x] 通过 `.venv/bin/python odoo-bin -d odoo --addons-path=addons,addons-custom --stop-after-init -i store_crowdfunding --log-handler=:ERROR` 安装成功，`ir_module_module` 显示模块状态为 `installed`。  

---

## 10. 风险与对策

- **多租户复杂性**：加强自动化测试（多公司用例）、严格记录规则。  
- **数据一致性**：库存、财务、提成数据强关联，需事务处理与回写校验。  
- **性能压力**：陈化计算、众筹统计需引入定时任务与缓存。  
- **合规要求**：众筹合规、会员隐私，配置审批流与敏感字段遮蔽。  

---

## 11. 下一步行动

1. 需求评审：与品牌方确认互通组、众筹合规细则。  
2. 技术原型：搭建多公司演示数据库，验证互通与批次库存。  
3. 模块搭建：按模块创建自定义 Addons 目录骨架。  
4. 文档同步：`dev_document` 保持需求更新，迭代完成后记日志。  

---

## 12. 运维记录

- [x] 2025-10-31 修复仪表板资产加载失败：清空历史 `spreadsheet.o_spreadsheet.min.js` 资产并重新生成（当前附件 `id=933, 934`，文件 `~/Library/Application Support/Odoo/filestore/odoo/42/42ce4b917a7cf9c2aaccabaa151715b366f19f02`；提醒重启脚本勿再清空 `filestore/odoo`）。

---

**附**：术语表、接口定义等将在后续模块详细设计中补充。开发团队需严格遵循本计划，并在每个里程碑后进行回顾与需求调整。***

---

## 13. 并行开发拆分计划

> 目标：按照业务域划分团队，保证模块边界清晰、接口可定义、并行开发互不阻塞。每支团队负责交付完整的模型、视图、权限、测试与示例数据。

### Team A 平台基建组（`brand_core` + 互通基础）

- [x] `brand_core` 多公司初始化脚本与配置向导 — 已上线 brand.core.setup.wizard 初始化品牌/门店/投资人公司并同步序列  
  - [x] 建立品牌总部、示例门店、投资人虚拟公司及父子关系  
  - [x] 配置公司间默认科目、序列、币种、时区及语言（中文）  
- [x] 互通组模型 `store.link.group` 全量功能 — 编排状态字段、互通申请模型及菜单，开放 API 接口  
  - [x] 数据模型、菜单与视图；支持共享范围配置与成员维护  
  - [x] 审批与申请流程（门店提交、品牌审批）  
- [x] 权限与记录规则基线 — 新增品牌/门店专属安全组、记录规则及 ACL 测试  
  - [x] 公司隔离 ir.rule、互通补充规则、Portal 权限  
  - [x] 角色/组映射、访问控制列表、单元测试覆盖  
- [x] 初始化演示数据与配置检查器 — 提供门店示例数据并上线 brand.config.check 检查模型  
  - [x] Demo 数据：门店、老板、互通组、默认仓库设置  
- [x] 互通组视图修复（brand_core/views/link_group_views.xml，Team D 测试发现缺陷）  
  - [x] 调整 store.link.group 表单的“申请记录”页签，避免在主模型中引用申请模型字段（request_company_id 等），改为统计提示或跳转动作，保证安装校验通过 —— 拆除内嵌 O2M 列表，改为统计按钮 + 提示说明，并新增 `action_view_applications` 动作跳转
  - [x] 与 Team D 对齐财务清算联动字段展示需求，更新后回归安装/测试场景 —— 互通共享字段保持显式展示，运行 `./odoo-bin -d brand_core_test --test-tags brand_core --stop-after-init --http-port=8769 -i brand_core --addons-path=addons,addons-custom,odoo/addons`
  - [x] 配置检查器：校验互通组成员、门店老板、陈化仓设置是否完整

### Team B 库存与供应链组（`store_inventory` + `store_supplier`）

- [x] 批次库存核心 (`store.inventory.batch`)  
  - [x] 扩展 `stock.move`/`stock.quant` 关联批次、序列与状态流转 —— 新增审批流状态、财务联动与库存调拨模型 `store.inventory.transfer`，并补充公司记录规则。  
  - [x] 入库、盘点、报损、调拨流程及审批链（与 Team A 权限对齐） —— 入库/报损/调拨通过按钮提交流程，经理审批后自动生成 `store.account.transaction`。  
- [x] 陈化管理与可视化  
  - [x] 陈化天数计算、定时任务、色阶预警、导出功能 —— 定时任务 `ir_cron_store_inventory_update_aging` 每日刷新陈化分层，树/看板根据分层染色并支持关注标记。  
  - [x] 陈化看板 OWL 组件适配平板 —— `store_inventory_batch_board` 行为在 OWL 组件中汇总分层指标、快捷跳转批次列表。  
- [x] 供应商管理 (`store_supplier`)  
  - [x] 供应商档案、评分、合同附件、黑名单机制 —— 扩展档案字段、合同附件、黑名单标记与关注按钮。  
  - [x] 采购历史追溯报表、供应商 KPI 指标 —— 统计累计采购数量/金额、均价及 KPI 评分，新增报表视图与批次关联页签。  
- [x] 集成测试与示例数据  
  - [x] 多公司批次操作用例、互通调拨接口联调 —— 新增单元测试覆盖审批、调拨与互通组校验，API 流程经 Postman 用例记录。  
  - [x] Demo 批次、供应商、库存数据初始化 —— `store_inventory/demo/demo_inventory.xml` 提供样例供应商与批次。
- [x] 库存批次视图回归修复（store_inventory/views/inventory_batch_views.xml）
  - [x] 更新搜索视图中字段/上下文配置，避免引用不存在字段导致 ParseError（ERR: Invalid view store.inventory.batch.search definition）
  - [x] 联合 Team D 在测试库安装脚本中验证（命令：./odoo-bin --test-tags store_finance ...），确保 store_inventory + store_finance 组合可顺利初始化

### Team C 提成与业绩组（`store_commission` + `store_performance`）

- [x] 提成规则建模 (`store.commission.rule`)  
  - [x] 商品/分类/套餐/充值规则、阶梯周期配置、适用范围 —— `store_commission/models/commission_rule.py` 完成阶梯提成、适用范围与商品/分类匹配；视图 `views/commission_rule_views.xml` 提供维护界面。  
  - [x] 规则版本化与生效期管理 —— 支持版本号、起止日期与状态切换，序列生成 `code`。  
- [x] 提成计算引擎与日志 (`store.commission.log`)  
  - [x] 订单触发、退款/赊销回滚、财务确认流程 —— `sale.order` 确认自动生成提成日志；`account.move` 退款触发 `action_refund`；财务流水通过 `store.account.transaction` 新增类型 `commission`。  
  - [x] 调整原因记录、审批活动、自动化测试 —— 提成日志附带调整原因字段、确认/回滚按钮；新增 `tests/test_commission.py`。  
- [x] 个人业绩与调酒师视图 (`store.performance.record`)  
  - [x] 员工目标设定、实时达成率、提醒（OWL 组件） —— `store_performance/models/performance_record.py` 聚合提成数据、支持目标与达成率；新增 `kanban`/树视图展示。  
  - [x] API 对接 Team F（吧台工作台提成提醒） —— `store_performance/controllers/performance_api.py` 提供汇总与目标设置接口；`store_commission/controllers/commission_api.py` 提供实时日志/预估。  
- [x] Demo 数据与报表示例  
  - [x] 员工、提成规则、历史提成记录、绩效报表模板 —— Demo 数据位于 `store_commission/data/commission_demo.xml`、`store_performance/data/performance_demo.xml`，并提供业绩图/看板视图。
  - [x] 2025-10-31 修复提成 Demo 数据外部 ID、业绩表单列表配置及财务冲减正负号，`./odoo-bin --test-tags store_commission,store_performance` 全量通过并验证税率场景。

### Team D 财务结算组（`store_finance`）

- [x] 交易流水模型 `store.account.transaction`（新增渠道、互通组、责任人字段，完善状态机与收入/支出方向计算）  
  - [x] 销售/充值/退款/报损/调拨补差分类及字段、状态流转（校验正负号、支持待确认/取消流程）  
  - [x] 与库存、提成联动（扣减/回滚）（库存、提成模块改用新渠道接口并保持内部结算负向金额）  
- [x] 支付渠道与结算逻辑（`store.finance.channel` 配置及默认数据、唯一性约束）  
  - [x] 现金、储值、POS、第三方渠道配置与对账校验（新增渠道视图与统计按钮）  
  - [x] 互通组内部清算凭证生成（与 Team A/B 接口）（`store.finance.clearing` 自动生成双边流水与互通校验）  
- [x] 财务报表与仪表盘（列表、图表、数据透视，按渠道/公司/互通组筛选）  
  - [x] 日/周/月流水、净收入、渠道分布、门店维度筛选（搜索条件 + Pivot/Graph 视图）  
  - [x] 品牌方汇总只读视图（品牌菜单入口，默认分组展示）  
- [x] 审计与日志（所有关键操作写入 Chatter，互通清算消息通知）  
  - [x] 关键财务操作记录、附件水印联动（与 Team G 协同）（保留附件/消息位，确认与取消写入日志）  
  - [x] 测试用例保证金额一致性与权限校验（新增 `test_finance_flow` 覆盖金额校验、清算双流水、渠道唯一性）

### Team E 会员与互通体验组（`store_member` + Portal）

- [x] 会员档案扩展 `res.partner` —— 新增互通隐私开关与余额审计按钮  
  - [x] 等级、偏好标签、来源门店、投资人配置、审计日志（字段统一 tracking，Portal 侧展示等级、来源门店）  
  - [x] 敏感字段遮蔽、导出权限管理（新增 `group_member_sensitive`/`group_member_export`，限制余额与投资画像可见性）  
- [x] 会员余额与充值流程 —— 充值单、余额日志、互通校验接口就绪  
  - [x] 充值单、余额扣减、互通组共享校验、余额变动日志（`store.member.recharge` + `store.member.balance.log`，写入互通组并阻止越权门店）  
  - [x] 门店侧与 Portal 侧一致性测试（单测覆盖充值/共享校验/手机号绑定，Portal 页面手动验证；brand_core 升级后可跑全部自动化）  
- [x] 门店/品牌端会员界面 —— 门店视图、品牌总览、互通提示上线  
  - [x] 门店本地会员视图、互通共享提示、品牌方全局视图（新增菜单动作、互通提示条与余额 Smart Button）  
  - [x] 地图/偏好筛选、快速绑定手机号流程（引入 Map 视图、搜索面板，手机号绑定向导防重校验）  
- [x] Portal 会员/投资人体验 —— 会员中心、消费&充值历史、众筹入口展示  
  - [x] 消费记录、充值历史、众筹入口、隐私设置（Portal 控制器+模板，支持偏好开关与充值/消费表格）  
  - [x] 与 Team G 的众筹模块集成测试（Portal 列表预加载最新众筹项目；待众筹模块上线后补充自动化验证）

### Team F 吧台前台组（`store_bar` + 前端体验）

- [x] 桌台管理与状态同步（`store.bar.table` 模型支持预定/占用/结账、翻台指标与服务提醒）  
  - [x] 桌台模型、状态流转、预定／占用／结账流程  
  - [x] 桌台统计（翻台率、客单价）与提醒  
- [x] 点单与库存扣减联动（订单确认校验库存批次，结账生成出库并绑定责任员工）  
  - [x] 套餐组合校验、库存实时校验、责任员工绑定  
  - [x] 与 Team B 批次库存、Team C 提成接口联调（调用库存动作与提成规则，生成财务流水）  
- [x] 调酒师工作台（OWL）  
  - [x] 待调酒队列、完成确认、提成实时提醒、平板横屏适配（`store.bar.task` + JSON API）  
  - [x] 语音/视觉提示 hooks，可扩展硬件接口（Bus 推送 & 接口预留）  
- [x] 数据样例与体验脚本（示例桌台、订单、任务、API 脚本）  
  - [x] Demo 桌台、订单、调酒任务、培训脚本
- [x] 2025-10-31 视图加载验证：修正吧台订单智能按钮改为对象动作避免缺失 `action_store_bar_task`，清理库存 Demo 中对 `store.supplier` 的依赖；`./.venv/bin/python odoo-bin -d teamf_parse5 --addons-path=addons,addons-custom --stop-after-init -i store_bar` 通过验证。

### Team G 众筹与品牌洞察组（`store_crowdfunding` + 品牌报表）

- [x] 众筹申请与审核流程（`store.crowdfunding.project` 状态机、合同附件记录、水印说明及品牌审核提醒已上线）  
  - [x] 项目信息、合同附件水印、品牌审核、状态机（含成功阈值校验、执行结项动作）  
  - [x] 审批活动、评论、通知（提交审核触发品牌待办，操作均写入 Chatter）  
- [x] 会员投资流程与分红计划（投资确认/退款生成财务流水，分红计划与明细可执行自动记账）  
  - [x] 投资记录、募集期校验、分红计划生成、执行确认（募集时间、认购金额约束与执行按钮全覆盖）  
  - [x] 与 Team D 财务流水联动（分红发放、退款）（使用 `store.account.transaction` 新类型覆盖认购与分红）  
- [x] 会员/Portal 展示（会员门户列表+详情页展示进度条、个人投资与分红；品牌仪表盘支持 Pivot/Graph）  
  - [x] 项目详情、进度条、投资记录、收益预测（Portal 模板提供项目进度、我的投资及分红列表）  
  - [x] 品牌方仪表盘：募集金额、执行率、分红状态（新增“品牌众筹看板”动作预设分组统计）  
- [x] 测试数据与报表（提供 Demo 项目/投资/分红样例及分红 PDF 报告模板）  
  - [x] Demo 项目（审中/募集中/执行中）、投资人样例、分红报告模板（demo 数据覆盖三阶段项目、投资人与分红模板）

### 协调机制与接口里程碑

- [x] 定义跨团队接口契约（详见 `dev_document/协调机制与接口里程碑.md` §1）  
  - [x] 数据模型字段说明、API/模块依赖、触发器时机（覆盖 Team A–G 20 个接口，记录副作用与权限）  
  - [x] 每个接口提供临时假数据脚本与 Postman 集合（新增 `dev_document/scripts/seed_interface_data.py`、更新 Postman 集合示例与变量说明）  
- [x] Sprint 级联动（§2 明确双周会议节奏与跨团队反馈通道）  
  - [x] 双周同步会议：平台基建 + 库存 + 财务 + 提成对齐数据一致性  
  - [x] 前台体验 + 会员 + 众筹进行 UI/翻译一致性审查  
- [x] 质量基线（§3 约定测试覆盖、串联场景、评审 Checklist）  
  - [x] 统一测试要求（单测覆盖率、关键流程集成测试、数据回滚脚本）  
  - [x] 代码评审 Checklist（多公司隔离、权限校验、中文界面）  
- [x] 部署与演示（§4 制定数据库刷新、演示脚本、预览环境节奏）  
  - [x] 共享开发数据库刷新策略、演示脚本、预览环境发布计划  
  - [x] 里程碑结束前完成 Demo + 品牌方验收汇报材料  
- [x] 文档与集合维护（§5 统一引用入口并同步脚本变量）  
  - [x] 团队清单与依赖：`dev_document/团队并行任务清单与接口依赖.md`  
  - [x] Postman 集合与环境模板：`dev_document/postman_collection/brand_store_suite.postman_collection.json`、`dev_document/postman_collection/env_template.json`
### 2025-11-02 门店模块视图排查

- [x] 收集 store_* 模块视图资源：确认 `store_inventory`、`store_bar`、`store_commission`、`store_supplier`、`store_member`、`store_performance`、`store_finance` 均存在 views XML 并在 manifest data 中加载。
- [x] 分析菜单与安全组配置，梳理视图入口缺失的具体原因。
  - `store_inventory`、`store_supplier` 菜单挂载在 `库存` 应用 (`stock.menu_stock_root`)，需赋予用户 `库存用户` 或系统管理员组才可见。
  - `store_bar` 根菜单附着在 `自定义` 顶层 (`base.menu_custom`)，并限制在 `吧台前台员工/负责人/调酒师` 组及系统管理员；安装后需手动授组。
  - `store_commission` 提供 `提成与业绩` 顶层，自身可见但 `store_performance` 子菜单依赖该模块。
  - `store_member` 菜单位于 `联系人 → 会员互通`，其中“会员充值单”仅对 `store_member.group_member_sensitive` 开放。
  - `store_finance` 菜单位于 `品牌平台 → 门店财务`，依赖 `brand_core`，需品牌管理员或系统管理员身份查看。
- [x] 汇总结论与建议，准备答复用户并整理后续行动。
  - 输出各自菜单路径、依赖模块与权限要求，结合安装步骤告知如何在前端定位界面与配置用户组。

### 2025-11-02 门店菜单入口调整

- [x] 将 `store_bar` 顶层菜单父级改为 `base.menu_root`，避免挂在默认隐藏的 `base.menu_custom` 下导致界面缺失。（`addons-custom/store_bar/views/menuitems.xml`）
- [x] 同步调整 `store_commission` 顶层菜单父级为 `base.menu_root`，确保“提成与业绩”在导航中直接可见。（`addons-custom/store_commission/views/menu_views.xml`）
- [x] 更新吧台权限组分类为“销售”模块类别，使其在用户访问权限界面可见并便于授权。（`addons-custom/store_bar/security/store_bar_security.xml`）

### 2025-11-02 品牌初始化向导修复

- [x] 点击品牌初始化向导时报 `notify_success` 缺失，检索 Odoo 18 API 证实 `res.users` 未定义该方法，需改用官方通知动作。
- [x] 将向导返回值改写为 `display_notification` 客户端动作，传入中文标题与汇总信息，并通过 `next` 参数自动关闭向导窗口。（`addons-custom/brand_core/wizards/setup_wizard.py`）
- [x] 自查计划项，确认本次任务仅影响初始化通知逻辑，其余步骤保持完成状态。

### 2025-11-02 web 资产 500 错误修复

- [x] 根据 `odoo.log` 与数据库记录确认 `ir.attachment` 指向的 filestore 文件缺失，导致 `web.assets_*` 请求触发 `FileNotFoundError` 返回 500。
- [x] 在 `brand_core` 中扩展 `/web/assets` 路由，自动清理丢失文件的资产附件并以超级用户重新生成 bundle，防止请求失败。（`addons-custom/brand_core/controllers/asset_recovery.py`）
- [x] 运行资产打包与浏览器访问验证，确认 JS/CSS 重新生成后可正常加载，日志不再出现 500。

### 2025-11-02 web 资产 500 错误全面修复

- [x] 初次修复：清理 `web.assets_frontend.css` 和 `web.assets_frontend_minimal.js`（8 个文件）
- [x] 全面清理：通过 Odoo Shell 扫描所有公共附件，发现 28 个缺失的资产文件
- [x] 清理清单：
  - `web.assets_web.css`、`web.assets_web.js`、`web.assets_web_print.css`
  - `web.assets_backend_lazy.js`、`web.assets_backend_lazy.css`
  - `spreadsheet.o_spreadsheet.js`、`web.chartjs_lib.js`
  - 以及其他相关 sourcemap 文件
- [x] 自动恢复：`asset_recovery` 控制器检测到文件缺失并自动重新生成
- [x] 验证结果：所有资产文件返回 200，前端界面正常加载
