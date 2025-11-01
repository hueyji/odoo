# Odoo 16.0 API 认证与权限策略指引

> 适用于雪茄威士忌品牌多门店项目所有 JSON 接口。目标：统一认证方式、权限映射与安全审计要求，避免多团队各自实现导致的安全缺口。

## 1. 认证模式总览

| 场景 | 推荐方式 | 说明 |
| --- | --- | --- |
| 内部前端（Web/OWL/Portal） | Session Cookie | 通过 `/web/session/authenticate` 登录，复用 Odoo 16 内建会话。 |
| 第三方系统/定时任务 | API Key | 使用用户级 API Key（`res.users.apikeys`）放入 `Authorization: Bearer <key>`。 |
| 公共 Portal | Session Cookie | Portal 用户同样走 `/web/session/authenticate`，权限由 `portal` 组控制。 |

- 禁止自定义 Basic Auth / 自建签名算法，优先复用 Odoo 标准能力。  
- 若必须开放第三方调用，需在接口描述中标注认证方式，并在 `postman_collection` 例子中明确。

## 2. Session Cookie 流程

1. 调用 `/web/session/authenticate`，传入 `db`、`login`、`password`。  
2. 成功后返回 `session_id`，写入请求头 `Cookie: session_id=<value>`。  
3. 服务端控制器使用 `auth='user'`，Odoo 自动完成权限校验。  
4. 若接口需要 Portal 访问，将 `auth='user'` 并在业务逻辑内判断 `request.env.user.has_group('portal.group_portal')`。

> Postman 集合中的「品牌管理员登录」请求已附带测试脚本，自动填充 `session_id` 环境变量。

## 3. API Key 流程

1. 打开「设置 → 用户与公司 → 用户」，选择用户后点击「生成 API 密钥」。  
2. 复制密钥后，仅用于后端脚本或第三方系统，前端禁止存储。  
3. 请求头加上 `Authorization: Bearer <api_key>`，控制器声明 `auth='api_key'`。  
4. 使用 `request.env.user` 获取对应用户身份，权限与 Session 相同。

> 约定：API Key 名称以 `brand_<team>_<用途>` 命名，例如 `brand_teamc_commission_sync`。

## 4. 权限映射

| 用户组 | 角色 | 备注 |
| --- | --- | --- |
| `base.group_system` | 品牌平台管理员 | 仅限品牌总部，拥有所有互通审批、配置权限。 |
| `base.group_user` | 门店内部用户 | 门店 CRUD 权限，受 ir.rule 限制在 `company_id` 范围内。 |
| `portal.group_portal` | 会员/投资人 | 访问 Portal，默认无写权限。 |
| `brand_core.group_brand_portal_manager` | 计划新增 | 供品牌方查看门店 Portal 数据，需在 `brand_core` 中定义。 |

- 所有接口在执行业务前必须进行二次校验，例如互通 API 检查 `request.env.company` 是否在互通组内。  
- 禁止在 Controller 中滥用 `sudo()`，除非为系统管理员提供只读数据导出，并需在代码注释说明原因。

## 5. 控制器实现模板

```python
from odoo import http
from odoo.http import request


class StoreInventoryController(http.Controller):

    @http.route("/api/inventory/batches", type="json", auth="user", csrf=False)
    def create_batch(self, **payload):
        if not request.env.user.has_group("brand_core.group_brand_manager"):
            request.env.user._rpc_check_access_rights("stock.picking")
        company_id = payload.get("company_id") or request.env.company.id
        request.env.context = dict(request.env.context, allowed_company_ids=[company_id])
        batch = request.env["store.inventory.batch"].create({
            "company_id": company_id,
            # ...
        })
        return batch._get_api_dict()
```

- `type="json"` 自动解析请求为字典；若需文件上传使用 `type="http"`。  
- `csrf=False` 仅对 API 开放；所有页面请求仍保留 CSRF。  
- 公司切换：使用 `allowed_company_ids` 控制记录可见性。

## 6. 审计与日志

- 接口需在 `ir.logging` 或自定义模型记录关键操作（如互通审批、资金流水），至少包含用户、公司、输入参数摘要。  
- 对外发布的 API Key 保存在密钥管理表，禁止在代码库明文出现。  
- 每周复查 Postman 集合，确认示例请求已使用正确认证方式。

## 7. 责任归属

- 文档维护人：平台基建组技术负责人（更新日期：2025-11-01）。  
- 若认证策略需调整（如启用 OAuth、SAML），必须先在里程碑会议评审，再更新本指引与相关脚本。
