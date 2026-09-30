# 终端资产（设备管理）+ 节点二维码 — 实施计划（第 5 版）

日期：2026-08-22
目标：补齐 CLAUDE.md"功能差距"中的两项能力（参照项目 `TheLayya/proxy_acc`）。
版本说明：v5 整合对抗审查第 1 轮（4 [P1] + 14 [P2]）、第 2 轮（2 [P1] + 9 [P2]）、第 3 轮（1 [P1] + 8 [P2]）全部修复意见；**第 4 轮 APPROVE（0 [P1] + 5 [P2] advisory，已全部采纳）**。

## 一、现状摘要

### 本项目（tk_crm）已有
- **代理节点管理**（`proxy_nodes` 表）：采购/出售视角，字段含 `ip/port/username/password/protocol` + 中转信息 `relay_ip/relay_port/relay_protocol`；状态 `idle/active/sold/disabled`；列表筛选/导入导出/批量测试齐全；更新语义已用 **PATCH**（`PATCH /{node_id}` 部分更新，项目既有约定）。
- **权限体系**：`require_permission("模块:动作")` 后端依赖 + 前端 `hasPermission`/`v-permission`/路由 `meta.permission`；权限矩阵在 `RoleManage.vue` 的 `permissionGroups` 常量中维护；权限存 `role_permissions` 表、登录时聚合下发，无独立目录/种子。
- **操作日志**：`OperationLogMiddleware` 按 `PATH_MODULE_MAP` 正则记录；**当前 GET 过滤条件为 `method in (POST,PUT,DELETE) or ("GET" and "export" in path)`——本轮需扩展**。
- **UI 设施**：Element Plus + iOS 卡片风、桌面表格/移动卡片双布局（`Layout.vue` + `MobileTabBar.vue`）、`Breadcrumb`。
- **接口风格**：同步 SQLAlchemy（`Column`、Integer 自增主键）、分页 `skip/limit`、响应 `{"items": [...], "total": N}`、`db: Session = Depends(get_db)`。

### 参照项目（proxy_acc）的目标概念
- **设备管理**：`Device`（name/device_type pc|phone/owner_id/node_id 可空/remark），列表筛选，非管理员仅见自己的设备；详情页含基本信息 + 历史轨迹（old→new 审计）；绑定/解绑节点。
- **节点二维码**：`QRCodeDialog.vue`（qrcode 库 canvas 渲染 + 复制 URI），`socks5://` 代理二维码，Shadowrocket 扫码导入。

## 二、设计决策（含第 1、2 轮审查修复）

| # | 决策 | 理由 |
|---|------|------|
| 1 | 主键用 Integer 自增 | tk_crm 全库风格，不用 proxy_acc 的 UUID 字符串 |
| 2 | 设备绑定节点**不改节点状态** | tk_crm 节点状态是销售业务态（idle/active/sold/disabled），绑定仅作引用关系（KISS） |
| 3 | 历史轨迹用独立 `device_logs` 表 + **设备软删除** | `create_all` 自动建新表，零迁移；**软删除（is_deleted=True）+ 删除时清空 node_id**，`device_logs` 不级联保留，历史轨迹可追溯且节点可再绑 |
| 4 | 权限：`device:view` / `device:manage`；**QR URI 端点仅超管** | 与既有命名一致；**QR 凭据读取无对象级归属概念（节点无 owner），独立权限仍构成批量外泄面——故端点显式仅超管可用**（前端按钮同样仅超管渲染），从根上消除凭据批量外泄路径 |
| 5 | **对象级授权（防 IDOR，全部端点）** | 非超管：list 强制 `owner_id=自己`；get/update/delete/logs 校验归属否则 403；create 时 owner 强制为自己（传他人 400）；update 中 owner 字段仅超管可改 |
| 6 | 二维码 URI **后端权威生成（仅超管）** | 新增 `GET /api/proxy-nodes/{id}/uri`（超管专属 + 中间件审计 + 状态策略）；URI 规则集中后端并配测试；`DeviceOut/DeviceDetail` 白名单字段，**绝不序列化节点凭据** |
| 7 | 节点绑定规则 | 仅 `status in (idle, active)` 可绑定（否则 400）；**一个节点最多绑定一台设备**（`node_id` 唯一约束；check-then-insert 竞态由 **捕获 IntegrityError 返回 409** 兜底）；owner_id/node_id 必须存在（404） |
| 8 | URI 构建规则 | 中转优先（relay_* 齐全用中转，否则直连）；凭据 `urllib.parse.quote(value, safe="")`（**含 `/` 也转义**）；IPv6 主机加方括号；协议白名单 socks5/http/https；URI 不落日志、不存库；**仅 idle/active 节点可生成，否则 400** |
| 9 | 前端 JS 适配 | tk_crm 前端为 JS；`<script setup>` 编写，遵循双布局与 iOS 卡片风；schema 风格对齐现有 schemas 文件 |
| 10 | 审计 schema 稳定化 | `device_logs.changes` 固定结构 `{"field": {"old": ..., "new": ...}}`；**对单个 old/new 值截断（≤500 字符 + 截断标记），整体 json.dumps 保证 JSON 永远合法**；存 `user_id`（Integer 不可变归属）+ `username`（展示冗余） |
| 11 | **更新语义用 PATCH**（非 PUT） | 与项目既有 `PATCH /api/proxy-nodes/{node_id}` 约定一致；`exclude_unset=True` 区分"未传"与"显式 null" |
| 12 | **删除语义（统一规则）** | 软删除：`is_deleted=True` + `node_id=None` + 写 DELETE 日志。**list/detail/PATCH/DELETE 一律排除/拒绝已删除设备（404）；仅 `GET /{id}/logs` 允许超管查已删除设备的日志**（历史可追溯），非超管查已删除设备一律 404。测试与授权矩阵按此对齐 |
| 13 | **响应组装显式化** | ORM 对象不直接作 response（派生字段会缺失/校验失败）；API 层手工构造 `DeviceOut/DeviceDetail`（owner_name/node_ip 经 relationship 或按需查询，仿 proxy_acc `_device_to_out` 模式），schema 用 from_attributes 校验 |
| 14 | **URI 空值规则** | username/password 任一为空 → URI 省略 `user:pass@` 段；relay 三字段（ip/port/protocol）**必须齐全**才用中转，否则直连；直连 port 必填；protocol 小写归一化 + 白名单校验；None 值不进入 quote |
| 15 | **bindable-nodes 排除已占用节点** | `get_bindable_nodes(q, exclude_device_id=None)`：排除被**其他未删除设备**绑定的节点；编辑设备时传 exclude_device_id=当前设备（放行自己的节点），否则下拉出现不可绑节点导致 409 |
| 16 | **owner_id 空值语义** | `DeviceCreate.owner_id` 可选（非超管无需传，服务层强制自己；超管必填否则 400）；`DeviceUpdate.owner_id` 显式 null → 400；变更 owner 时校验存在 404 |
| 17 | **唯一性预检查排除自身** | 查重条件 `node_id == X AND id != 当前设备 AND is_deleted == False`（避免 PATCH 保留原节点被误判 409） |
| 18 | **编辑对话框完整字段** | DeviceDetail 编辑含 name/device_type/所属人(超管)/绑定节点/备注（PATCH 契约全部有 UI 入口） |
| 19 | **已删除设备的前端路径** | UI 不提供已删除设备浏览入口（v1）；删除后跳转列表并提示；超管经 `/logs` API 追溯（冒烟按接口验证，验收标准据此调整） |

## 三、授权矩阵（后端 enforce，前端仅 UI 收敛）

| 端点/动作 | 超管 | 普通用户（经角色授权） |
|-----------|------|------------------------|
| `device:view` 路由/菜单可见 | ✓ | 授权可见 |
| GET /api/devices（list） | 全部（含筛选） | **仅自己所属**（owner_id 参数忽略） |
| GET /api/devices/{id} | 任意**未删除**设备（已删除 404） | **仅自己所属且未删除，否则 403/404** |
| GET /api/devices/{id}/logs | 任意设备（**含已删除**——历史可追溯） | 仅自己所属（已删除 404） |
| POST /api/devices | 可指定 owner | **owner 强制为自己**（指定他人 → 400） |
| PATCH /api/devices/{id} | 全部字段（含 owner） | 仅自己所属；owner 不可改（→ 400）；name/device_type 显式 null → 400 |
| DELETE /api/devices/{id} | 任意设备 | 仅自己所属 |
| GET /api/devices/bindable-nodes?q= | ✓ | 授权 device:manage 者可调（仅返回 idle/active 节点摘要） |
| GET /api/proxy-nodes/{id}/uri | **仅超管** | 一律 403（无此权限路径） |

## 四、改动清单

### 后端（`backend/app/`）
1. **新增 `models/device.py`**：`Device`（id Integer PK、name String(100) 非空、device_type String(10) pc|phone、owner_id FK users.id 非空、node_id FK proxy_nodes.id 可空 + `UniqueConstraint("node_id")`、remark Text、is_deleted Boolean default False index、created_at/updated_at）；`DeviceLog`（id、device_id FK devices.id 无 ondelete、user_id Integer 非空、username String(64)、action String(16)、changes Text、created_at）。
2. **新增 `schemas/device.py`**：`DeviceCreate`（name min/max、device_type `^(pc|phone)$`、owner_id、node_id、remark）；`DeviceUpdate`（全字段 Optional；node_id 显式 None=解绑）；`DeviceOut`（含 owner_name；`node_id/node_ip` 显式 `Optional` 可空——未绑定设备响应 null；**无凭据字段**）；`DeviceDetail`（DeviceOut + updated_at + `node: Optional[dict]` 摘要仅 {id, ip, port, protocol, status}）；`DeviceLogOut`（id/user_id/username/action/changes dict/created_at）。
3. **新增 `services/device_service.py`**：list（skip/limit 默认 20 上限 200、keyword/device_type/owner_id 筛选、数据范围、排除 is_deleted）；create（owner/node 校验、非超管 owner 强制、写 DeviceLog）；update（归属校验、owner 仅超管、**name/device_type 显式 None → ValueError(400)**、remark 允许置空、node 换绑/解绑校验、变更集写 DeviceLog）；soft_delete（is_deleted=True + node_id=None + 写 DELETE 日志）；update 首行守卫 `is_deleted → 404`；get_logs（允许查已删除设备，权限按矩阵）；get_bindable_nodes(q, limit=100)（仅 idle/active，返回 id/ip/port/protocol）。`changes` 序列化：值级截断（≤500 字符 + "…(截断)" 标记）后 json.dumps；绑定/换绑唯一性冲突捕获 `IntegrityError` → **先 `db.rollback()`** 再返回 409（测试断言）。
4. **新增 `api/devices.py`**：router `/api/devices`（GET 列表、POST、GET /bindable-nodes（**注册在 /{device_id} 之前**）、GET /{id}、PATCH /{id}、DELETE /{id}、GET /{id}/logs）；写操作 `require_permission("device:manage")`、读操作 `require_permission("device:view")`；全部执行授权矩阵。
5. **改 `api/proxy_nodes.py`**：新增 `GET /{node_id}/uri`（**仅超管**：显式校验 `current_user.is_super_admin` 否则 403；节点不存在 404；status 非 idle/active → 400；返回 `{"uri": ...}`；按决策 #8 构建；注册在 `/{node_id}` 之前）。需确认/复用超管依赖（若无则按 team.py 现有模式实现 `require_super_admin`）。
6. **改 `main.py`**：显式 `from app.models import device`（确保 create_all 建表）+ 注册 devices router。
7. **改 `middleware/operation_log.py`**：`PATH_MODULE_MAP` 增加 `POST /api/devices`（终端资产/CREATE）、`PATCH /api/devices/\d+`（终端资产/UPDATE）、`DELETE /api/devices/\d+`（终端资产/DELETE）、`GET /api/proxy-nodes/\d+/uri`（节点管理/VIEW_SECRET）；**uri 条目必须排在列表靠前位置**（middleware 顺序匹配，`/api/proxy-nodes/\d+` 类通用模式若在前会吞掉分类——测试断言落库 module/action=节点管理/VIEW_SECRET）；**并修改 GET 过滤条件**：`method not in (POST,PATCH,PUT,DELETE) and not (method=="GET" and ("export" in path or "/uri" in path))` → 跳过（保证 VIEW_SECRET 落入审计）。
8. **新增 `tests/test_devices_api.py`**：CRUD 主流程；越权矩阵（非超管 get/update/delete/logs 他人 403、create 指定他人 owner 400、PATCH 改 owner 400）；list 数据范围；节点绑定（不存在 404、disabled/sold 400、重复绑定 409、**解绑/软删除后节点可再绑**、IntegrityError 兜底后 session 可用）；name/device_type 显式 null 400 与非法值 422；软删除后 list/detail 404/不可见、**logs 仍可查（超管）**、**对已删除设备 PATCH/DELETE 404**；未绑定设备响应 node 字段为 null；bindable-nodes 过滤与 q 搜索；fresh-DB 建表；**audit 落库断言（middleware 记录 module=终端资产）**。
9. **新增 `tests/test_proxy_node_uri.py`**：URI 纯函数——中转优先、`quote(safe="")` 含 `/` 凭据、IPv6 方括号、协议白名单；端点——非超管 403、超管 200、sold/disabled 400、不存在 404、审计记录写入（VIEW_SECRET 落 operation_logs）。

### 前端（`frontend/src/`）
10. **新增 `api/devices.js`**（getDevices/getDevice/createDevice/updateDevice/deleteDevice/getDeviceLogs/getBindableNodes）；`api/proxy_nodes.js` 增 `getNodeUri(id)`。
11. **新增 `views/devices/DeviceList.vue`**：筛选栏（关键词/类型/所属人——所属人下拉仅超管渲染，数据源复用 `GET /team/member` 即 getMembers）+ 桌面表格 + 移动卡片 + 分页 + 新增对话框（所属人：非超管固定为自己不渲染；节点下拉数据源 `getBindableNodes`（filterable 远程搜索 q））；新增按钮 `v-permission="device:manage"`。
12. **新增 `views/devices/DeviceDetail.vue`**：基本信息（descriptions + 移动字段列表）+ 历史轨迹 tab（时间线）+ 编辑（绑定/解绑节点、备注；owner 仅超管可见可改，数据源 getMembers）+ 删除（软删除）；操作按钮 `v-permission="device:manage"`。
13. **新增 `components/QRCodeDialog.vue`**：props visible/uri/title + **emit `update:visible`（v-model 双向契约，关闭按钮与父状态同步）**；qrcode.toCanvas；复制 URI；关闭清画布；失败 ElMessage.error 且清空 DOM。
14. **改 `views/ProxyNodeManage.vue`**：操作列"二维码"按钮 `v-if="authStore.user?.is_super_admin"` → `getNodeUri(id)` → QRCodeDialog。
15. **改 `router/index.js`**：`/devices`、`/devices/:id`（meta permission `device:view`、breadcrumb 终端资产）。
16. **改 `components/Layout.vue`**：侧边栏菜单"终端资产"（`hasPermission('device:view')`）。
17. **改 `components/MobileTabBar.vue`**：移动端 tab 增"终端资产"。
18. **改 `views/team/RoleManage.vue`**：`permissionGroups` 增"终端资产"组（device:view 查看 / device:manage 管理）。
19. **改 `package.json`**：加 `qrcode`；`npm install` 更新 `package-lock.json` 一并提交。安装失败则本轮 BLOCKED 汇报（无手写回退）。

## 五、验证（按 CLAUDE.md 对抗模式，逐条失败即停并记录退出码）

1. `cd backend && ./.venv312/Scripts/python.exe -m compileall app`（无报错；每条命令独立携带完整 `cd` 路径，不依赖持久工作目录）
2. `cd backend && ./.venv312/Scripts/python.exe -m pip install pytest pytest-cov mypy`（venv 内解释器）
3. `cd backend && ./.venv312/Scripts/python.exe -m pytest tests/test_devices_api.py tests/test_proxy_node_uri.py -v`（全过）；覆盖率 `--cov=app.models.device --cov=app.services.device_service --cov=app.api.devices --cov-fail-under=80`
4. `cd backend && ./.venv312/Scripts/python.exe -m mypy app/models/device.py app/schemas/device.py app/services/device_service.py app/api/devices.py app/api/proxy_nodes.py app/middleware/operation_log.py app/main.py`（本轮全部新增+修改文件，0 错误）；全库 `--strict` 遗留债务（延后登记）
5. `cd frontend && npm install && npm run build`（通过）
6. 手工冒烟：角色授权 → 建设备/绑节点/改绑/解绑/删除 → 历史轨迹 → 删除后列表不可见 + 超管经 /logs 接口追溯 → 非超管数据范围与越权 403 → 超管节点二维码渲染/复制/审计日志 → 非超管无二维码按钮

## 六、风险与对策

| 风险 | 对策 |
|------|------|
| 既有库无 alembic 使用记录（启动靠 create_all） | 只新增表不修改既有表；main.py 显式导入新模型；fresh-DB 建表测试兜底 |
| ProxyNodeManage.vue 较大 | 只插入操作列按钮与 dialog 挂载点，不重构 |
| qrcode 依赖需联网安装 | 失败即 BLOCKED 并汇报，不做手写回退 |
| 旧角色升级后无新权限 | 交付说明注明：需在角色管理勾选 device:view/device:manage |
| 非超管新增设备时成员下拉不可用 | 非超管创建时 owner 固定为自己、不渲染下拉 |

## 七、范围外（显式不做）

- 节点状态随绑定联动（决策 #2）
- 设备 Excel 导入导出、部门级数据范围、节点管理页"分配/解绑设备"反向入口（后续轮）
- 手写二维码组件回退实现（依赖失败即 BLOCKED）
- 全库 mypy --strict / 全库覆盖率达标（延后登记）
