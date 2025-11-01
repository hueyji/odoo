# Odoo 16 多公司 / 记录规则 / 门户权限复核（Team A）

> 更新人：Team A（2025-11-02）  
> 目标：梳理 Odoo 16 标准机制与 18.0 方案差异，明确 `brand_core` 互通基建是否需要调整。

## 核心结论
- Odoo 16 多公司模型仍依赖 `company_id` + `_check_company_auto`，自研模型需显式启用并在多对一字段上使用 `check_company=True`，互通方案无需改变共享范围设计。
- 记录规则默认使用 `company_id` 域过滤；品牌总部需要 `sudo()` 级别或专用规则访问所有门店。互通共享应通过额外记录规则（基于 `store.link.group`）放开，而不是放弃 `_check_company_auto`。
- 门户体系基于 Bootstrap 4 + 旧版 `portal`，保留 `portal.group_portal` / `portal.group_share`。互通门户经理组需继承 `portal.group_portal`，并通过 `portal.share` 记录授予加盟门店/投资人访问。
- 原 18.0 Redwood Portal 扩展不可复用，需要重新编写 QWeb 模板，但权限映射整体无变更；只需留意 16 中 `portal` 默认不加载品牌样式，需要在自研模块 assets 中补中文 UI。

## 多公司机制要点
1. **公司上下文**  
   - 16.0 中用户的默认公司字段为 `company_id`，可访问公司为 `company_ids`；与 18.0 相同，但 16 无 Redwood 命令面板简化界面，需要保留设置菜单来切换公司。  
   - 服务端应使用 `with_company(record.company_id)` 处理公司依赖字段；参见官方文档 `developer/howtos/company.rst`。
2. **自动公司校验**  
   - `_check_company_auto = True` 仍然默认开启；需在自研模型中保留该属性，避免跨公司数据串联。  
   - 对关联字段（如互通审批关联的门店、互通组成员）使用 `check_company=True`，以便 ORM 自动校验。  
3. **多公司共享**  
   - 若需要品牌总部操作门店数据，可在动作或服务中切换 `with_company` + `with_context(force_company=...)`；不建议直接 `sudo()` 以免违反审计要求。  
   - `res.company` 支持父子关系，保持品牌总部为父公司、门店/投资人虚拟公司挂载在其下即可，无需额外代码调整。

## 记录规则基线
1. **基础规则**  
   - 系统自带的 `ir.rule`：`multi_company_res_users`、`multi_company_partner` 会依据 `company_id` / `company_ids` 自动过滤；我们需扩展自研模型时遵循相同模式，域表达式 `['|', ('company_id', '=', False), ('company_id', 'in', allowed_company_ids)]`。  
   - 品牌平台管理员组应有一条 `sudo` 访问 `store.link.group`、互通日志等模型的规则，避免 2025-10-31 所述菜单缺失问题复发。
2. **互通共享规则**  
   - 对需要跨公司查看的数据（库存、会员、财务）不可直接授予全局访问，而应通过互通组建立补充规则：例如 `['|', ('company_id', 'in', allowed_company_ids), ('id', 'in', shared_record_ids)]`。  
   - 建议在互通批准后创建一条对应的 `ir.rule` 记录或使用 `sudo().with_user()` 结合 domain filter，后续实现时需设计缓存/刷新策略。
3. **管理员兜底**  
   - `base.group_system` 仍需保留访问所有模型；我们在 `ir.model.access.csv` 中务必给系统级组添加读取权限。  
   - 门店管理员只应看到本公司数据，互通查看基于 `store.link.group`；保持与 18.0 方案一致。

## 门户权限差异
1. **Portal 结构**  
   - Odoo 16 Portal 基于 QWeb + Bootstrap 4，与 18.0 Redwood Portal 存在前端差异。自研门户界面需重新实现，但权限模型未变。  
   - `portal.group_portal` 仍为门户基准组；`portal.group_share` 提供只读分享。互通门户经理需要继承 `portal.group_portal` 并额外拥有后台菜单访问。
2. **账号授权流程**  
   - 授予门户访问依旧通过 `Action -> Grant portal access`；`portal.share` 模型用于记录分享链接。  
   - 16 中邮件模板采用经典编辑器，邀请内容需自行本地化中文。 
3. **安全提醒**  
   - Portal 用户默认 `company_id` 为品牌总部的门户公司，需要在注册流程中调用 `with_company` 更新为对应门店/互通虚拟公司。  
   - 访问控制依赖 `website_publish`、`portal_access_rule`，我们在自研 REST API 中必须检查 `request.env.user.has_group('brand_core.group_brand_portal_manager')` 等组，而非手写 `portal` 判定。

## 对互通方案的影响
- 互通组设计可以保持：成员门店 + 共享范围字段；新增需求是在模型中启用 `_check_company_auto` 并在字段上启用 `check_company`。
- 需要提前规划以下开发任务：
  1. `store.link.group` 与互通申请模型在 `create/write` 中调用 `_check_company()`，拒绝跨品牌互通。
  2. 门户邀请逻辑必须同步 `company_ids`，否则门户经理跨店时将无法看到对应菜单。
  3. Demo 数据与初始化脚本中，为门户用户配置 `company_ids` 与默认公司，避免首次登录后的 `Access Error`。
- 不需要调整互通审批/共享流程，但在实现权限规则时需避免直接 `sudo`；建议为品牌平台管理员创建专用 `ir.rule`，并在审批动作中临时切换 `with_company`。

## 后续动作
1. 在即将编写的多公司初始化脚本中加入：`company_ids`、`with_company` 切换示例与 `_check_company_auto` 校验。
2. 在权限实现阶段准备两类记录规则模板：公司隔离 + 互通共享，供 Team B/E/F 引用。
3. 门户模板开发时，先建立中文基础布局，确认 `portal.group_portal` 仍可访问，并按本文档结论更新《中文 UI 与翻译规范》。
