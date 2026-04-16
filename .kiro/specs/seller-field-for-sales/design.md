# 设计文档：出售人字段（seller-field-for-sales）

## 概述

本功能为 `op_accounts`（运营账号）和 `proxy_nodes`（代理节点）两张表的出售信息区域新增 `sellers` 字段，用于记录"谁负责了这笔出售"。`sellers` 支持多选，存储为 JSON 数组（`["alice", "bob"]`），选项来源于系统现有的团队成员（`users` 表）。

### 设计目标

- 最小侵入：仅在现有出售信息字段旁追加一列，不改变已有字段语义
- 宽松验证：允许存储不存在于 `users` 表的 username，保证历史数据兼容
- 前后端一致：后端以 `List[str]` 传输，前端以 `string[]` 传输，序列化/反序列化在服务层完成

---

## 架构

本功能横跨四层，每层改动均为增量式：

```
前端 Vue 3 (Element Plus)
  └─ SellerSelector 组件（新增）
  └─ OpAccountList.vue / ProxyNodeManage.vue（修改：表单 + 列表列）
        │  HTTP JSON
后端 FastAPI
  └─ Schema 层（新增 sellers 字段）
  └─ Service 层（JSON 序列化/反序列化）
  └─ API 层（batch-status 接口扩展）
        │  SQLAlchemy ORM
数据库 SQLite（通过 Alembic 迁移）
  └─ op_accounts.sellers  TEXT NULL
  └─ proxy_nodes.sellers  TEXT NULL
```

### 数据流

```
用户选择出售人
  → 前端 SellerSelector 收集 username[]
  → 表单提交时序列化为 JSON 字符串（或直接传 List）
  → 后端 Schema 接收 Optional[List[str]]
  → Service 层将 List[str] 序列化为 JSON 字符串存入 TEXT 列
  → 查询时反序列化 JSON 字符串为 List[str] 返回给前端
  → 前端列表列展示出售人名称
```

---

## 组件与接口

### 后端组件

#### 1. 数据模型层（`models/`）

**`OpAccount` 模型**（`backend/app/models/op_account.py`）：
- 新增列：`sellers = Column(Text, nullable=True)`
- 存储格式：JSON 字符串，如 `'["alice", "bob"]'`，空时为 `NULL` 或 `'[]'`

**`ProxyNode` 模型**（`backend/app/models/proxy_node.py`）：
- 新增列：`sellers = Column(Text, nullable=True)`
- 存储格式：同上

#### 2. Schema 层（`schemas/`）

**`OpAccountCreate` / `OpAccountUpdate` / `OpAccountResponse`**（`backend/app/schemas/op_account.py`）：
- 新增字段：`sellers: Optional[List[str]] = None`
- `OpAccountResponse` 中 `sellers` 始终返回列表（`None` 转为 `[]`）

**`ProxyNodeCreate` / `ProxyNodeUpdate` / `ProxyNodeResponse`**（`backend/app/schemas/proxy_node.py`）：
- 新增字段：`sellers: Optional[List[str]] = None`
- 同上

**`BatchStatusUpdate`**（`backend/app/schemas/op_account.py`）：
- 新增字段：`sellers: Optional[List[str]] = None`

#### 3. 服务层（`services/`）

**`op_account_service.py`**：
- `create_op_account`：将 `data.sellers`（`List[str]`）序列化为 JSON 字符串后存入模型
- `update_op_account`：同上，支持 PATCH 语义（未传则不修改）
- `batch_update_status`：当 `sellers` 参数不为 `None` 时，更新所有目标账号的 `sellers` 字段
- 新增辅助函数 `_serialize_sellers(sellers: Optional[List[str]]) -> Optional[str]`
- 新增辅助函数 `_deserialize_sellers(value: Optional[str]) -> List[str]`

**`proxy_node_service.py`**：
- `create_node` / `update_node`：同上，处理 `sellers` 字段的序列化

#### 4. API 层（`api/`）

**`op_accounts.py`**：
- `batch_update_status` 端点：透传 `data.sellers` 到服务层

**`proxy_nodes.py`**：
- 无需修改（`create_node` / `update_node` 已通过 Schema 透传）

### 前端组件

#### 1. `SellerSelector` 组件（新增）

**路径**：`frontend/src/components/SellerSelector.vue`

**职责**：
- 从 `/team/member` 接口加载团队成员列表
- 渲染 Element Plus `<el-select multiple>` 多选下拉框
- 选项展示格式：`真实姓名（用户名）`，若无真实姓名则仅展示用户名
- 支持 `v-model`（值为 `string[]`，存储 username）
- 加载失败时展示错误提示，提供重试按钮

**Props**：
```typescript
modelValue: string[]   // 已选 username 列表
placeholder?: string   // 默认"选择出售人"
disabled?: boolean
```

**Emits**：
```typescript
update:modelValue: (value: string[]) => void
```

#### 2. `OpAccountList.vue`（修改）

- 编辑/新增表单的"出售信息"区域：添加 `<SellerSelector v-model="form.sellers" />`
- 批量状态更新对话框：添加 `<SellerSelector v-model="batchForm.sellers" />`
- 列表表格：在出售信息相关列（如"出售客户"列旁）展示出售人，多个以逗号分隔或 `<el-tag>` 形式展示
- 数据加载时将后端返回的 `sellers`（`string[]`）直接绑定到表单

#### 3. `ProxyNodeManage.vue`（修改）

- 编辑/新增表单的"出售信息"区域：添加 `<SellerSelector v-model="form.sellers" />`
- 列表表格：在出售信息相关列展示出售人

---

## 数据模型

### 数据库列定义

```sql
-- op_accounts 表
ALTER TABLE op_accounts ADD COLUMN sellers TEXT NULL DEFAULT NULL;

-- proxy_nodes 表
ALTER TABLE proxy_nodes ADD COLUMN sellers TEXT NULL DEFAULT NULL;
```

### 存储格式

| 场景 | 数据库存储值 | API 响应值 |
|------|------------|-----------|
| 未设置出售人 | `NULL` | `[]` |
| 一个出售人 | `'["alice"]'` | `["alice"]` |
| 多个出售人 | `'["alice", "bob"]'` | `["alice", "bob"]` |

### 序列化辅助函数

```python
import json
from typing import List, Optional

def _serialize_sellers(sellers: Optional[List[str]]) -> Optional[str]:
    """将 Python 列表序列化为 JSON 字符串存入数据库。空列表存为 '[]'，None 存为 NULL。"""
    if sellers is None:
        return None
    return json.dumps(sellers, ensure_ascii=False)

def _deserialize_sellers(value: Optional[str]) -> List[str]:
    """将数据库中的 JSON 字符串反序列化为 Python 列表。NULL 或空值返回空列表。"""
    if not value:
        return []
    try:
        result = json.loads(value)
        return result if isinstance(result, list) else []
    except (json.JSONDecodeError, TypeError):
        return []
```

### Schema 字段定义

```python
# OpAccountCreate / OpAccountUpdate / ProxyNodeCreate / ProxyNodeUpdate
sellers: Optional[List[str]] = None

# OpAccountResponse / ProxyNodeResponse（始终返回列表）
sellers: List[str] = []
```

### Alembic 迁移脚本

**文件名**：`backend/alembic/versions/20260602_0001_add_sellers_to_op_accounts_and_proxy_nodes.py`

```python
revision = '20260602_0001'
down_revision = '20260601_0001'

def upgrade():
    op.add_column('op_accounts', sa.Column('sellers', sa.Text(), nullable=True))
    op.add_column('proxy_nodes', sa.Column('sellers', sa.Text(), nullable=True))

def downgrade():
    op.drop_column('op_accounts', 'sellers')
    op.drop_column('proxy_nodes', 'sellers')
```

---

## 正确性属性

*属性是在系统所有有效执行中都应成立的特征或行为——本质上是关于系统应该做什么的形式化陈述。属性是人类可读规范与机器可验证正确性保证之间的桥梁。*

### 属性 1：sellers 字段往返一致性（OpAccount）

*对于任意* username 字符串列表（包括空列表），将其作为 `sellers` 字段创建或更新运营账号后，再查询该账号，返回的 `sellers` 字段应与写入的列表完全相同。

**验证：需求 1.2、1.4**

### 属性 2：sellers 字段往返一致性（ProxyNode）

*对于任意* username 字符串列表（包括空列表），将其作为 `sellers` 字段创建或更新代理节点后，再查询该节点，返回的 `sellers` 字段应与写入的列表完全相同。

**验证：需求 2.2、2.4**

### 属性 3：宽松验证——不存在的 username 不阻止保存

*对于任意* 不存在于 `users` 表中的 username 字符串列表，将其作为 `sellers` 字段写入运营账号或代理节点，操作应成功完成，且存储的值与写入值一致。

**验证：需求 1.5、2.5**

### 属性 4：批量更新时 sellers 字段被正确设置

*对于任意* 运营账号 ID 列表和 username 列表，当批量状态更新时提供 `sellers` 字段，所有被更新账号的 `sellers` 字段都应被设置为该 username 列表。

**验证：需求 3.1、3.2**

### 属性 5：批量更新不传 sellers 时原值不变

*对于任意* 已设置了 `sellers` 字段的运营账号列表，当批量状态更新请求中不包含 `sellers` 字段时，所有账号的 `sellers` 字段应保持原值不变。

**验证：需求 3.3**

### 属性 6：列表渲染包含出售人名称

*对于任意* 包含非空 `sellers` 列表的账号或节点记录，列表页对应行的出售人展示区域应包含所有出售人的名称（username 或真实姓名），且不抛出错误。

**验证：需求 5.1、5.2**

---

## 错误处理

### 后端

| 场景 | 处理方式 |
|------|---------|
| `sellers` 字段包含非字符串元素 | Pydantic 自动校验，返回 422 |
| 数据库中 `sellers` 列存储了损坏的 JSON | `_deserialize_sellers` 捕获异常，返回空列表，不抛出 500 |
| 批量更新时部分账号 ID 不存在 | 跳过不存在的 ID，返回实际更新数量（现有行为保持不变） |

### 前端

| 场景 | 处理方式 |
|------|---------|
| 团队成员接口加载失败 | 展示错误提示（`el-alert`），提供"重试"按钮，允许跳过出售人选择继续提交 |
| 后端返回的 `sellers` 中包含已删除成员的 username | 展示 username（无法匹配到真实姓名时降级展示 username） |
| `sellers` 为 `null` 或 `undefined` | 前端统一处理为空数组 `[]`，展示"-" |

---

## 测试策略

### 单元测试（示例测试）

**后端**（`pytest`）：

- `test_serialize_sellers_empty`：空列表序列化为 `'[]'`
- `test_serialize_sellers_none`：`None` 序列化为 `None`
- `test_deserialize_sellers_null`：`NULL` 反序列化为 `[]`
- `test_deserialize_sellers_invalid_json`：损坏 JSON 反序列化为 `[]`
- `test_batch_update_without_sellers_preserves_existing`：不传 sellers 时原值不变（具体示例）
- 迁移脚本 upgrade/downgrade 执行不报错

**前端**（Vitest）：

- `SellerSelector` 渲染时调用 `/team/member` 接口
- `SellerSelector` 加载失败时展示错误提示
- 表单提交时 `sellers` 字段包含正确的 username 列表
- 空 `sellers` 列表展示"-"

### 属性测试（property-based testing）

使用 **Hypothesis**（Python）实现后端属性测试，每个属性测试运行最少 100 次迭代。

**测试标签格式**：`# Feature: seller-field-for-sales, Property {N}: {property_text}`

**属性 1 & 2 实现思路**：
```python
from hypothesis import given, settings
from hypothesis import strategies as st

@given(sellers=st.lists(st.text(min_size=1, max_size=64), max_size=10))
@settings(max_examples=100)
def test_sellers_round_trip_op_account(db, sellers):
    # Feature: seller-field-for-sales, Property 1: sellers 字段往返一致性（OpAccount）
    account = create_op_account(db, OpAccountCreate(..., sellers=sellers))
    fetched = get_op_account(db, account.id)
    assert fetched.sellers_list == sellers  # sellers_list 为反序列化后的属性
```

**属性 3 实现思路**：
```python
@given(sellers=st.lists(st.text(min_size=1, max_size=64), min_size=1, max_size=5))
@settings(max_examples=100)
def test_nonexistent_sellers_accepted(db, sellers):
    # Feature: seller-field-for-sales, Property 3: 宽松验证
    # sellers 中的 username 均不存在于 users 表
    account = create_op_account(db, OpAccountCreate(..., sellers=sellers))
    assert account is not None
```

**属性 4 & 5 实现思路**：
```python
@given(
    sellers=st.lists(st.text(min_size=1, max_size=32), max_size=5),
    n_accounts=st.integers(min_value=1, max_value=10)
)
@settings(max_examples=100)
def test_batch_update_sets_sellers(db, sellers, n_accounts):
    # Feature: seller-field-for-sales, Property 4: 批量更新时 sellers 字段被正确设置
    ids = [create_op_account(db, ...).id for _ in range(n_accounts)]
    batch_update_status(db, ids=ids, status="已售", sellers=sellers)
    for id_ in ids:
        account = get_op_account(db, id_)
        assert account.sellers_list == sellers
```

### 集成测试

- 迁移脚本在测试数据库上执行 upgrade 和 downgrade 各一次，验证无数据丢失
- API 端到端测试：通过 FastAPI TestClient 验证 `POST /op-accounts` 和 `PATCH /proxy-nodes/{id}` 携带 `sellers` 字段时的完整响应
