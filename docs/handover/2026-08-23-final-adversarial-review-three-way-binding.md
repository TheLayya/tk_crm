# 三方关联实现 · 最终反方复审（只读）

- 日期：2026-08-23
- 审查对象：tk_crm 三方关联（账号-终端-节点）实现，未提交工作状态（git status 大量 M + 新增 devices/迁移/tests）
- 审查方式：只读代码走查（Read/Grep），未修改任何文件
- 参照：上一轮结论 [2026-08-23-team-association-adversarial-review.md](2026-08-23-team-association-adversarial-review.md)（6 P1 + 13 P2，GATE FAIL）

## 上轮 P1 修复状态核对

| 上轮 P1 | 状态 | 说明 |
|---|---|---|
| P1-1 角色 UI 无法授予 device 权限 | ✅ 已修复 | team_service PREDEFINED_PERMISSIONS 含 device:view/manage；RoleManage.vue 有"终端资产"权限组 |
| P1-2 DeviceOut 缺 node_ids | ❌ 未修复 | 见本轮 P1-A |
| P1-3 relations 绕过业务校验 | ⚠️ 部分 | 校验已内联到 API 层（存在性/状态/冲突带占用者名），但无异常封装（403→500）、无并发防护 |
| P1-4 双字段矛盾 + 约束删除 | ❌ 未修复 | 见本轮 P1-B |
| P1-5 账号绑定越权 | ⚠️ 部分 | 账号侧新增设备/节点存在性与状态校验，但对象级授权（数据范围）仍缺失，create 入口仍零校验 |
| P1-6 入口/追溯/同源 | ⚠️ 部分 | 节点页行内"关联"入口已加、反向追溯覆盖 JSON；设备详情编辑与显示不同源未修复 |

## 本轮 P1 清单（存在即 GATE FAIL）

### P1-A 设备列表响应丢 `node_ids` → 多节点绑定重开对话框被静默截断（上轮 P1-2 未修复）
- 位置：`schemas/device.py:39-56`（DeviceOut 无 node_ids 字段）vs `api/devices.py:92`（`_device_to_out` 显式传 `node_ids=`，Pydantic 默认 ignore 丢弃）
- 后果：`DeviceList.vue:260` 回显 `row.node_ids` 永远 undefined，退化为单节点 `[row.node_id]`；多节点设备保存关联后其余节点绑定静默丢失。
- 验收：GET /api/devices 每项含完整 `node_ids` 数组；多节点设备重开关联对话框回显全部节点且保存后与提交一致。

### P1-B `node_id`/`node_ids` 双字段矛盾 + 旧 PATCH 入口绕过全部校验（上轮 P1-4 未修复）
- 唯一约束 `uq_devices_node_id` 已被迁移 `20260823_0001` 删除，`device_service._is_node_unique_error` 引用死约束名（死代码）；DB 层无任何节点唯一性兜底。
- `update_device`（DeviceDetail 编辑入口）只校验/修改 `node_id`，不碰 `node_ids`：
  - **解绑失效**：编辑框清空节点 → 仅 `node_id=None`，`node_ids` 残留 → 列表/详情仍显示已"解绑"节点。
  - **换绑失效**：`node_id` X→Y，`node_ids` 仍 `[X]` → 显示层仍显示 X。
  - **JSON 占用可绕过**：设备 A `node_ids=[X,Y]`（node_id=X），设备 B 经旧 PATCH 绑 `node_id=Y` → `_check_node_duplicate` 只查 `node_id` 列 → 通过 → 节点 Y 双绑（违反"一节点一设备"）。
  - `DeviceUpdate.node_ids` 在白名单内可任意写（无存在性/状态/冲突校验）。
- `get_bindable_nodes` 只排除 `node_id` 列占用，不排除 `node_ids` JSON 占用 → 下拉可选到已被 JSON 占用的节点。
- 验收：DeviceDetail 编辑换绑/解绑后列表与详情即时一致；旧 PATCH 与 relations 走同一校验（JSON 占用同样 409）；删除死代码或恢复等价约束；`node_id` 只作为 `node_ids[0]` 的派生快照。

### P1-C 账号侧无对象级授权；创建入口零校验；dept 语义两模块漂移（上轮 P1-5 残余）
- `update_op_account`/`delete_op_account` 无数据范围校验：任何持 `op_account:edit` 的用户可改/删任意账号的 device_id/node_id 绑定（对象级越权，IDOR）。
- `create_op_account` 对 device_id/node_id 零校验（存在性/状态/占用均无）→ 创建即绕过三方全部约束。
- `api/op_accounts.py:55-56`：data_scope=dept 时 `scope_username=None` 等同 all（越权放大）；devices 模块则把非超管一律降为 self。两个关联模块数据范围语义互不一致。
- 验收：非超管改他人账号绑定 → 403/404；创建绑定不存在/已占用对象 → 业务 4xx；dept 语义两模块一致（实现或文档化降级）。

### P1-D 节点列表接口本体字段全部丢失 → 节点管理页大面积空白、关联下拉显示 undefined
- `ProxyNodeResponse`（schemas/proxy_node.py:92-101）仅 8 个关系字段（无 ip/port/status/protocol/密码/到期/测试等）；`list_nodes` 用它序列化全部节点。
- 后果：ProxyNodeManage.vue 表格 IP/端口/协议/状态/中转/测试结果/延迟/渠道/客户/出售人/密码/到期列全部空白或 `undefined`（148-227 行依赖 row.ip 等）；设备页与账号页关联弹窗节点下拉 label 渲染 `undefined:undefined`；删除确认文案 `undefined:undefined`。
- `ProxyNodeLegacyFields` 为无人引用的死代码（半成品痕迹）。
- 验收：GET /api/proxy-nodes 返回本体字段 + 关系字段；节点管理页各列正常渲染；三个关联弹窗下拉显示 `ip:port`。

### P1-E 审计日志链路断裂（任务核心检查点）
- DeviceLog 三方关系变更键为 `relations`，前端历史轨迹白名单 `DISPLAYABLE_LOG_FIELDS`（DeviceDetail.vue:185）不含 `relations` → **变更写了日志但用户不可见**。
- 节点反向绑定/解绑账号（`api/proxy_nodes.py:417-428` account 分支）：账号 node_id 变化**无任何审计**（无 OpAuditLog、无 DeviceLog），不可追溯。
- `OperationLogMiddleware.PATH_MODULE_MAP` 缺 `PUT /api/devices/{id}/relations`、`PUT /api/proxy-nodes/{id}/relation`（以及节点 CRUD）→ 全局操作日志缺失两个三方关联核心写端点。
- 验收：历史轨迹展示 relations 的 old/new 节点与账号；节点绑/解绑账号产生审计记录；OperationLog 记录两个关系端点（成功/失败均记）。

### P1-F 节点生命周期反向一致性缺失 → 悬空引用
- `delete_node`/`batch_delete_nodes` 物理删除不检查设备/账号绑定；SQLite 未启用外键 PRAGMA（`core/database.py` 无 connect 事件，ondelete="SET NULL" 不生效）→ `Device.node_ids` 残留死节点 ID、`OpAccount.node_id` 悬空，设备页显示绑定不存在的节点。
- `update_node`/`batch_update_status` 可把已绑定设备的节点改 sold/disabled，无占用提示/阻断。
- 验收：删除已绑定节点被 409 拒绝并提示占用者（或显式先行解绑）；状态变更时提示占用；database.py 启用 `PRAGMA foreign_keys=ON`；无悬空引用。

### P1-G 节点侧清空账号 = 静默解绑该节点全部账号
- `update_node_relation`：`account_id` 显式 None → 解绑 `node_id` 相等的**所有**账号（1:N 静默全清）；前端 openRelation 只回显第一个账号 → 用户清空下拉（意图"不改动"或"仅解绑当前账号"）实际解绑全部，无任何提示。
- 验收：清空仅解绑回显的账号，或 UI 明确展示全部绑定账号 + 保存前弹窗列出受影响范围。

### P1-H proxy-nodes CRUD 端点全部无鉴权（既有问题，三方关联暴露面扩大）
- `list/create/update/delete/batch-delete/batch-status/import/export` 均无 `require_permission`（git HEAD 版本即如此，非本次引入，但本次改造未修复且节点已成为关联操作对象）。
- 后果：未认证请求可物理删除节点、批量改状态，直接破坏已建立的三方绑定。
- 验收：全部节点端点挂权限依赖（或全局认证）；无令牌访问返回 401/403。

## 本轮 P2 清单（不构成 FAIL，需登记或顺手修）

| 编号 | 问题 | 位置 | 验收标准 |
|---|---|---|---|
| P2-1 | N+1 查询：节点列表每行全表扫描设备+查账号（500 行≈1000 次查询）；设备列表每行查账号；账号列表每行查设备+节点（上轮 P2-1 未修复） | `api/proxy_nodes.py:85-88`、`api/devices.py:84`、`api/op_accounts.py:71-74` | 列表接口单次请求 SQL 数恒定（批量 JOIN/IN） |
| P2-2 | relations/relation 端点无 `DeviceServiceError` 封装：越权调用 `get_device` 抛 403 → 未捕获变 500 | `api/devices.py:276-314`、`api/proxy_nodes.py:385-434` | 越权/业务错误返回原状态码与可读 detail |
| P2-3 | 并发防护不对称：`_device_mutation_lock` 只罩 create（update/relations/relation 无锁）；唯一约束删除后无 DB 兜底；进程内锁多 worker 失效；SQLite 写冲突报 "database is locked" 而非 409 | `device_service.py:21,198`、迁移 20260823 | 所有绑定入口统一冲突兜底；并发测试覆盖新端点；多 worker 场景无静默双绑 |
| P2-4 | 关联下拉无远程搜索、静默封顶（账号 200/节点 500/设备 200）、不标注占用状态（上轮 P2-3/P2-4 未修复） | `DeviceList.vue:262-265`、`OpAccountList.vue:760-762` | remote 搜索 + 占用者标注 + 超限提示 |
| P2-5 | 账号编辑弹窗全量提交 device_id/node_id，存在丢失更新风险（上轮 P2-9 未修复） | `OpAccountList.vue:895` 附近 `{...emptyForm(), ...row}` | 编辑表单提交字段显式白名单（不含关联字段）或表单内可编辑关联 |
| P2-6 | schema 与实现漂移：`DeviceCreate.node_ids` 重复声明且服务层忽略；`OpAccountCreate/Update` 无 extra=forbid（上轮 P2-12 未修复） | `schemas/device.py:15-16`、`schemas/op_account.py` | schema 与写入字段一致；账号 schema 加 extra=forbid |
| P2-7 | 权限语义交叉：节点页关联需 `device:manage`，账号页关联需 `op_account:edit`，无权限矩阵文档（上轮 P2-10 未修复） | `api/proxy_nodes.py:386` | 权限口径文档化并补矩阵测试 |
| P2-8 | 测试缺口：relations/relation 端点零测试；并发测试仅覆盖 create 旧路径且依赖进程内锁（测试环境还启用了生产未启用的 FK PRAGMA） | `backend/tests/test_devices_api.py` | 两个关系端点补 80% 行覆盖；并发测试覆盖新端点；测试与生产数据库配置一致 |
| P2-9 | 限流未启用：slowapi Limiter 定义但无 `@limiter.limit`、未挂载 SlowAPIMiddleware，default_limits 不生效（既有） | `middleware/rate_limit.py`、`main.py:68-70` | 登录/写端点限流实际生效 |
| P2-10 | 绑定语义不对称：节点页 `list(dict.fromkeys(ids + [node_id]))` 追加、设备页 relations 替换 | `api/proxy_nodes.py:414` vs `api/devices.py:309` | 两入口语义统一（建议均替换）并文档化 |
| P2-11 | 多节点设备列表/详情只显示第一个节点 IP（node_ip 取 `linked_node_ids[0]`，node_count 未用） | `api/devices.py:82-83` | 列表显示节点数 badge + 全部节点摘要 |
| P2-12 | CORS `allow_origins=["*"]` + `allow_credentials=True`（既有） | `main.py:72-78` | 收紧为白名单或去 credentials |
| P2-13 | 设备详情页不显示绑定账号；移动端设备卡片无"关联"入口 | `DeviceDetail.vue` 模板、`DeviceList.vue` mobile-cards | 详情显示绑定账号并可跳转；移动端提供关联入口 |

## 上轮 P2 登记状态（简要）

- 已见修复痕迹：P2-1（部分，账号/设备列表仍未修）、P2-2/P2-10 未核销（无批量关联、权限口径仍未文档化）。
- 仍存在：P2-3、P2-4、P2-9、P2-11（dept）、P2-12 均可见于本轮 P2 清单对应项。
- P2-13（基数设计确认：1 设备:1 账号 vs 一机多号）仍未文档化，且 20260823 迁移保留了 `uq_op_accounts_device_id` 强制唯一 → 与"一机多号"运营习惯的冲突需业务裁决。

## GATE 判定

```
[P1] 8 项（P1-A ~ P1-H）; [P2] 13 项（P2-1 ~ P2-13）; GATE FAIL
```

- 存在 [P1] → 本轮不通过。修复顺序建议：P1-D（前端可用性，一处 schema 修复面小）→ P1-B（模型收敛，决定其他修复方式）→ P1-A（随 P1-B 一并）→ P1-E/P1-G（审计与语义）→ P1-C/P1-H（权限）→ P1-F（反向一致性）。
- 已核对问题清单与 GATE 一致性：8 条 P1 全部为必须修复级，无"列 P1 却 PASS"的矛盾。
- 审查全程只读，未修改任何文件；审查后无新增工作区改动（本报告为唯一新增文件）。
