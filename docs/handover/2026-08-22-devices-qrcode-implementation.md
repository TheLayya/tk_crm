# 终端资产 + 节点二维码 — 实施与验证记录（2026-08-22）

## 实施范围

按 [实施计划](../plans/2026-08-22-devices-qrcode-plan.md)（v5，对抗审查 4 轮 APPROVE + 5 项 advisory 采纳）执行。

### 后端（backend/app/）
- 新增 `models/device.py`：Device（软删除 is_deleted + node_id 唯一约束）+ DeviceLog（无级联，历史保留）——SQLAlchemy 2.0 Mapped 风格。
- 新增 `schemas/device.py`：Create/Update（PATCH 语义）/Out/Detail（节点摘要白名单，无凭据）/LogOut。
- 新增 `services/device_service.py`：DeviceServiceError 业务异常（404/400/409）、数据范围、绑定规则（仅 idle/active、1:1 唯一、IntegrityError→rollback→409）、日志值级截断（≤500 字符保证 JSON 合法）。
- 新增 `api/devices.py`：CRUD + bindable-nodes + logs；require_permission("device:view"/"device:manage") + 对象级授权矩阵。
- 改 `api/proxy_nodes.py`：GET /{node_id}/uri（仅超管 + idle/active + 审计）。
- 改 `services/proxy_node_service.py`：build_node_uri（中转优先、quote(safe="")、IPv6 方括号、协议白名单、空凭据省略 auth 段）。
- 改 `main.py`：显式导入 models.device（create_all 建表）+ 注册 devices router；slowapi 既有类型错加定点 ignore。
- 改 `middleware/operation_log.py`：PATCH 纳入写方法、GET "/uri" 纳入审计、新增 4 条路径映射（终端资产 CREATE/UPDATE/DELETE + 节点管理 VIEW_SECRET）。
- 新增 `mypy.ini`：sqlalchemy 插件 + follow_imports=silent（隔离遗留模块噪音）。

### 测试（backend/tests/）
- 新增 conftest.py（内存 SQLite StaticPool、中间件 SessionLocal monkeypatch、超管/普通用户/节点 fixtures）。
- 新增 test_devices_api.py（14 用例）+ test_proxy_node_uri.py（10 用例）。

### 前端（frontend/src/）
- 新增 `api/devices.js`、`views/devices/DeviceList.vue`（桌面表格+移动卡片+筛选+新增对话框）、`views/devices/DeviceDetail.vue`（基本信息+历史轨迹时间线+编辑/软删除）。
- 新增 `components/QRCodeDialog.vue`（qrcode 渲染、复制 URI、update:visible 契约、关闭清画布）。
- 改 `ProxyNodeManage.vue`：操作列"二维码"按钮（仅超管渲染）→ getNodeUri → QRCodeDialog。
- 改 router/Layout/MobileTabBar/RoleManage：/devices 路由（device:view）、侧边栏与移动端入口、角色权限矩阵"终端资产"组（device:view/device:manage）。
- 依赖：qrcode ^1.5.4（package.json + lockfile）。

## 验证结果（逐条执行，退出码记录）

| 项 | 命令 | 结果 |
|----|------|------|
| 编译 | `cd backend && ./.venv312/Scripts/python.exe -m compileall app` | ✅ 0 错误 |
| 测试 | `cd backend && ./.venv312/Scripts/python.exe -m pytest tests/ -v` | ✅ 24 passed |
| 覆盖率 | `pytest tests/ --cov=app.models.device --cov=app.services.device_service --cov=app.api.devices` | ✅ 84%（≥80% 达标；缺口为 500 兜底与少数异常分支） |
| mypy | `mypy --config-file mypy.ini <本轮 7 个文件>` | ✅ 0 错误（遗留 Column 风格属性经 cast 收口，见 device_service/api 注释） |
| 前端构建 | `cd frontend && npm install && npm run build` | ✅ 通过（chunk >500KB 警告为既有 echarts 问题，非本轮引入） |

## 实施后对抗审查

6 路 Codex 审查（service / api / 模型+URI+中间件 / 测试 / 前端视图 / 前端接线）。

### 第 1 轮（6 路）发现与修复

**A 路（device_service.py）— 3 [P1] + 3 [P2]，全部修复**：
- [P1] list_devices 非超管且 current_user_id=None 时 fail-open → 服务层显式 400（防全量泄露）。
- [P1] 对象级授权仅在 API 层 → 下沉服务层为权威执行点（get/update/delete/logs 均校验归属）。
- [P1] update 无字段白名单（setattr 可改 is_deleted/id 等保留字段）→ ALLOWED/FORBIDDEN 字段表 + schema extra="forbid" 双层防线。
- [P2] 软删除日志失真（name old→None 而 name 未变、缺 is_deleted 迁移）→ 改为 is_deleted false→true + node_id 清空；create 日志值统一走截断；_truncate_value(None) 保持 JSON null。
- [P2] 节点状态 check-then-use 竞态 → flush 前复核状态（窗口缩到最小；SQLite 写串行化下为业务规则级残余风险，已注释说明）。
- [P2] IntegrityError 全部映射 409 误分类 → 按约束名精确判定（node_id/uq_devices_node_id → 409），其他完整性错误 rollback 后重抛 500。

**B 路（api/devices.py）— 1 [P1]（路向错配误报）+ 3 [P2]，2 项修复**：
- [P1] "URI 端点不在 devices.py" — 误报：URI 端点按计划在 `api/proxy_nodes.py`（C 路覆盖审查），记录在案不改动。
- [P2] bindable-nodes 的 exclude_device_id 无归属校验（可借他人设备 ID 探测其绑定节点）→ 非超管校验该设备存在且属于自己，否则 403；新增回归测试。
- [P2] get_device_logs total=len(items)（分页错）→ 服务层独立 COUNT 返回 (logs, total)。
- [P2] 路由层 raw IntegrityError→500 → 已由 A 路服务层修复覆盖（node 唯一冲突转 409）。

**C 路（models/URI/中间件）— 2 [P1] + 5 [P2]，有效项全部修复**：
- [P1] "软删除保留 node_id 致节点永久占用" — 复核：`soft_delete_device` 已清空 node_id（唯一约束对 NULL 不冲突），并有 `test_soft_delete_frees_node` 锁定。**已闭环，无需改代码**。
- [P1] DeviceDetail.node 为无约束 dict → 新增 `NodeSummary` schema（白名单字段 + `extra="forbid"`），API 层构造 NodeSummary，凭据字段物理上不可能被序列化；新增泄露断言测试。
- [P2] build_node_uri 单凭据输出 `user:@host` 违反契约 → 改为**仅双凭据齐备才输出 auth 段**（修正了我此前写错的测试断言）。
- [P2] host 未校验 → 空白/斜杠/@/#/? 等非法字符拒绝；IPv6 zone 保留在方括号内。
- [P2] relay_protocol 非法静默回退 → 非法协议直接 ValueError（不产生误导 URI）。
- [P2] owner_id 显式 null → service 层 400（复核已存在）。DeviceLogOut.changes 解析 — API 手工构造已规避（记录）。

**D 路（测试）— 6 [P1] + 4 [P2]，全部补齐**：
- [P1] 设备序列化凭据泄露无断言 → `test_device_responses_never_expose_node_credentials`（list/detail 不含凭据与 uri，节点摘要字段精确匹配）。
- [P1] URI 审计保密无断言 → `test_uri_endpoint_audited_without_secret_leak`（日志所有字段不含 URI/凭据）。
- [P1] 跨 owner 绑定未测 → `test_cross_owner_node_binding_conflict`（409）。
- [P1] 并发绑定竞态未测 → `test_concurrent_node_binding_single_winner`（文件型 SQLite + 双线程 + Barrier，断言 201/409 各一且最终一行绑定）。
- [P1] 删除后原 owner 查 logs 未测 → `test_deleted_device_logs_404_for_former_owner`。
- [P2] 全部处理：URI 保留字符表驱动语料（/ : # ? % 空格 中文 + unquote 往返断言）、owner 变更成功与 404 用例、PATCH/DELETE 审计落库断言、fixture 开启 `PRAGMA foreign_keys=ON`。

**E 路（前端视图）— 1 [P1] + 7 [P2]，有效项全部修复**：
- [P1] 日志 changes 直出（可能泄露敏感值）→ 前端**白名单字段渲染**（仅 name/device_type/owner_id/node_id/remark/is_deleted，字段名中文化）；服务端本就不记录凭据，双重防线。
- [P2] 全部处理：watch route.params.id 重载（组件复用场景）；加载失败清空旧数据并显示 404 语义；日志分页（total + 分页控件）；列表与节点搜索**请求序号守卫**（乱序响应丢弃）；编辑时 node_id 仅变化才提交（幂等）+ 服务端业务错误 detail 透出（409 不再笼统"编辑失败"）；"URI 未在 views 出现"为路向误报（在 ProxyNodeManage，F 路审查）。

**F 路（前端接线）— 0 [P1] + 2 [P2]，全部修复**：
- [P2] showQrDialog 竞态（A 节点凭据可显示在 B 节点标题下）→ 请求序号守卫，过期响应丢弃。
- [P2] 关闭后凭据 URI 残留 → `destroy-on-close` + 关闭时清空 qrUri/qrTitle 并使在途请求失效。

**收敛轮（G/H 路）— 0 [P1] + 11 [P2]，GATE PASS，P2 全部顺手修复**：
- G 路（后端）7 项：`_recheck_node_bindable` 节点消失 → 404（防悬空外键 500）；行锁说明固化进注释（SQLite 无 FOR UPDATE，残余窗口为业务规则级风险；换库后替换为事务内行锁）；CREATE 审计补 remark 字段；`list_devices` 默认 fail-closed（is_super_admin 无默认值，显式传入）；`_is_node_unique_error` 优先结构化错误码（SQLITE_CONSTRAINT_UNIQUE 2067）消息子串兜底；list 路由捕获 DeviceServiceError 保留原状态码；bindable-nodes 的 exclude_device_id 指向已删除设备 → 404（对齐删除口径）。
- H 路（前端）4 项：日志分页页码参数处理（数字=切页，true=重置）；Element Plus clearable 的 undefined → null 归一化（解绑/不绑定语义正确）；列表加载失败清空旧结果（防跨查询残留）；创建失败透出服务端 detail（409 节点占用不再被笼统提示吞掉）。

## 终局验证（收敛修复后，全绿）

| 项 | 结果 |
|----|------|
| `compileall app tests` | ✅ 0 错误 |
| pytest | ✅ 37 passed（含并发绑定竞态、凭据泄露断言、审计保密断言、越权矩阵、软删除语义） |
| 覆盖率（本轮新增后端模块） | ✅ 84% |
| mypy（本轮 7 文件） | ✅ 0 错误 |
| `npm run build` | ✅ 通过 |
| 对抗审查 | ✅ 计划 4 轮 APPROVE；实施 6 路 + 收敛 2 路，最终 0 [P1]，P2 全部闭环 |

### UI 冒烟清单（交付后由用户在真实环境执行）

1. 启动后端 `run.py` + 前端 `npm run dev -- --host 0.0.0.0 --port 5174`。
2. 角色管理 → 给运营角色勾选"终端资产"组（device:view / device:manage）。
3. 终端资产页：新增设备（选所属人/绑定节点下拉只列空闲与使用中且未被占用）→ 详情页编辑/换绑/解绑/删除。
4. 历史轨迹：创建/更新/删除时间线完整，删除后列表不可见。
5. 非超管账号登录：仅见自己设备，无"所属人"筛选；操作他人设备被拒（403 提示）。
6. 超管在节点管理点"二维码"：扫码/复制 URI，Shadowrocket 导入验证；关闭对话框后无残留；操作日志出现"节点管理/VIEW_SECRET"。
7. 已售/禁用节点：二维码按钮点击后提示不可生成。

## 验证结果（第 2 轮修复后）

- pytest：24 passed ✅（新增 exclude_device_id 越权、字段白名单、保留字段注入回归）
- mypy（7 文件）：0 错误 ✅
- compileall：0 错误 ✅

## 延后登记

| 问题 | 理由 | 计划处理轮次 |
|------|------|-------------|
| 全库 mypy --strict（遗留 215 错误） | 既有代码历史债务 | 待定 |
| 全库测试覆盖率 | 既有模块无测试基础 | 待定 |
| 交付说明：旧角色需在角色管理勾选 device:view/device:manage | 权限矩阵为角色级配置 | 随交付 |
