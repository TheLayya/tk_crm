# 团队关联（三方关联）对抗审查报告 — 2026-08-23

> 审查方：Claude 反方审查员（Orca worker，只读审查，未修改任何文件）
> 审查对象：运营账号 ↔ 终端（设备）↔ 代理节点 三方关联设计与前端工作流（tk_crm 工作树未提交改动）
> 审查视角：内部团队成员实际操作（固定审查问题 6 项全覆盖）

## 现状摘要

**数据模型**（迁移 `20260823_0001_add_account_device_node_links.py` + 模型改动）：
- `op_accounts` 新增 `device_id`（唯一约束 `uq_op_accounts_device_id`，1 账号:1 设备）+ `node_id`（无唯一、无状态校验）。
- `devices` 新增 `node_ids`（JSON 数组），同时**删除**了原有 `uq_devices_node_id` 唯一约束；`node_id` 单列保留，形成"单 + 多"双字段并存。

**后端入口**：
- `PUT /api/devices/{id}/relations`（`api/devices.py:269-288`）：一次性改 `node_ids` + `node_id` + 账号绑定，**无 schema、无校验、无日志**。
- `create/update_op_account` 直接接受 `device_id`/`node_id`（`op_account_service.py:105-109` 仅有 1 条 409 预检查）。
- 三个列表接口互查反向展示（账号列表显设备/节点、设备列表显账号、节点列表显设备/账号数）。

**前端入口**：
- 账号列表 `OpAccountList.vue`：行内"关联"按钮 → 弹窗选设备（仅 phone，200 条）+ 节点（500 条），保存走 `updateOpAccount`。
- 设备列表 `DeviceList.vue`：行内"关联"按钮 → 弹窗选账号（200 条）+ 多选节点，保存走 `PUT /relations`。
- 节点列表 `ProxyNodeManage.vue`：仅新增"绑定终端/关联账号数"两列，**无任何行内关联操作**。
- 设备详情 `DeviceDetail.vue`：编辑对话框仍走旧 PATCH 单节点路径。

## 固定审查问题 → 结论矩阵

| 固定问题 | 结论 |
|---|---|
| 成员能否从当前对象直接完成绑定、替换、解除 | ❌ 账号页/设备页可绑；节点页**零入口**；设备详情编辑与显示不同源（改完不变） |
| 是否支持搜索和批量操作 | ❌ 三处下拉均为一次性拉取（200/500 封顶、无远程搜索）；**无任何批量关联/解绑** |
| 冲突时是否显示占用者和可执行下一步 | ❌ 409 文案无占用者；设备页 `/relations` 静默抢占（无确认无日志） |
| 账号、终端、节点能否反向追溯 | ⚠️ 列表列可看；但节点页漏掉 `node_ids` JSON 绑定；`/relations` 变更不写任何日志 |
| 保存后三个页面是否即时一致 | ⚠️ 保存后仅刷新当前列表；无 keep-alive 缓存故导航重载可用，但同页多标签无感知 |
| 权限和数据范围是否保持原语义 | ❌ 角色 UI 无法授予 device 权限（422）；账号/设备绑定互相越权（见 P1-1/P1-3/P1-5） |

## P1 清单（必须修复，GATE FAIL）

### P1-1 角色无法通过 UI 授予终端资产权限 → 设备模块对普通成员整体不可用
- **证据**：`services/team_service.py:298-308` 的 `PREDEFINED_PERMISSIONS` 缺 `device:view`/`device:manage`；`team_service.py:342/365` 对未知权限抛 422；前端 `RoleManage.vue` 已提供"终端资产"权限组 → 保存角色必报"包含未知权限标识符"。`tests/conftest.py:126` 直接插库绕过验证，掩盖了此问题。
- **成员视角影响**：管理员按交付说明给运营角色勾选"终端资产"→ 保存失败；普通成员登录后侧边栏/移动端 tab/路由（`Layout.vue` v-if、`MobileTabBar.vue`、`router/index.js` meta.permission）全部不显示设备页。整个设备模块实际只对超管可用。
- **验收标准**：① 角色管理保存含 `device:view`/`device:manage` 的角色返回 200；② 普通角色登录后可见并可进入终端资产页、仅见自己设备；③ 新增 create_role/update_role 含 device 权限的回归测试。

### P1-2 `DeviceOut` schema 缺 `node_ids` → 前端多节点绑定重开对话框即被截断（静默数据丢失）
- **证据**：`schemas/device.py:37-53` `DeviceOut` 无 `node_ids` 字段；`api/devices.py:85` 传入的 `node_ids` kwarg 被 Pydantic 默认 ignore 静默丢弃；前端 `DeviceList.vue:260` 回退逻辑 `row.node_ids || (row.node_id ? [row.node_id] : [])` 永远只回显 1 个节点。
- **成员视角影响**：成员在设备页绑了 3 个节点 → 保存成功 → 再点"关联"只见 1 个 → 顺手保存 → 后端 `node_ids` 被截成 1 个，其余 2 个节点绑定无声消失。
- **验收标准**：① `DeviceOut` 显式声明 `node_ids: list[int]`；② 绑 2+ 节点后重开对话框完整回显、不保存直接关闭不产生变更；③ 序列化测试断言响应含完整 `node_ids`。

### P1-3 `PUT /devices/{id}/relations` 完全绕过业务校验层（api/devices.py:269-288）
- **证据**：`body: dict` 无 Pydantic schema；对 `node_ids` 不做存在性/状态/占用校验（可绑已售/禁用/不存在的节点）；`node_ids: null` → TypeError → 500；`account_id` 非数字 → ValueError → 500；无 `DeviceLog`/`OpAuditLog`；`middleware/operation_log.py:9-32` 无该路径映射 → 操作日志不落库。
- **成员视角影响**：成员可在设备页把节点绑成"已售"节点、把任意账号静默挪到本设备（原设备无感知、无历史记录可查）；乱传参数直接 500。
- **验收标准**：① 下沉 service 层并复用 Device 校验函数（状态仅 idle/active、占用检查、存在性）；② 请求改 Pydantic schema（`node_ids` 白名单 int 数组、`account_id` 可选、extra=forbid）；③ 节点不存在/不可绑 → 404/400，账号越权 → 403；④ 变更同时写 `DeviceLog`（含账号/节点 old→new）+ `OpAuditLog` + 中间件映射；⑤ 前端保存成功提示被替换方（原设备名/原账号名）；⑥ 补 ≥8 个测试（越权、悬空节点、静默抢占日志断言、非法参数 400/422）。

### P1-4 数据模型三角冗余自相矛盾（node_id 与 node_ids 双字段 + 约束删除后服务层仍按 1:1 校验）
- **证据**：迁移 `20260823_0001` 删除 `uq_devices_node_id`；`models/device.py:40` 注释"一个节点最多绑定一台设备"已失效；`device_service.py:93-104` `_check_node_duplicate` 与 `:107-119` `_is_node_unique_error`（检测已不存在的 `uq_devices_node_id`，死代码）仍让 PATCH 路径按 1:1 拦截，而 `/relations` 路径允许 1:N → **同一节点经两条路径结果矛盾，两设备可双绑同一节点**；`soft_delete_device`（`device_service.py:323-342`）只清 `node_id` 不清 `node_ids`；`get_bindable_nodes`（`:389-395`）排除逻辑只看 `node_id` 列 → 被 JSON 占用的节点仍出现在"可绑定"下拉。
- **成员视角影响**：A 成员在设备页绑了节点 X，B 成员在另一台设备的下拉里仍能选到 X 并保存成功，两设备同时显示占用同一节点；删除设备后 JSON 节点残留，后续成员无从判断节点到底还绑没绑。
- **验收标准**：① 明确三者基数设计（1 账号:1 设备:N 节点，或按业务确认多账号），消除 `node_id`/`node_ids` 双源（保留其一为唯一事实源）；② `/relations` 与 PATCH 路径走同一校验函数；③ 软删除同步清 `node_ids`；④ 删除死代码与失效注释；⑤ 补双路径一致性 + 双绑拒绝测试。

### P1-5 账号绑定不校验设备归属/状态，冲突无占用者信息 → 数据范围破坏 + UX 死锁
- **证据**：`op_account_service.py:105-109` 冲突检查只看 `OpAccount.device_id`，不查设备是否软删除，409 文案"该终端已绑定其他运营账号"无占用者；`create_op_account`（`:73-92`）无预检查 → 唯一约束冲突被 `api/op_accounts.py:97-102` 的 catch-all 吞成 500 并把原始 DB 错误 `detail=str(e)` 泄给前端；create/update 接受任意 `node_id`（含已售/禁用），与设备"仅 idle/active 可绑"语义矛盾；对 `device_id` 无数据范围/归属校验（self 范围用户可绑他人设备）。
- **成员视角影响**：账号绑到软删除设备后列表显示"未绑定"，再绑别的设备报 409，前端设备下拉又看不到占用设备 → 找不到占用者、无法解除，形成死锁；绑定已售节点不报错。
- **验收标准**：① 绑定前校验设备存在且未删除（404/400）；② 409 响应携带占用账号名/设备名；③ create 的 catch-all 不再泄漏 `str(e)`，完整性冲突映射为业务 409；④ 账号 node 绑定与设备节点同口径状态校验；⑤ 补软删除占位回归测试。

### P1-6 节点页无行内关联入口；节点反向追溯漏掉 JSON 绑定；设备详情编辑与显示不同源
- **证据**：`ProxyNodeManage.vue` 仅新增两个只读列（绑定终端/关联账号数），无绑定/解绑入口；反向查询 `api/proxy_nodes.py:82-88` 只匹配 `Device.node_id == n.id`，经 `/relations` 绑进 `node_ids` 的设备在节点页显示"未绑定"；`DeviceDetail.vue` 编辑对话框（`:118-136`）只提交 `node_id`（PATCH），而详情"绑定节点"（`:20-22`）显示 `node_ids[0]` → 成员改绑节点后详情显示仍旧值（保存不同步）。
- **成员视角影响**：成员在节点页看到"关联账号数 3"却无法点进去处理；想从设备详情改绑节点，保存后页面无变化，以为没保存成功。
- **验收标准**：① 节点行内至少提供"查看占用者/跳转绑定设备"入口（或明确登记延后，不得静默缺位）；② 节点列表反向查询覆盖 `node_ids` JSON 关联；③ `DeviceDetail` 编辑与显示同源（编辑改的是显示所用的字段），保存后详情即时刷新正确。

## P2 清单（本轮内尽量顺手修；不修须登记）

| # | 问题 | 证据 | 验收标准 |
|---|---|---|---|
| P2-1 | 列表 N+1 查询（账号列表每行 2 次、节点列表每行 2 次、设备列表每行 1 次） | `api/op_accounts.py:70-74`、`api/proxy_nodes.py:82-88`、`api/devices.py:77` | 列表接口单次请求 ≤5 条 SQL（50 行数据量） |
| P2-2 | 无批量关联/批量解除（固定问题"批量操作"缺失） | 三页面均只有逐行弹窗 | 账号列表支持勾选批量绑定同一设备/节点或批量解绑，带确认弹窗与成功/失败数反馈 |
| P2-3 | 关联下拉无远程搜索、静默截断（账号 200/节点 500/设备 200 封顶） | `DeviceList.vue:262-265`、`OpAccountList.vue:750-757` | remote 搜索；超过上限数据可搜到；超限时明确提示而非静默 |
| P2-4 | 下拉不标注占用状态 | 两处关联弹窗选项不含占用者信息 | 已占用设备/账号在选项上标注占用者；选中后提交前二次确认 |
| P2-5 | 冲突提示缺"可执行下一步" | 409 文案仅有"该终端已绑定其他运营账号" | 冲突弹窗包含占用者标识 + 跳转/一键解除入口 |
| P2-6 | 三页面即时一致性弱 | 保存后仅刷新当前列表，无跨页通知 | 保存成功提示含关联摘要；或全局事件让可见的其他列表自动刷新 |
| P2-7 | 导出/导入不携带关联（备份/迁移丢关联） | `op_account_service.py:282-291` `_EXPORT_COLUMNS` 无 device/node 列；导入亦不支持 | CSV/XLSX 导出含"绑定终端/绑定节点"列，导入可重建关联；若不支持需在导入模板说明 |
| P2-8 | 关联代码零测试（`/relations`、409 冲突分支、节点反向列、角色 422 均无覆盖） | `backend/tests/` 无 "relations" 匹配 | 新增代码行覆盖 ≥80%（CLAUDE.md 门禁口径），补越权/软删除/多节点回显用例 |
| P2-9 | 编辑账号表单隐藏携带 `device_id`/`node_id`（弹窗无关联字段却提交，有丢失更新风险） | `OpAccountList.vue:912` `{...emptyForm(), ...row}` 全量提交 | 表单提交字段显式白名单（不含关联字段）或表单内展示并可编辑关联 |
| P2-10 | 权限语义交叉：`device:manage` 即可重绑账号（属 op_account 变更） | `api/devices.py:270` | 关联操作权限口径明确化（如 device:manage 且 op_account:edit，或文档化交叉授权）并补权限矩阵测试 |
| P2-11 | dept 数据范围未实现：`get_user_data_scope` 返回 dept 时 `scope_username=None` 等同 all | `api/op_accounts.py:55-56`、`auth_service.py:255-269` | 实现 dept 过滤或文档明确降级语义；关联功能不得放大该缺口 |
| P2-12 | schema 与实现漂移：`DeviceCreate.node_ids` 被服务忽略；`OpAccountCreate/Update` 无 extra=forbid | `schemas/device.py:15` vs `device_service.create_device`；`schemas/op_account.py` | schema 与实际写入字段一致；账号 schema 加 extra=forbid |
| P2-13 | 设计确认项：`uq_op_accounts_device_id` 强制 1 设备:1 账号，与"一机多号"运营习惯可能冲突；账号 node 与设备 node_ids 关系未定义；无团队关联计划文档 | 迁移 + 模型 | 与业务确认基数后固化进 `docs/plans/`；`tk_crm/CLAUDE.md` 同步新工作流（当前未同步） |

## GATE 判定

```
[P1] 6 项（P1-1 至 P1-6）; [P2] 13 项; GATE FAIL
```

- 存在 [P1] → **本轮不通过**，主代理按 P1 清单修复后进入下一轮复审。
- 修复顺序建议：P1-1（权限可授予）→ P1-4（模型收敛）→ P1-3（/relations 下沉校验）→ P1-2（schema 回显）→ P1-5（冲突/软删除）→ P1-6（入口与追溯），P2 随轮顺手修。
- 已核对问题清单与 GATE 一致性：6 条 P1 全部为必须修复级，无"列 P1 却 PASS"的矛盾。
- 本轮为只读审查：未修改、未创建任何工作树文件（本报告为新增审查产物，不影响工作树基线判定口径）。

## 附：审查证据清单（文件:行）

- `backend/alembic/versions/20260823_0001_add_account_device_node_links.py:10-22`（加列 + 删 uq_devices_node_id）
- `backend/app/models/device.py:25-41`、`backend/app/models/op_account.py:16-17`
- `backend/app/api/devices.py:71-93`（_device_to_out）、`:269-288`（update_device_relations）
- `backend/app/services/device_service.py:93-119,323-342,389-395`
- `backend/app/services/op_account_service.py:73-92,100-119,282-291`
- `backend/app/services/team_service.py:298-308,342,365`
- `backend/app/api/op_accounts.py:55-56,70-74,97-102`
- `backend/app/api/proxy_nodes.py:82-88`
- `backend/app/middleware/operation_log.py:9-32`
- `backend/app/schemas/device.py:37-53`、`backend/app/schemas/op_account.py:51-88`
- `frontend/src/views/devices/DeviceList.vue:196-204,257-268`
- `frontend/src/views/devices/DeviceDetail.vue:118-136,366-376`
- `frontend/src/views/OpAccountList.vue:362-371,750-770,901-925`
- `frontend/src/views/ProxyNodeManage.vue`（新增两列，无操作入口）
- `frontend/src/views/team/RoleManage.vue:148-153,219-233`
