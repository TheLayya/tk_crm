# 设计文档：多平台运营账号管理模块

## 概述

本模块在现有 TikTok 监控系统基础上，新增一个独立的**运营账号管理（Op Account Manager）**功能，用于替代团队使用 Excel 管理多平台运营账号的方式。

核心设计原则：
- **零侵入**：不修改任何现有表结构和 API，新增独立的表、路由和服务
- **最大复用**：复用现有 `Project`、`MonitorProxy` 模型和 `scraper_service` 的 TikTok 采集能力
- **渐进扩展**：当前仅支持 TikTok 采集，其他平台预留扩展点，标记"不支持"跳过

---

## 架构

```
┌─────────────────────────────────────────────────────────────┐
│                        前端 (Vue3)                           │
│  MonitorManage.vue                                           │
│  ├── 项目管理 tab (现有)                                      │
│  ├── 账号列表 tab (现有)                                      │
│  ├── 代理管理 tab (现有)                                      │
│  └── 运营账号 tab (新增)                                      │
│       └── OpAccountList.vue (新增)                           │
└─────────────────────────────────────────────────────────────┘
                          │ HTTP/REST
┌─────────────────────────────────────────────────────────────┐
│                       后端 (FastAPI)                          │
│  /api/op-accounts/*  (新增路由)                               │
│  /api/op-accounts/tasks/{task_id}  (进度查询)                 │
│                                                              │
│  OpAccountService (新增)                                     │
│  ├── CRUD 操作                                               │
│  ├── CSV 批量导入                                             │
│  └── 采集任务调度                                             │
│                                                              │
│  OpCollectorService (新增)                                   │
│  ├── TikTok: 复用 scraper_service.fetch_user_info            │
│  └── 其他平台: 标记"不支持"，跳过                              │
└─────────────────────────────────────────────────────────────┘
                          │ SQLAlchemy
┌─────────────────────────────────────────────────────────────┐
│                       数据库 (SQLite)                         │
│  op_accounts (新增)                                          │
│  op_collect_tasks (新增)                                     │
│  ── 复用 ──                                                  │
│  projects (现有)                                             │
│  monitor_proxies (现有)                                      │
└─────────────────────────────────────────────────────────────┘
```

### 异步采集架构

采集任务使用 Python `asyncio` + FastAPI 后台任务（`BackgroundTasks`）实现异步执行：

```
POST /api/op-accounts/collect  →  创建 task_id，立即返回
                                   │
                                   └→ BackgroundTask: run_collect_task(task_id, account_ids)
                                        ├── 逐个采集账号
                                        ├── 更新 op_collect_tasks 进度
                                        └── 完成后标记 task status = "completed"

GET /api/op-accounts/tasks/{task_id}  →  查询进度
```

---

## 组件与接口

### 后端组件

#### 1. 数据模型层 (`backend/app/models/op_account.py`)

新增两个 SQLAlchemy 模型：`OpAccount`、`OpCollectTask`

#### 2. Schema 层 (`backend/app/schemas/op_account.py`)

Pydantic schemas：`OpAccountCreate`、`OpAccountUpdate`、`OpAccountResponse`、`OpImportResult`、`CollectTaskResponse`

#### 3. 服务层 (`backend/app/services/op_account_service.py`)

- `create_op_account(db, data)` → 创建账号，触发采集，写入审计日志
- `update_op_account(db, id, data)` → 部分更新，写入审计日志（逐字段记录变更）
- `batch_update_status(db, ids, status, sale_info)` → 批量修改状态，写入审计日志
- `delete_op_account(db, id)` → 级联删除（含审计日志）
- `list_op_accounts(db, filters, skip, limit)` → 过滤分页查询（支持标签、采购渠道、出售客户过滤）
- `export_op_accounts(db, filters, format)` → 按过滤条件导出 CSV 或 Excel
- `import_from_csv(db, project_id, csv_content)` → CSV 批量导入
- `trigger_collect(db, account_ids, background_tasks)` → 触发异步采集
- `get_collect_task(db, task_id)` → 查询任务进度
- `get_audit_logs(db, account_id)` → 查询账号操作日志

#### 4. 采集器 (`backend/app/services/op_collector_service.py`)

- `collect_account(db, account, proxy)` → 单账号采集（分平台路由）
- `_collect_tiktok(account, proxy)` → 调用 `scraper_service.fetch_user_info`
- `_collect_unsupported(account)` → 标记"不支持"
- `select_proxy(db)` → 从代理池随机选取启用的 SOCKS 代理

#### 5. API 路由 (`backend/app/api/op_accounts.py`)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/op-accounts` | 列表查询（过滤+分页） |
| POST | `/api/op-accounts` | 创建单个账号 |
| PUT | `/api/op-accounts/{id}` | 更新账号 |
| DELETE | `/api/op-accounts/{id}` | 删除账号 |
| POST | `/api/op-accounts/batch-status` | 批量修改状态 |
| POST | `/api/op-accounts/import` | CSV 批量导入 |
| GET | `/api/op-accounts/export` | 导出（CSV/Excel，支持过滤参数） |
| POST | `/api/op-accounts/collect` | 触发批量采集 |
| GET | `/api/op-accounts/tasks/{task_id}` | 查询采集任务进度 |
| GET | `/api/op-accounts/{id}/logs` | 查询账号操作日志 |

### 前端组件

#### 1. `frontend/src/views/OpAccountList.vue` (新增)

运营账号列表主视图，包含：
- 过滤栏（平台、项目、状态、关键词）
- 可配置列的 el-table（支持列显示/隐藏）
- 内联编辑（手动维护字段）
- 批量操作工具栏
- 分页组件

#### 2. `frontend/src/api/op_accounts.js` (新增)

封装所有运营账号相关 API 调用。

#### 3. `frontend/src/components/Layout.vue` (修改)

在侧边栏菜单中新增"运营账号"菜单项（`/op-accounts`），与"监控管理"、"系统设置"并列。

#### 4. `frontend/src/router/index.js` (修改)

新增 `/op-accounts` 路由，指向 `OpAccountList.vue`。

---

## 数据模型

### `op_accounts` 表

```python
class OpAccount(Base):
    __tablename__ = "op_accounts"

    # 主键
    id = Column(Integer, primary_key=True, index=True)

    # 关联
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)

    # 平台
    platform = Column(SAEnum("tiktok", "youtube", "instagram", "facebook", name="op_platform_enum"), nullable=False, index=True)

    # 手动维护字段
    account = Column(String(255), nullable=False, index=True)   # 登录用户名/ID
    password = Column(String(255), nullable=True)
    totp_secret = Column(String(255), nullable=True)            # 2FA 密钥
    email = Column(String(255), nullable=True)                  # 绑定邮箱
    email_password = Column(String(255), nullable=True)         # 邮箱密码
    email_login_url = Column(String(512), nullable=True)        # 邮箱登录地址
    phone = Column(String(50), nullable=True)                   # 绑定手机号
    phone_manage_url = Column(String(512), nullable=True)       # 手机管理链接
    country = Column(String(100), nullable=True)                # 国家/地区
    source = Column(String(50), nullable=True)                  # 账号来源（self_register/purchase/other）
    tags = Column(Text, nullable=True)                          # 自定义标签（JSON 数组存储）
    remark = Column(Text, nullable=True)                        # 备注
    status = Column(
        SAEnum("正常", "自用", "封禁", "已售", name="op_status_enum"),
        default="正常", nullable=False, index=True
    )
    registrant = Column(String(100), nullable=True)             # 注册人
    operator = Column(String(100), nullable=True)               # 使用人

    # 采购字段
    purchase_channel = Column(String(255), nullable=True)       # 采购渠道
    purchase_price = Column(Numeric(10, 2), nullable=True)      # 采购金额
    purchase_date = Column(Date, nullable=True)                 # 采购日期
    maintenance_cost = Column(Numeric(10, 2), nullable=True)    # 养号成本

    # 出售字段
    sale_customer = Column(String(255), nullable=True)          # 出售客户
    sale_price = Column(Numeric(10, 2), nullable=True)          # 出售金额
    sale_date = Column(Date, nullable=True)                     # 出售日期
    tiktok_mid_video = Column(Boolean, nullable=True)           # 是否开通中视频
    tiktok_showcase = Column(Boolean, nullable=True)            # 是否开通橱窗
    tiktok_phone_live = Column(Boolean, nullable=True)          # 手机直播权限
    tiktok_partner_live = Column(Boolean, nullable=True)        # 伴侣直播权限

    # 采集字段
    platform_user_id = Column(String(255), nullable=True)       # 平台用户 ID
    platform_sec_uid = Column(String(512), nullable=True)       # 平台安全 UID
    nickname = Column(String(255), nullable=True)               # 昵称
    avatar_url = Column(String(1024), nullable=True)            # 头像 URL
    follower_count = Column(BigInteger, nullable=True)          # 粉丝数
    following_count = Column(BigInteger, nullable=True)         # 关注数
    like_count = Column(BigInteger, nullable=True)              # 点赞数
    video_count = Column(BigInteger, nullable=True)             # 视频数
    account_created_at = Column(DateTime, nullable=True)        # 账号注册时间
    last_collected_at = Column(DateTime, nullable=True)         # 最近采集时间
    collect_status = Column(
        SAEnum("pending", "success", "failed", "unsupported", name="op_collect_status_enum"),
        default="pending", nullable=False
    )
    collect_error = Column(Text, nullable=True)                 # 采集错误信息

    # 系统字段
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # 关系
    project = relationship("Project", foreign_keys=[project_id])

    # 唯一约束：同一项目下，同一平台+账号名唯一
    __table_args__ = (
        UniqueConstraint("project_id", "platform", "account", name="uq_op_account_project_platform_account"),
    )
```

### `op_collect_tasks` 表

```python
class OpCollectTask(Base):
    __tablename__ = "op_collect_tasks"

    id = Column(String(36), primary_key=True)  # UUID
    status = Column(
        SAEnum("running", "completed", "failed", name="op_task_status_enum"),
        default="running", nullable=False
    )
    total = Column(Integer, default=0, nullable=False)
    completed = Column(Integer, default=0, nullable=False)
    success = Column(Integer, default=0, nullable=False)
    failed = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
```

### `op_audit_logs` 表

```python
class OpAuditLog(Base):
    __tablename__ = "op_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    op_account_id = Column(Integer, ForeignKey("op_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    action = Column(String(50), nullable=False)         # create / update / delete
    field_name = Column(String(100), nullable=True)     # 变更字段名（批量更新时可为 None）
    old_value = Column(Text, nullable=True)             # 变更前值
    new_value = Column(Text, nullable=True)             # 变更后值
    operator = Column(String(100), nullable=True)       # 操作人（预留，当前记录 IP 或固定值）
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
```

### 唯一性约束

`(project_id, platform, account)` 三元组唯一，防止同一项目下同平台重复账号。

### 与现有模型的关系

- `op_accounts.project_id` → `projects.id`（复用现有 Project 模型，CASCADE 删除）
- 采集时通过 `monitor_proxies` 表查询可用代理（复用现有 MonitorProxy 模型）

---

## 正确性属性

*属性（Property）是在系统所有合法执行中都应成立的特征或行为——本质上是对系统应该做什么的形式化陈述。属性是人类可读规范与机器可验证正确性保证之间的桥梁。*

### 属性 1：账号数据 round-trip

*对于任意*合法的运营账号数据（包含所有手动维护字段），创建后通过 ID 查询，返回的数据应与创建时提交的数据完全一致。

**验证：需求 1.1、2.1**

---

### 属性 2：平台枚举合法性

*对于任意*合法平台值（tiktok/youtube/instagram/facebook），创建账号应该成功；*对于任意*非法平台值，创建应该失败并返回验证错误。

**验证：需求 1.5**

---

### 属性 3：项目唯一性约束

*对于任意*运营账号，在同一项目下使用相同平台和相同账号名创建第二次，应该返回 409 冲突错误，且数据库中只存在一条记录。

**验证：需求 2.2**

---

### 属性 4：部分更新不影响其他字段

*对于任意*运营账号和任意字段子集，执行部分更新后，未包含在更新请求中的字段值应与更新前完全相同。

**验证：需求 2.3**

---

### 属性 5：删除级联清理

*对于任意*有采集任务历史的运营账号，删除该账号后，相关的采集任务记录也应被清理，不留孤立数据。

**验证：需求 2.4**

---

### 属性 6：过滤结果一致性

*对于任意*过滤条件（平台、项目、状态、关键词），列表查询返回的每一条记录都应满足该过滤条件，且满足条件的记录不会被遗漏。

**验证：需求 2.5**

---

### 属性 7：CSV 导入汇总数字一致性

*对于任意* CSV 输入（包含任意比例的有效行、重复行、无效行），导入结果中 `total = success + duplicates + failed` 恒成立。

**验证：需求 3.4**

---

### 属性 8：CSV 导入错误隔离

*对于任意*包含部分无效行的 CSV，有效行应该被成功创建，无效行的失败不影响有效行的导入结果。

**验证：需求 3.2**

---

### 属性 9：重复导入幂等性

*对于任意*已存在的运营账号，通过 CSV 重复导入相同数据后，该账号的字段值应与导入前完全相同（不被覆盖），且被标记为"重复"。

**验证：需求 3.3**

---

### 属性 10：采集失败不覆盖已有数据

*对于任意*已有采集数据的运营账号，当采集失败时，原有的采集字段（user_id、sec_uid、粉丝数等）应保持不变，仅 `collect_status` 更新为"failed"，`collect_error` 记录错误信息。

**验证：需求 4.3**

---

### 属性 11：代理选取合法性

*对于任意*代理池状态（含启用/禁用代理的任意组合），采集时选取的代理应始终是 `is_active=True` 的代理；若代理池中无启用代理，则 `select_proxy` 返回 `None`。

**验证：需求 4.4、4.5**

---

### 属性 12：非 TikTok 平台采集跳过

*对于任意*平台为 youtube、instagram 或 facebook 的运营账号，触发采集后，`collect_status` 应被标记为"unsupported"，不产生错误，不修改其他字段。

**验证：需求 4.7**

---

### 属性 13：批量采集进度数字一致性

*对于任意*批量采集任务，在任意时刻查询进度，`completed = success + failed` 恒成立，且 `completed <= total`。

**验证：需求 5.3**

---

### 属性 14：密码明文 round-trip

*对于任意*密码字符串，存储到 `op_accounts` 后读取，应得到与存储时完全相同的明文字符串。

**验证：需求 7.3**

---

## 错误处理

| 场景 | HTTP 状态码 | 错误信息 |
|------|------------|---------|
| 缺少必填字段（platform、account、project_id） | 422 | 字段验证错误详情 |
| 同项目下平台+账号名重复 | 409 | "账号已存在于该项目" |
| 账号 ID 不存在 | 404 | "账号不存在" |
| project_id 不存在 | 404 | "项目不存在" |
| 采集任务 ID 不存在 | 404 | "任务不存在" |
| 账号正在采集中，重复触发 | 409 | "账号正在采集中，请稍后再试" |
| CSV 格式错误（无法解析） | 400 | "CSV 格式错误" |
| 采集失败（网络/代理） | — | 记录到 `collect_error`，不抛出 HTTP 错误 |

### 采集错误处理策略

采集失败属于业务层错误，不向前端抛出 HTTP 异常，而是：
1. 将 `collect_status` 更新为 `"failed"`
2. 将错误信息写入 `collect_error` 字段
3. 保留已有采集字段不变
4. 任务进度中 `failed` 计数 +1

---

## 测试策略

### 测试框架选择

- **后端属性测试**：[Hypothesis](https://hypothesis.readthedocs.io/)（Python PBT 库）
- **后端单元/集成测试**：pytest + pytest-asyncio
- **前端测试**：Vitest（单元测试）

### 属性测试配置

每个属性测试最少运行 **100 次迭代**（Hypothesis 默认），通过 `@settings(max_examples=100)` 配置。

每个属性测试使用注释标注对应设计属性：
```python
# Feature: multi-platform-account-management, Property 3: 项目唯一性约束
@given(account_data=st.builds(...))
@settings(max_examples=100)
def test_duplicate_account_rejected(account_data):
    ...
```

### 属性测试实现

针对上述 14 个属性，使用 Hypothesis 实现：

**属性 1（数据 round-trip）**：
```python
@given(st.builds(OpAccountCreate, 
    platform=st.sampled_from(["tiktok", "youtube", "instagram", "facebook"]),
    account=st.text(min_size=1, max_size=100),
    ...))
def test_account_data_roundtrip(data):
    created = service.create_op_account(db, data)
    fetched = service.get_op_account(db, created.id)
    assert fetched.account == data.account
    assert fetched.platform == data.platform
    # ... 验证所有字段
```

**属性 7（CSV 汇总数字一致性）**：
```python
@given(rows=st.lists(st.one_of(valid_row(), invalid_row(), duplicate_row())))
def test_import_summary_consistency(rows):
    result = service.import_from_csv(db, project_id, to_csv(rows))
    assert result.total == result.success + result.duplicates + result.failed
```

**属性 11（代理选取合法性）**：
```python
@given(proxies=st.lists(st.builds(MockProxy, is_active=st.booleans())))
def test_proxy_selection_always_active(proxies):
    selected = collector.select_proxy_from_list(proxies)
    if selected is not None:
        assert selected.is_active == True
    else:
        assert all(not p.is_active for p in proxies)
```

### 单元测试覆盖

- 创建账号时自动触发采集（mock BackgroundTasks）
- TikTok 采集调用 `scraper_service.fetch_user_info`（mock）
- 非 TikTok 平台采集返回"不支持"
- 正在采集的账号拒绝重复采集请求
- 前端密码掩码显示/切换逻辑

### 集成测试

- 完整的 CSV 导入流程（含文件上传）
- 批量采集任务的异步执行和进度查询
- 与现有 Project 和 MonitorProxy 的关联查询
