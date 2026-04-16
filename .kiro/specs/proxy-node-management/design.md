# 技术设计文档：节点管理模块（proxy-node-management）

## 概述

本模块是一个**全新独立的节点管理系统**，作为独立侧边菜单项集成到现有 TikTok Monitor 平台中。系统面向团队运营人员，用于管理代理节点资产，包括原始节点信息、中转信息、采购/出售信息、连通性测试及成本收益统计。

本模块与现有监控代理管理模块（`MonitorProxy` / `monitor_proxies` 表）**完全独立**，拥有独立的数据表 `proxy_nodes`、独立的服务层、独立的 API 路由和独立的前端视图，不修改任何现有代码。

### 技术栈

- **后端**：Python 3.11 + FastAPI + SQLAlchemy 2.x + SQLite（Alembic 迁移）
- **前端**：Vue 3 + Vite + Element Plus
- **文件处理**：`pandas` + `openpyxl`（CSV/Excel 导入导出）
- **HTTP 测试**：`httpx`（异步，复用现有依赖）
- **并发控制**：`asyncio.Semaphore`

---

## 架构

### 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                        前端（Vue 3）                         │
│  frontend/src/views/ProxyNodeManage.vue                     │
│  frontend/src/api/proxy_nodes.js                            │
│  frontend/src/router/index.js（新增路由 /proxy-nodes）       │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP REST API
┌──────────────────────────▼──────────────────────────────────┐
│                    后端 FastAPI 路由层                        │
│  backend/app/api/proxy_nodes.py                             │
│  前缀：/api/proxy-nodes                                      │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                      服务层                                  │
│  backend/app/services/proxy_node_service.py                 │
│  backend/app/services/proxy_node_import_service.py          │
│  backend/app/services/proxy_node_export_service.py          │
│  backend/app/services/proxy_node_test_service.py            │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                    数据层                                    │
│  backend/app/models/proxy_node.py（ProxyNode 模型）          │
│  backend/app/schemas/proxy_node.py（Pydantic Schema）        │
│  backend/alembic/versions/YYYYMMDD_0001_add_proxy_nodes.py  │
└─────────────────────────────────────────────────────────────┘
```

### 与现有系统的关系

```
现有系统（不修改）                    新模块（独立新增）
─────────────────────                ──────────────────────
monitor_proxies 表                   proxy_nodes 表
MonitorProxy 模型                    ProxyNode 模型
proxy_service.py                     proxy_node_service.py
/api/proxies 路由                    /api/proxy-nodes 路由
ProxyManage.vue                      ProxyNodeManage.vue
```

---

## 组件与接口

### 后端组件

#### 1. 数据模型（`backend/app/models/proxy_node.py`）

新建 `ProxyNode` SQLAlchemy 模型，映射到 `proxy_nodes` 表。

#### 2. Pydantic Schema（`backend/app/schemas/proxy_node.py`）

定义请求/响应的数据验证模型：
- `ProxyNodeCreate`：创建节点请求体
- `ProxyNodeUpdate`：更新节点请求体（所有字段可选，PATCH 语义）
- `ProxyNodeResponse`：节点响应体
- `ProxyNodeFilter`：筛选参数
- `ProxyNodeImportResult`：导入结果
- `ProxyNodeTestResult`：单节点测试结果
- `ProxyNodeBatchTestResult`：批量测试结果
- `ProxyNodeStats`：统计结果

#### 3. API 路由（`backend/app/api/proxy_nodes.py`）

路由前缀：`/api/proxy-nodes`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 查询节点列表（支持分页和筛选） |
| POST | `/` | 创建单个节点 |
| GET | `/{node_id}` | 查询单个节点 |
| PATCH | `/{node_id}` | 更新节点（部分更新） |
| DELETE | `/{node_id}` | 删除单个节点 |
| DELETE | `/batch` | 批量删除节点 |
| PATCH | `/batch/status` | 批量修改状态 |
| POST | `/{node_id}/test` | 测试单个节点连通性 |
| POST | `/batch/test` | 批量测试节点连通性 |
| POST | `/import` | 批量导入（CSV/Excel） |
| GET | `/import/template` | 下载导入模板 |
| GET | `/export` | 导出节点数据（CSV/Excel） |
| GET | `/stats` | 获取统计数据 |

#### 4. 服务层

**`proxy_node_service.py`**：核心 CRUD 逻辑
- `get_nodes(db, filter, skip, limit)` → 带筛选的分页查询
- `get_node(db, node_id)` → 按 ID 查询
- `create_node(db, data)` → 创建节点
- `update_node(db, node_id, data)` → 部分更新
- `delete_node(db, node_id)` → 删除
- `batch_delete_nodes(db, node_ids)` → 批量删除
- `batch_update_status(db, node_ids, status)` → 批量修改状态
- `get_stats(db, filter)` → 统计计算

**`proxy_node_import_service.py`**：导入逻辑
- `import_from_csv(db, file_content)` → 解析 CSV 并导入
- `import_from_excel(db, file_content)` → 解析 Excel 并导入
- `generate_template_csv()` → 生成模板 CSV
- `_validate_row(row, line_num)` → 行数据验证

**`proxy_node_export_service.py`**：导出逻辑
- `export_to_csv(nodes)` → 序列化为 CSV bytes
- `export_to_excel(nodes)` → 序列化为 Excel bytes

**`proxy_node_test_service.py`**：连通性测试
- `test_node(db, node_id)` → 测试单个节点
- `batch_test_nodes(db, node_ids)` → 并发批量测试（最大并发 10）
- `_do_test(node)` → 实际发起 HTTP 请求

#### 5. 数据库迁移

新建迁移文件：`backend/alembic/versions/YYYYMMDD_0001_add_proxy_nodes.py`

#### 6. 注册路由

在 `backend/app/main.py` 中新增一行（不修改其他内容）：
```python
from app.api import proxy_nodes
app.include_router(proxy_nodes.router, prefix="/api")
```

### 前端组件

#### 1. API 模块（`frontend/src/api/proxy_nodes.js`）

封装所有后端接口调用。

#### 2. 视图组件（`frontend/src/views/ProxyNodeManage.vue`）

主视图，包含：
- 统计面板（顶部卡片）
- 筛选栏
- 节点数据表格（支持多选）
- 批量操作工具栏
- 添加/编辑节点对话框
- 导入对话框
- 导出对话框

#### 3. 路由注册（`frontend/src/router/index.js`）

新增路由：
```javascript
{
  path: '/proxy-nodes',
  name: 'ProxyNodeManage',
  component: () => import('../views/ProxyNodeManage.vue'),
  meta: { requiresAuth: true, breadcrumb: '节点管理' }
}
```

#### 4. 侧边菜单（`frontend/src/components/Layout.vue`）

在侧边菜单中新增"节点管理"菜单项（在"运营账号"之后）。

---

## 数据模型

### `proxy_nodes` 表结构

```python
class ProxyNode(Base):
    __tablename__ = "proxy_nodes"

    # 主键
    id = Column(Integer, primary_key=True, index=True)

    # 原始节点信息（ip + port 必填）
    ip       = Column(String(255), nullable=False)
    port     = Column(Integer, nullable=False)
    username = Column(String(255), nullable=True)
    password = Column(String(255), nullable=True)
    protocol = Column(
        SAEnum("socks5", "http", "https", name="proxy_node_protocol_enum"),
        nullable=False, default="socks5"
    )

    # 中转节点信息（全部可选）
    relay_ip       = Column(String(255), nullable=True)
    relay_port     = Column(Integer, nullable=True)
    relay_protocol = Column(
        SAEnum("socks5", "http", "https", name="proxy_node_relay_protocol_enum"),
        nullable=True
    )

    # 采购信息（全部可选）
    purchase_date    = Column(Date, nullable=True)
    purchase_price   = Column(Numeric(10, 2), nullable=True)
    purchase_channel = Column(String(255), nullable=True)
    expire_date      = Column(Date, nullable=True)

    # 出售信息（全部可选）
    sale_customer = Column(String(255), nullable=True)
    sale_price    = Column(Numeric(10, 2), nullable=True)

    # 状态字段
    status = Column(
        SAEnum("active", "expired", "sold", "disabled", name="proxy_node_status_enum"),
        nullable=False, default="active"
    )
    usage = Column(
        SAEnum("self", "rented", "idle", name="proxy_node_usage_enum"),
        nullable=False, default="idle"
    )

    # 测试字段
    last_test_at      = Column(DateTime, nullable=True)
    last_test_result  = Column(
        SAEnum("success", "failed", name="proxy_node_test_result_enum"),
        nullable=True
    )
    last_test_latency = Column(Integer, nullable=True)  # 毫秒

    # 备注
    remark = Column(Text, nullable=True)

    # 系统字段
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
```

**索引设计**：
- `id`：主键索引（自动）
- `status`：单列索引（筛选高频字段）
- `usage`：单列索引
- `expire_date`：单列索引（范围查询）
- `purchase_channel`：单列索引（模糊搜索）

### Pydantic Schema 设计

```python
# 创建请求
class ProxyNodeCreate(BaseModel):
    ip: str
    port: int = Field(..., ge=1, le=65535)
    username: Optional[str] = None
    password: Optional[str] = None
    protocol: Literal["socks5", "http", "https"] = "socks5"
    relay_ip: Optional[str] = None
    relay_port: Optional[int] = Field(None, ge=1, le=65535)
    relay_protocol: Optional[Literal["socks5", "http", "https"]] = None
    purchase_date: Optional[date] = None
    purchase_price: Optional[Decimal] = None
    purchase_channel: Optional[str] = None
    expire_date: Optional[date] = None
    sale_customer: Optional[str] = None
    sale_price: Optional[Decimal] = None
    status: Literal["active", "expired", "sold", "disabled"] = "active"
    usage: Literal["self", "rented", "idle"] = "idle"
    remark: Optional[str] = None

# 更新请求（所有字段可选）
class ProxyNodeUpdate(BaseModel):
    ip: Optional[str] = None
    port: Optional[int] = Field(None, ge=1, le=65535)
    # ... 其余字段同 Create，全部 Optional

# 响应体
class ProxyNodeResponse(BaseModel):
    id: int
    ip: str
    port: int
    username: Optional[str]
    password: Optional[str]  # 返回原始值，前端负责掩码显示
    protocol: str
    relay_ip: Optional[str]
    relay_port: Optional[int]
    relay_protocol: Optional[str]
    purchase_date: Optional[date]
    purchase_price: Optional[Decimal]
    purchase_channel: Optional[str]
    expire_date: Optional[date]
    sale_customer: Optional[str]
    sale_price: Optional[Decimal]
    status: str
    usage: str
    last_test_at: Optional[datetime]
    last_test_result: Optional[str]
    last_test_latency: Optional[int]
    remark: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# 筛选参数
class ProxyNodeFilter(BaseModel):
    status: Optional[List[str]] = None          # 多值
    usage: Optional[List[str]] = None           # 多值
    protocol: Optional[List[str]] = None        # 多值
    purchase_channel: Optional[str] = None      # 模糊搜索
    sale_customer: Optional[str] = None         # 模糊搜索
    expire_date_from: Optional[date] = None
    expire_date_to: Optional[date] = None

# 统计结果
class ProxyNodeStats(BaseModel):
    total: int
    by_status: Dict[str, int]   # {"active": N, "expired": N, ...}
    by_usage: Dict[str, int]    # {"self": N, "rented": N, "idle": N}
    total_purchase_cost: Decimal
    total_sale_revenue: Decimal
    net_profit: Decimal
    by_channel: List[ChannelStats]  # 按渠道分组

class ChannelStats(BaseModel):
    channel: str
    count: int
    total_cost: Decimal
```

---

## 正确性属性

*属性（Property）是在系统所有有效执行中都应成立的特征或行为——本质上是对系统应做什么的形式化陈述。属性是人类可读规范与机器可验证正确性保证之间的桥梁。*

### 属性 1：节点数据 Round-Trip 完整性

*对于任意*有效的节点创建数据（包含所有可选字段），创建节点后按 ID 查询，返回的所有字段值应与输入数据完全一致。

**验证：需求 1.2、1.3、1.4、1.5、1.6、1.7、1.8、2.1、2.3**

### 属性 2：分页查询结果数量约束

*对于任意*节点集合和任意合法的分页参数（skip ≥ 0，1 ≤ limit ≤ 500），查询返回的节点数量应满足：`len(result) <= limit`，且当 `skip < total` 时 `len(result) > 0`。

**验证：需求 2.2**

### 属性 3：部分更新不影响未指定字段

*对于任意*节点和任意字段子集的更新操作，更新后未被指定的字段值应与更新前完全相同，被指定的字段值应等于更新请求中的值。

**验证：需求 2.5**

### 属性 4：更新操作自动刷新 updated_at

*对于任意*节点的任意更新操作，更新后的 `updated_at` 值应大于等于更新前的 `updated_at` 值。

**验证：需求 2.8**

### 属性 5：筛选结果满足所有筛选条件（AND 逻辑）

*对于任意*节点集合和任意筛选条件组合，返回的每个节点都应满足所有指定的筛选条件，且不存在满足所有条件但未被返回的节点。

**验证：需求 3.1、3.2、3.3、3.4、3.5、3.6、3.7**

### 属性 6：导入-导出 Round-Trip 数据一致性

*对于任意*有效节点数据集合，将其序列化为 CSV 或 Excel 文件后再导入，所有有效行的字段值应与原始数据完全一致。

**验证：需求 4.1、4.2、4.3、5.1、5.2、5.3**

### 属性 7：导入部分失败不中止整批处理

*对于任意*包含 N 个有效行和 M 个无效行（M ≥ 1）的导入文件，导入结果应满足：`success_count = N`，`fail_count = M`，且 `errors` 列表长度等于 M，每条错误信息包含对应的行号。

**验证：需求 4.4、4.5、4.6、4.7、4.8**

### 属性 8：导出筛选结果仅包含满足条件的节点

*对于任意*节点集合和任意筛选条件，导出文件中的每个节点都应满足所有指定的筛选条件。

**验证：需求 5.4**

### 属性 9：测试结果字段与测试结论一致

*对于任意*节点，执行连通性测试后，数据库中的 `last_test_result`、`last_test_latency`、`last_test_at` 字段应与测试实际结论一致：成功时 `last_test_result = "success"` 且 `last_test_latency` 为正整数；失败时 `last_test_result = "failed"` 且 `last_test_latency` 为空。

**验证：需求 6.2、6.3、6.4**

### 属性 10：有中转信息时优先使用中转地址测试

*对于任意*同时具有原始地址和中转地址（`relay_ip` 和 `relay_port` 均不为空）的节点，连通性测试时实际使用的代理地址应为中转地址，而非原始地址。

**验证：需求 6.6**

### 属性 11：批量测试并发数不超过上限

*对于任意*数量 N > 10 的节点批量测试请求，任意时刻同时进行的测试数量不超过 10。

**验证：需求 6.7**

### 属性 12：批量测试结果汇总数量守恒

*对于任意*节点 ID 列表的批量测试，返回汇总中 `success_count + fail_count` 应等于请求的节点 ID 数量。

**验证：需求 6.8**

### 属性 13：统计数量守恒

*对于任意*节点集合，统计结果中各状态数量之和应等于总节点数，各 usage 数量之和也应等于总节点数。

**验证：需求 7.1**

### 属性 14：成本收益计算正确性

*对于任意*节点集合，统计结果应满足：
- `total_purchase_cost` = 所有 `purchase_price` 非空节点的 `purchase_price` 之和
- `total_sale_revenue` = 所有 `sale_price` 非空节点的 `sale_price` 之和
- `net_profit` = `total_sale_revenue` - `total_purchase_cost`

**验证：需求 7.2、7.3、7.4**

### 属性 15：到期日期高亮逻辑正确性

*对于任意* `expire_date` 值，前端高亮判断函数应满足：当 `expire_date` 距当前日期不足 7 天（含今天）时返回高亮样式，否则返回正常样式。

**验证：需求 8.12**

---

## 错误处理

### HTTP 错误码规范

| 场景 | HTTP 状态码 | 响应体格式 |
|------|------------|-----------|
| 节点 ID 不存在 | 404 | `{"detail": "Node {id} not found"}` |
| 请求体验证失败（如 port 超范围） | 422 | FastAPI 默认 ValidationError 格式 |
| 导入文件格式不支持 | 400 | `{"detail": "Unsupported file format. Use .csv or .xlsx"}` |
| 导入文件解析失败 | 400 | `{"detail": "Failed to parse file: {reason}"}` |
| 服务器内部错误 | 500 | `{"detail": "Internal server error"}` |

### 导入错误处理策略

- 逐行处理，单行错误不中止整批
- 错误信息格式：`"第 {行号} 行: {原因}"`（例：`"第 3 行: port 必须是 1-65535 之间的整数"`）
- 枚举值错误格式：`"第 {行号} 行: {字段名} 值 '{值}' 不合法，允许值为 {允许值列表}"`

### 连通性测试错误处理

- 超时（15 秒）：记录为失败，`error` 字段填写 `"Connection timeout"`
- 代理连接失败：记录为失败，`error` 字段填写具体错误信息（截断至 200 字符）
- 节点不存在：返回 HTTP 404，不执行测试

### 前端错误处理

- API 请求失败：通过 `ElMessage.error()` 显示错误提示
- 表单验证失败：Element Plus 内置表单验证，字段级别错误提示
- 导入结果展示：成功/失败数量摘要 + 失败详情可展开查看

---

## 测试策略

### 单元测试

使用 `pytest` + `pytest-asyncio`，测试文件位于 `backend/tests/test_proxy_node_*.py`。

**测试重点**：
- 服务层函数的具体行为（创建、更新、删除、筛选）
- 导入解析逻辑（各种边界情况：空字段、非法枚举、端口越界）
- 导出序列化逻辑（字段完整性、文件格式正确性）
- 统计计算逻辑（空数据集、部分字段为空）
- 到期日期高亮判断函数

### 属性测试

使用 `hypothesis` 库（Python 属性测试标准库），每个属性测试运行最少 100 次迭代。

测试文件：`backend/tests/test_proxy_node_properties.py`

每个属性测试用注释标注对应的设计属性：
```python
# Feature: proxy-node-management, Property 1: 节点数据 Round-Trip 完整性
@given(node_data=st.builds(ProxyNodeCreate, ...))
@settings(max_examples=100)
def test_node_round_trip(node_data):
    ...
```

**属性测试覆盖**：
- 属性 1：节点 Round-Trip（使用 `hypothesis` 生成随机节点数据）
- 属性 2：分页约束（生成随机节点数量和分页参数）
- 属性 3：部分更新隔离性（生成随机节点和随机更新字段子集）
- 属性 4：`updated_at` 自动更新
- 属性 5：筛选结果正确性（生成随机节点集合和筛选条件）
- 属性 6：导入导出 Round-Trip（生成随机节点数据，序列化后导入）
- 属性 7：导入部分失败处理（生成混合有效/无效行的数据）
- 属性 8：导出筛选正确性
- 属性 9：测试结果字段一致性（mock 网络请求）
- 属性 10：中转地址优先（mock 网络请求，验证使用的代理 URL）
- 属性 11：并发数上限（mock 网络请求，记录并发峰值）
- 属性 12：批量测试数量守恒
- 属性 13：统计数量守恒
- 属性 14：成本收益计算正确性
- 属性 15：到期日期高亮逻辑（纯函数，无需 mock）

### 集成测试

- 连通性测试的实际网络行为（使用真实代理节点，少量示例）
- 导入/导出文件的完整流程（端到端）

### 前端测试

- 到期日期高亮工具函数的单元测试（Vitest）
- 密码掩码切换行为的组件测试（Vue Test Utils）
