# 需求文档

## 简介

本功能是一个**全新独立的节点管理模块**，作为独立的侧边菜单出现在系统中，面向团队运营的代理节点资产管理场景。

团队采购原始代理节点（通常为 socks5 协议），可能经过中转服务器转换协议后对外出租或出售。系统需要完整记录节点的原始信息、中转信息、采购/出售信息、状态及测试监控数据，并支持批量导入导出和成本收益统计。

本模块拥有独立的 `ProxyNode` 数据表和独立的业务逻辑，与现有的监控代理管理模块（`MonitorProxy`，用于账号监控管控）**完全分离，互不影响**。

---

## 词汇表

- **节点（Node）**：一条代理记录，包含原始连接信息及相关业务信息
- **原始节点（Origin Node）**：供应商提供的原始代理地址，通常为 socks5 协议
- **中转节点（Relay Node）**：经过中转服务器转发后对外暴露的地址，协议可能不同
- **节点管理系统（Node_Manager）**：本功能的核心系统，负责节点的增删改查及统计
- **导入器（Importer）**：负责解析并批量导入节点数据的组件
- **导出器（Exporter）**：负责将节点数据序列化为文件的组件
- **连通性测试器（Connectivity_Tester）**：负责测试节点连通性并记录结果的组件
- **统计引擎（Stats_Engine）**：负责计算成本、收益及汇总统计的组件
- **节点状态（status）**：`active`（正常）/ `expired`（已到期）/ `sold`（已出售）/ `disabled`（停用）
- **使用情况（usage）**：`self`（自用）/ `rented`（出租）/ `idle`（闲置）
- **协议类型（protocol）**：`socks5` / `http` / `https`

---

## 需求

### 需求 1：节点数据模型（全新独立数据表）

**用户故事：** 作为团队运营人员，我希望节点记录能完整保存原始信息、中转信息、采购出售信息及测试结果，以便全面管理代理资产。

#### 验收标准

1. THE Node_Manager SHALL 创建全新的独立数据表 `proxy_nodes`，与现有 `monitor_proxies` 表完全分离，不共享数据也不存在外键关联。
2. THE Node_Manager SHALL 为每个节点存储以下原始节点字段：`ip`（原始 IP）、`port`（原始端口）、`username`、`password`、`protocol`（枚举值：socks5 / http / https，默认 socks5）。
3. THE Node_Manager SHALL 为每个节点存储以下中转字段：`relay_ip`（中转 IP，可为空）、`relay_port`（中转端口，可为空）、`relay_protocol`（中转协议，枚举值：socks5 / http / https，可为空）。
4. THE Node_Manager SHALL 为每个节点存储以下采购字段：`purchase_date`（采购日期，可为空）、`purchase_price`（采购单价，精度为小数点后 2 位，可为空）、`purchase_channel`（采购渠道/供应商，可为空）、`expire_date`（到期时间，可为空）。
5. THE Node_Manager SHALL 为每个节点存储以下出售字段：`sale_customer`（出售客户，可为空）、`sale_price`（出售价格，精度为小数点后 2 位，可为空）。
6. THE Node_Manager SHALL 为每个节点存储以下状态字段：`status`（枚举值：active / expired / sold / disabled，默认 active）、`usage`（枚举值：self / rented / idle，默认 idle）。
7. THE Node_Manager SHALL 为每个节点存储以下测试字段：`last_test_at`（最后测试时间，可为空）、`last_test_result`（枚举值：success / failed，可为空）、`last_test_latency`（延迟毫秒数，整数，可为空）。
8. THE Node_Manager SHALL 为每个节点存储 `remark`（备注，文本，可为空）以及系统字段 `created_at`、`updated_at`。
9. WHEN 创建节点时未指定 `protocol`，THE Node_Manager SHALL 将 `protocol` 默认设置为 `socks5`。
10. WHEN 创建节点时未指定 `status`，THE Node_Manager SHALL 将 `status` 默认设置为 `active`。
11. WHEN 创建节点时未指定 `usage`，THE Node_Manager SHALL 将 `usage` 默认设置为 `idle`。

---

### 需求 2：节点列表管理（增删改查）

**用户故事：** 作为团队运营人员，我希望能够对节点进行增删改查操作，以便维护代理资产列表。

#### 验收标准

1. THE Node_Manager SHALL 提供创建节点的接口，接受需求 1 中定义的所有字段，其中 `ip` 和 `port` 为必填项。
2. THE Node_Manager SHALL 提供查询节点列表的接口，返回所有节点的完整信息，支持分页（默认每页 100 条，最大 500 条）。
3. THE Node_Manager SHALL 提供按 ID 查询单个节点的接口，返回该节点的完整信息。
4. IF 查询的节点 ID 不存在，THEN THE Node_Manager SHALL 返回 HTTP 404 状态码及描述性错误信息。
5. THE Node_Manager SHALL 提供更新节点的接口，支持对需求 1 中所有字段的部分更新（PATCH 语义）。
6. THE Node_Manager SHALL 提供删除节点的接口，删除成功后返回 HTTP 204 状态码。
7. IF 删除的节点 ID 不存在，THEN THE Node_Manager SHALL 返回 HTTP 404 状态码及描述性错误信息。
8. WHEN 节点更新时，THE Node_Manager SHALL 自动更新 `updated_at` 字段为当前 UTC 时间。

---

### 需求 3：节点筛选与搜索

**用户故事：** 作为团队运营人员，我希望能够按多种条件筛选节点，以便快速定位目标节点。

#### 验收标准

1. THE Node_Manager SHALL 支持按 `status` 字段筛选节点列表（支持多值，如同时筛选 active 和 expired）。
2. THE Node_Manager SHALL 支持按 `usage` 字段筛选节点列表（支持多值）。
3. THE Node_Manager SHALL 支持按 `protocol` 字段筛选节点列表（支持多值）。
4. THE Node_Manager SHALL 支持按 `purchase_channel` 字段进行模糊搜索。
5. THE Node_Manager SHALL 支持按 `expire_date` 范围筛选节点（起始日期和结束日期均可选）。
6. THE Node_Manager SHALL 支持按 `sale_customer` 字段进行模糊搜索。
7. WHEN 多个筛选条件同时存在时，THE Node_Manager SHALL 对所有条件取交集（AND 逻辑）后返回结果。
8. WHEN 未传入任何筛选条件时，THE Node_Manager SHALL 返回全部节点列表。

---

### 需求 4：批量导入

**用户故事：** 作为团队运营人员，我希望能够通过上传 CSV 或 Excel 文件批量导入节点，以便快速录入大量代理数据。

#### 验收标准

1. THE Importer SHALL 支持上传 CSV 格式文件（`.csv`，UTF-8 编码）进行批量导入。
2. THE Importer SHALL 支持上传 Excel 格式文件（`.xlsx`）进行批量导入。
3. THE Importer SHALL 识别并映射以下列名（不区分大小写）：`ip`、`port`、`username`、`password`、`protocol`、`relay_ip`、`relay_port`、`relay_protocol`、`purchase_date`、`purchase_price`、`purchase_channel`、`expire_date`、`sale_customer`、`sale_price`、`status`、`usage`、`remark`。
4. WHEN 导入文件中某行的 `ip` 或 `port` 字段为空时，THE Importer SHALL 跳过该行并在结果中记录错误信息（包含行号）。
5. WHEN 导入文件中某行的枚举字段值不合法时，THE Importer SHALL 跳过该行并在结果中记录错误信息（包含行号和字段名）。
6. WHEN 导入文件中某行的 `port` 字段不是 1–65535 范围内的整数时，THE Importer SHALL 跳过该行并在结果中记录错误信息。
7. THE Importer SHALL 在导入完成后返回汇总结果，包含：成功导入数量、失败数量、每条失败记录的行号及原因。
8. WHEN 部分行导入失败时，THE Importer SHALL 继续处理其余行，不因单行错误中止整批导入。
9. THE Importer SHALL 支持提供模板文件下载，模板包含所有支持的列名及示例数据。

---

### 需求 5：批量导出

**用户故事：** 作为团队运营人员，我希望能够将节点数据导出为文件，以便进行离线分析或与他人共享。

#### 验收标准

1. THE Exporter SHALL 支持将节点数据导出为 CSV 格式文件（UTF-8 编码，带 BOM 以兼容 Excel）。
2. THE Exporter SHALL 支持将节点数据导出为 Excel 格式文件（`.xlsx`）。
3. THE Exporter SHALL 在导出文件中包含需求 1 定义的所有字段（`password` 字段默认包含，由用户决定是否使用）。
4. THE Exporter SHALL 支持结合需求 3 中的筛选条件，仅导出符合条件的节点。
5. WHEN 导出请求中未指定筛选条件时，THE Exporter SHALL 导出全部节点数据。
6. THE Exporter SHALL 在响应头中设置正确的 `Content-Disposition` 和 `Content-Type`，使浏览器触发文件下载。
7. WHEN 导出数据为空时，THE Exporter SHALL 仍返回包含列名行的空文件，而非返回错误。

---

### 需求 6：节点连通性测试

**用户故事：** 作为团队运营人员，我希望能够测试节点的连通性，以便了解节点是否可用及其响应延迟。

#### 验收标准

1. WHEN 对单个节点发起测试请求时，THE Connectivity_Tester SHALL 通过该节点发起 HTTP 请求，超时时间为 15 秒。
2. WHEN 测试成功时，THE Connectivity_Tester SHALL 将 `last_test_result` 更新为 `success`，将 `last_test_latency` 更新为实际响应时间（毫秒，整数），并将 `last_test_at` 更新为当前 UTC 时间。
3. WHEN 测试失败或超时时，THE Connectivity_Tester SHALL 将 `last_test_result` 更新为 `failed`，将 `last_test_latency` 置为空，并将 `last_test_at` 更新为当前 UTC 时间。
4. THE Connectivity_Tester SHALL 在测试响应中返回：`success`（布尔值）、`latency_ms`（整数或空）、`error`（失败原因字符串或空）。
5. IF 测试的节点 ID 不存在，THEN THE Connectivity_Tester SHALL 返回 HTTP 404 状态码。
6. WHEN 节点存在中转信息（`relay_ip` 和 `relay_port` 均不为空）时，THE Connectivity_Tester SHALL 优先使用中转地址进行测试。
7. THE Connectivity_Tester SHALL 支持对选中的多个节点发起批量测试，批量测试以并发方式执行，最大并发数为 10。
8. WHEN 批量测试完成时，THE Connectivity_Tester SHALL 返回每个节点的测试结果汇总，包含成功数量和失败数量。

---

### 需求 7：成本与收益统计

**用户故事：** 作为团队运营人员，我希望能够查看节点的成本和收益统计，以便评估代理资产的盈亏情况。

#### 验收标准

1. THE Stats_Engine SHALL 提供统计接口，返回以下汇总数据：节点总数、各状态节点数量（active / expired / sold / disabled）、各 usage 节点数量（self / rented / idle）。
2. THE Stats_Engine SHALL 计算并返回总采购成本（所有节点 `purchase_price` 之和，忽略 `purchase_price` 为空的节点）。
3. THE Stats_Engine SHALL 计算并返回总出售收入（所有节点 `sale_price` 之和，忽略 `sale_price` 为空的节点）。
4. THE Stats_Engine SHALL 计算并返回净收益（总出售收入 − 总采购成本）。
5. THE Stats_Engine SHALL 支持按 `purchase_channel` 分组，返回每个渠道的节点数量和总采购成本。
6. THE Stats_Engine SHALL 支持按时间范围（`purchase_date` 起止）筛选后再进行统计计算。
7. WHEN 统计范围内无节点数据时，THE Stats_Engine SHALL 返回各数值字段为 0 的统计结果，而非返回错误。

---

### 需求 8：前端节点管理界面

**用户故事：** 作为团队运营人员，我希望通过直观的 Web 界面管理节点，以便高效完成日常运营工作。

#### 验收标准

1. THE Node_Manager SHALL 提供节点列表页面，以表格形式展示节点的关键字段：`ip`、`port`、`protocol`、`relay_ip`、`relay_port`、`status`、`usage`、`expire_date`、`last_test_result`、`last_test_latency`、`purchase_channel`、`sale_customer`。
2. THE Node_Manager SHALL 在列表页面提供筛选栏，支持按 `status`、`usage`、`protocol`、`purchase_channel`、`sale_customer` 进行筛选。
3. THE Node_Manager SHALL 在列表页面提供"添加节点"按钮，点击后弹出表单对话框，支持填写需求 1 中的所有字段。
4. THE Node_Manager SHALL 在每行提供"编辑"操作，点击后弹出预填充当前数据的表单对话框。
5. THE Node_Manager SHALL 在每行提供"删除"操作，点击后弹出确认对话框，确认后执行删除。
6. THE Node_Manager SHALL 在每行提供"测试"操作，点击后发起连通性测试，测试期间显示加载状态，完成后在当前行更新测试结果。
7. THE Node_Manager SHALL 支持多选节点，并提供批量操作按钮：批量测试、批量删除、批量修改状态。
8. THE Node_Manager SHALL 提供"导入"按钮，支持上传 CSV 或 Excel 文件，导入完成后显示结果摘要（成功数/失败数）。
9. THE Node_Manager SHALL 提供"导出"按钮，支持选择导出格式（CSV / Excel），导出当前筛选结果。
10. THE Node_Manager SHALL 提供统计面板，展示需求 7 中定义的汇总数据（总数、各状态数量、总成本、总收入、净收益）。
11. WHEN `password` 字段在列表中展示时，THE Node_Manager SHALL 默认以掩码（`******`）显示，并提供切换可见性的按钮。
12. WHEN `expire_date` 距当前时间不足 7 天时，THE Node_Manager SHALL 以醒目颜色（如橙色或红色）高亮显示该字段。
