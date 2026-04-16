# 需求文档

## 简介

本功能为 TikTok 账号监控与运营管理系统中的"运营账号"（op_accounts）和"代理节点"（proxy_nodes）两个模块添加"出售人"（seller）字段。出售人支持多选，即一笔出售记录可以关联多个团队成员作为出售人。

当前系统已有 `sale_customer`（买家/客户）、`sale_price`（出售价格）、`sale_date`（出售日期）等出售相关字段，但缺少记录"谁负责了这笔出售"的字段。新增的出售人字段将从系统现有团队成员（User）中选取，支持多选。

---

## 词汇表

- **OpAccount**：运营账号，存储于 `op_accounts` 表，代表被管理的 TikTok/YouTube 等平台账号。
- **ProxyNode**：代理节点，存储于 `proxy_nodes` 表，代表可出售的代理 IP 节点。
- **Seller**：出售人，指负责完成某笔出售的团队成员，可以是一人或多人。
- **User**：系统团队成员，存储于 `users` 表，具有 `username` 和 `real_name` 字段。
- **SaleInfo**：出售信息，包含 `sale_customer`、`sale_price`、`sale_date`、`sellers` 等字段的集合。
- **Seller_Selector**：前端多选组件，用于从团队成员列表中选择一个或多个出售人。
- **System**：本系统后端服务（FastAPI）。
- **Frontend**：本系统前端应用（Vue 3）。

---

## 需求

### 需求 1：运营账号出售人字段存储

**用户故事：** 作为运营人员，我希望在运营账号的出售信息中记录出售人，以便追踪每笔出售由哪些团队成员负责。

#### 验收标准

1. THE System SHALL 在 `op_accounts` 表中新增 `sellers` 字段，用于存储出售人列表（以 JSON 数组格式存储 username 字符串列表）。
2. WHEN 创建或更新运营账号时，THE System SHALL 接受 `sellers` 字段，其值为包含零个或多个团队成员 username 的列表。
3. WHEN `sellers` 字段为空列表或未提供时，THE System SHALL 将其存储为空列表，不报错。
4. WHEN 查询运营账号列表或详情时，THE System SHALL 在响应中返回 `sellers` 字段，其值为 username 字符串列表。
5. IF `sellers` 字段包含不存在于 `users` 表中的 username，THEN THE System SHALL 仍然保存该值，不阻止保存（允许历史数据兼容）。

---

### 需求 2：代理节点出售人字段存储

**用户故事：** 作为运营人员，我希望在代理节点的出售信息中记录出售人，以便追踪每笔节点出售由哪些团队成员负责。

#### 验收标准

1. THE System SHALL 在 `proxy_nodes` 表中新增 `sellers` 字段，用于存储出售人列表（以 JSON 数组格式存储 username 字符串列表）。
2. WHEN 创建或更新代理节点时，THE System SHALL 接受 `sellers` 字段，其值为包含零个或多个团队成员 username 的列表。
3. WHEN `sellers` 字段为空列表或未提供时，THE System SHALL 将其存储为空列表，不报错。
4. WHEN 查询代理节点列表或详情时，THE System SHALL 在响应中返回 `sellers` 字段，其值为 username 字符串列表。
5. IF `sellers` 字段包含不存在于 `users` 表中的 username，THEN THE System SHALL 仍然保存该值，不阻止保存（允许历史数据兼容）。

---

### 需求 3：批量状态更新时支持出售人

**用户故事：** 作为运营人员，我希望在批量将运营账号标记为"已售"时，能够同时设置出售人，以便一次操作完成出售信息的完整录入。

#### 验收标准

1. WHEN 调用运营账号批量状态更新接口时，THE System SHALL 接受可选的 `sellers` 字段（username 列表）。
2. WHEN `sellers` 字段被提供时，THE System SHALL 将批量更新的所有账号的 `sellers` 字段设置为该值。
3. WHEN `sellers` 字段未提供时，THE System SHALL 保持各账号原有的 `sellers` 字段不变。

---

### 需求 4：前端出售人多选组件

**用户故事：** 作为运营人员，我希望在填写出售信息时，能够通过多选下拉框从团队成员列表中选择一个或多个出售人，而不是手动输入文字。

#### 验收标准

1. THE Frontend SHALL 在运营账号编辑表单的出售信息区域展示出售人多选组件（Seller_Selector）。
2. THE Frontend SHALL 在代理节点编辑表单的出售信息区域展示出售人多选组件（Seller_Selector）。
3. WHEN Seller_Selector 被渲染时，THE Frontend SHALL 从团队成员接口加载可选的成员列表，展示格式为"真实姓名（用户名）"或仅真实姓名（若真实姓名存在）。
4. THE Seller_Selector SHALL 支持同时选中多个团队成员。
5. WHEN 用户提交表单时，THE Frontend SHALL 将已选出售人的 username 列表作为 `sellers` 字段提交给后端。
6. WHEN 加载已有记录时，THE Frontend SHALL 将后端返回的 `sellers` username 列表回显到 Seller_Selector 中，显示对应的成员名称。
7. WHERE 团队成员列表加载失败，THE Frontend SHALL 展示错误提示，并允许用户重试或跳过出售人选择。

---

### 需求 5：出售人字段的筛选与展示

**用户故事：** 作为运营人员，我希望在列表页能够看到每条记录的出售人信息，以便快速了解出售情况。

#### 验收标准

1. WHEN 运营账号列表渲染时，THE Frontend SHALL 在出售信息相关列中展示出售人名称（多个出售人以逗号或标签形式分隔展示）。
2. WHEN 代理节点列表渲染时，THE Frontend SHALL 在出售信息相关列中展示出售人名称（多个出售人以逗号或标签形式分隔展示）。
3. WHEN 出售人列表为空时，THE Frontend SHALL 展示空值（"-"或空白），不报错。

---

### 需求 6：数据库迁移

**用户故事：** 作为系统管理员，我希望通过数据库迁移脚本安全地为现有表添加出售人字段，以便在不丢失现有数据的情况下完成升级。

#### 验收标准

1. THE System SHALL 提供 Alembic 迁移脚本，为 `op_accounts` 表添加 `sellers` 列（类型为 Text，可为空，默认值为 NULL）。
2. THE System SHALL 提供 Alembic 迁移脚本，为 `proxy_nodes` 表添加 `sellers` 列（类型为 Text，可为空，默认值为 NULL）。
3. WHEN 迁移脚本执行时，THE System SHALL 不修改现有行的其他字段数据。
4. WHEN 迁移脚本回滚时，THE System SHALL 删除新增的 `sellers` 列，恢复到迁移前的表结构。
