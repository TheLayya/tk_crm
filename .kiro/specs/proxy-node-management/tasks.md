# 实现计划：节点管理模块（proxy-node-management）

## 概述

本模块是一个全新独立的节点管理系统，与现有监控代理管理完全分离。实现分为后端（Python FastAPI + SQLAlchemy + SQLite）和前端（Vue 3 + Element Plus）两部分，按照"数据层 → 服务层 → API 层 → 前端"的顺序逐步构建，每一步都在前一步的基础上增量推进。

## 任务

- [x] 1. 创建数据模型与数据库迁移
  - 新建 `backend/app/models/proxy_node.py`，定义 `ProxyNode` SQLAlchemy 模型，映射到 `proxy_nodes` 表
  - 包含所有字段：原始节点（ip、port、username、password、protocol）、中转节点（relay_ip、relay_port、relay_protocol）、采购信息（purchase_date、purchase_price、purchase_channel、expire_date）、出售信息（sale_customer、sale_price）、状态字段（status、usage）、测试字段（last_test_at、last_test_result、last_test_latency）、备注（remark）、系统字段（created_at、updated_at）
  - 为 `status`、`usage`、`expire_date`、`purchase_channel` 字段添加单列索引
  - 在 `backend/app/models/__init__.py` 中导入 `ProxyNode`，确保 Alembic 能发现该模型
  - 新建 Alembic 迁移文件 `backend/alembic/versions/20260601_0001_add_proxy_nodes.py`，创建 `proxy_nodes` 表及所有索引，并实现 `downgrade()` 方法
  - _需求：1.1、1.2、1.3、1.4、1.5、1.6、1.7、1.8、1.9、1.10、1.11_

- [x] 2. 创建 Pydantic Schema
  - 新建 `backend/app/schemas/proxy_node.py`，定义以下 Schema：
    - `ProxyNodeCreate`：ip 和 port 为必填，其余字段可选，port 范围 1–65535，枚举字段使用 `Literal` 类型
    - `ProxyNodeUpdate`：所有字段均为 `Optional`，实现 PATCH 语义
    - `ProxyNodeResponse`：包含所有字段及 id、created_at、updated_at，配置 `from_attributes = True`
    - `ProxyNodeFilter`：status/usage/protocol 支持多值列表，purchase_channel/sale_customer 为字符串（模糊搜索），expire_date_from/expire_date_to 为日期范围
    - `ProxyNodeImportResult`：包含 success_count、fail_count、errors 列表
    - `ProxyNodeTestResult`：包含 success（布尔）、latency_ms（整数或空）、error（字符串或空）
    - `ProxyNodeBatchTestResult`：包含 success_count、fail_count、results 列表
    - `ChannelStats` 和 `ProxyNodeStats`：统计结果，包含 total、by_status、by_usage、total_purchase_cost、total_sale_revenue、net_profit、by_channel
  - _需求：2.1、2.2、2.5、6.4、6.8、7.1、7.2、7.3、7.4、7.5_

- [x] 3. 实现核心 CRUD 服务层
  - 新建 `backend/app/services/proxy_node_service.py`，实现以下函数：
    - `get_nodes(db, filter, skip, limit)` → 带筛选的分页查询，支持 status/usage/protocol 多值 IN 查询、purchase_channel/sale_customer LIKE 模糊搜索、expire_date 范围查询，多条件取 AND 交集
    - `get_node(db, node_id)` → 按 ID 查询，不存在返回 None
    - `create_node(db, data)` → 创建节点，应用默认值（protocol=socks5、status=active、usage=idle）
    - `update_node(db, node_id, data)` → 使用 `model_dump(exclude_unset=True)` 实现部分更新，自动更新 `updated_at`
    - `delete_node(db, node_id)` → 删除节点，返回布尔值
    - `batch_delete_nodes(db, node_ids)` → 批量删除，返回删除数量
    - `batch_update_status(db, node_ids, status)` → 批量修改状态，自动更新 `updated_at`
    - `get_stats(db, filter)` → 统计计算：各状态/usage 数量、总采购成本（忽略 None）、总出售收入（忽略 None）、净收益、按渠道分组统计
  - _需求：2.1、2.2、2.3、2.4、2.5、2.6、2.7、2.8、3.1、3.2、3.3、3.4、3.5、3.6、3.7、3.8、7.1、7.2、7.3、7.4、7.5、7.6、7.7_

  - [ ]* 3.1 为 CRUD 服务层编写属性测试
    - **属性 1：节点数据 Round-Trip 完整性**
    - **验证：需求 1.2、1.3、1.4、1.5、1.6、1.7、1.8、2.1、2.3**
    - **属性 2：分页查询结果数量约束**
    - **验证：需求 2.2**
    - **属性 3：部分更新不影响未指定字段**
    - **验证：需求 2.5**
    - **属性 4：更新操作自动刷新 updated_at**
    - **验证：需求 2.8**
    - **属性 5：筛选结果满足所有筛选条件（AND 逻辑）**
    - **验证：需求 3.1、3.2、3.3、3.4、3.5、3.6、3.7**
    - 测试文件：`backend/tests/test_proxy_node_properties.py`，使用 `hypothesis` 库，每个属性最少 100 次迭代

  - [ ]* 3.2 为 CRUD 服务层编写单元测试
    - 测试文件：`backend/tests/test_proxy_node_service.py`
    - 覆盖：创建节点默认值、404 场景、批量操作、统计空数据集（返回 0 而非报错）
    - _需求：1.9、1.10、1.11、2.4、2.7、7.7_

- [x] 4. 实现导入服务层
  - 新建 `backend/app/services/proxy_node_import_service.py`，实现以下函数：
    - `import_from_csv(db, file_content: bytes)` → 解析 UTF-8 CSV，逐行处理
    - `import_from_excel(db, file_content: bytes)` → 使用 `openpyxl` 解析 `.xlsx`
    - `_validate_row(row_dict, line_num)` → 验证单行数据：ip/port 必填检查、port 范围 1–65535 检查、枚举字段合法性检查；返回 `(ProxyNodeCreate | None, error_str | None)`
    - `generate_template_csv()` → 生成包含所有列名和示例数据的模板 CSV bytes（UTF-8 with BOM）
    - 列名识别不区分大小写，支持的列：ip、port、username、password、protocol、relay_ip、relay_port、relay_protocol、purchase_date、purchase_price、purchase_channel、expire_date、sale_customer、sale_price、status、usage、remark
    - 单行失败不中止整批，错误信息格式：`"第 {行号} 行: {原因}"`
    - 返回 `ProxyNodeImportResult`
  - _需求：4.1、4.2、4.3、4.4、4.5、4.6、4.7、4.8、4.9_

  - [ ]* 4.1 为导入服务层编写属性测试
    - **属性 7：导入部分失败不中止整批处理**
    - **验证：需求 4.4、4.5、4.6、4.7、4.8**
    - 使用 `hypothesis` 生成混合有效/无效行的数据集，验证 `success_count + fail_count = 总行数`，`errors` 列表长度等于 `fail_count`

  - [ ]* 4.2 为导入服务层编写单元测试
    - 测试文件：`backend/tests/test_proxy_node_import_service.py`
    - 覆盖：空 ip/port 跳过、非法枚举值跳过、port 越界跳过、列名大小写不敏感、模板文件包含所有列名
    - _需求：4.3、4.4、4.5、4.6、4.9_

- [x] 5. 实现导出服务层
  - 新建 `backend/app/services/proxy_node_export_service.py`，实现以下函数：
    - `export_to_csv(nodes: List[ProxyNode]) -> bytes` → 序列化为 UTF-8 with BOM 的 CSV bytes，包含所有字段列
    - `export_to_excel(nodes: List[ProxyNode]) -> bytes` → 使用 `openpyxl` 序列化为 `.xlsx` bytes，包含所有字段列
    - 当 `nodes` 为空列表时，仍返回包含列名行的文件（不返回错误）
  - _需求：5.1、5.2、5.3、5.7_

  - [ ]* 5.1 为导出服务层编写属性测试
    - **属性 6：导入-导出 Round-Trip 数据一致性**
    - **验证：需求 4.1、4.2、4.3、5.1、5.2、5.3**
    - 使用 `hypothesis` 生成随机有效节点数据集，序列化为 CSV/Excel 后再导入，验证所有有效行字段值与原始数据一致
    - **属性 8：导出筛选结果仅包含满足条件的节点**
    - **验证：需求 5.4**

  - [ ]* 5.2 为导出服务层编写单元测试
    - 测试文件：`backend/tests/test_proxy_node_export_service.py`
    - 覆盖：空节点列表导出仍有列名行、CSV BOM 头、Excel 格式正确性
    - _需求：5.1、5.2、5.7_

- [x] 6. 实现连通性测试服务层
  - 新建 `backend/app/services/proxy_node_test_service.py`，实现以下函数：
    - `_do_test(node: ProxyNode) -> dict` → 使用 `httpx.AsyncClient` 通过代理发起 HTTP 请求，超时 15 秒；当 `relay_ip` 和 `relay_port` 均不为空时优先使用中转地址，否则使用原始地址；成功返回 `{success: True, latency_ms: int}`，失败返回 `{success: False, latency_ms: None, error: str}`（错误信息截断至 200 字符）
    - `test_node(db, node_id) -> ProxyNodeTestResult` → 测试单个节点，更新 `last_test_result`、`last_test_latency`、`last_test_at`，节点不存在返回 None
    - `batch_test_nodes(db, node_ids) -> ProxyNodeBatchTestResult` → 使用 `asyncio.Semaphore(10)` 控制最大并发数为 10，并发测试所有节点，返回每个节点的测试结果及汇总
  - _需求：6.1、6.2、6.3、6.4、6.5、6.6、6.7、6.8_

  - [ ]* 6.1 为连通性测试服务层编写属性测试
    - **属性 9：测试结果字段与测试结论一致**
    - **验证：需求 6.2、6.3、6.4**
    - mock `httpx.AsyncClient`，验证成功时 `last_test_result="success"` 且 `last_test_latency` 为正整数，失败时 `last_test_result="failed"` 且 `last_test_latency` 为空
    - **属性 10：有中转信息时优先使用中转地址测试**
    - **验证：需求 6.6**
    - mock 网络请求，验证实际使用的代理 URL 为中转地址
    - **属性 11：批量测试并发数不超过上限**
    - **验证：需求 6.7**
    - mock 网络请求并记录并发峰值，验证任意时刻并发数 ≤ 10
    - **属性 12：批量测试结果汇总数量守恒**
    - **验证：需求 6.8**

- [x] 7. 实现 API 路由层
  - 新建 `backend/app/api/proxy_nodes.py`，路由前缀 `/proxy-nodes`，实现以下端点：
    - `GET /` → 查询节点列表，支持分页（skip/limit，默认 100，最大 500）和筛选参数（通过 Query 参数传入）
    - `POST /` → 创建节点，返回 201
    - `GET /stats` → 获取统计数据（注意：此路由必须在 `/{node_id}` 之前注册，避免路由冲突）
    - `GET /import/template` → 下载导入模板 CSV，设置正确的 Content-Disposition 和 Content-Type
    - `GET /export` → 导出节点数据，支持 format 参数（csv/xlsx），结合筛选条件，设置正确的响应头触发浏览器下载
    - `POST /import` → 批量导入，接受 `UploadFile`，根据文件扩展名分发到 CSV 或 Excel 导入函数，不支持的格式返回 400
    - `GET /{node_id}` → 查询单个节点，不存在返回 404
    - `PATCH /{node_id}` → 部分更新节点，不存在返回 404
    - `DELETE /{node_id}` → 删除节点，成功返回 204，不存在返回 404
    - `DELETE /batch` → 批量删除，接受 node_ids 列表，返回删除数量
    - `PATCH /batch/status` → 批量修改状态，接受 node_ids 和 status
    - `POST /{node_id}/test` → 测试单个节点连通性，不存在返回 404
    - `POST /batch/test` → 批量测试节点连通性
  - 在 `backend/app/main.py` 中新增一行注册路由：`from app.api import proxy_nodes` 和 `app.include_router(proxy_nodes.router, prefix="/api")`，不修改其他任何内容
  - _需求：2.1、2.2、2.3、2.4、2.5、2.6、2.7、4.1、4.2、4.9、5.1、5.2、5.4、5.5、5.6、5.7、6.1、6.5、6.7、6.8、7.1_

- [x] 8. 检查点 — 后端验证
  - 确保所有测试通过，运行 `pytest backend/tests/test_proxy_node*.py -v`
  - 确认 Alembic 迁移文件语法正确（`alembic check`）
  - 如有问题，请向用户说明并等待指示

- [x] 9. 创建前端 API 模块
  - 新建 `frontend/src/api/proxy_nodes.js`，封装所有后端接口调用，使用现有的 `request.js` 工具：
    - `getProxyNodes(params)` → GET `/api/proxy-nodes`，params 包含分页和筛选参数
    - `getProxyNode(id)` → GET `/api/proxy-nodes/{id}`
    - `createProxyNode(data)` → POST `/api/proxy-nodes`
    - `updateProxyNode(id, data)` → PATCH `/api/proxy-nodes/{id}`
    - `deleteProxyNode(id)` → DELETE `/api/proxy-nodes/{id}`
    - `batchDeleteProxyNodes(nodeIds)` → DELETE `/api/proxy-nodes/batch`
    - `batchUpdateStatus(nodeIds, status)` → PATCH `/api/proxy-nodes/batch/status`
    - `testProxyNode(id)` → POST `/api/proxy-nodes/{id}/test`
    - `batchTestProxyNodes(nodeIds)` → POST `/api/proxy-nodes/batch/test`
    - `importProxyNodes(file)` → POST `/api/proxy-nodes/import`，使用 FormData
    - `downloadImportTemplate()` → GET `/api/proxy-nodes/import/template`
    - `exportProxyNodes(params, format)` → GET `/api/proxy-nodes/export`，触发文件下载
    - `getProxyNodeStats(params)` → GET `/api/proxy-nodes/stats`
  - _需求：2.1、2.2、2.5、2.6、4.1、4.2、4.9、5.1、5.2、6.1、6.7、7.1、8.1_

- [x] 10. 创建前端视图组件
  - 新建 `frontend/src/views/ProxyNodeManage.vue`，包含以下功能区域：

  - [x] 10.1 实现统计面板
    - 页面顶部展示统计卡片：节点总数、各状态数量（active/expired/sold/disabled）、总采购成本、总出售收入、净收益
    - 调用 `getProxyNodeStats()` 获取数据，页面加载时自动刷新
    - _需求：8.10、7.1、7.2、7.3、7.4_

  - [x] 10.2 实现筛选栏
    - 提供筛选控件：status 多选下拉、usage 多选下拉、protocol 多选下拉、purchase_channel 文本输入、sale_customer 文本输入
    - 筛选条件变化时自动触发列表刷新
    - _需求：8.2、3.1、3.2、3.3、3.4、3.6_

  - [x] 10.3 实现节点数据表格
    - 使用 `el-table` 展示节点列表，支持多选（`el-table-column type="selection"`）
    - 展示列：ip、port、protocol、relay_ip、relay_port、status（标签样式）、usage（标签样式）、expire_date（到期不足 7 天时橙色/红色高亮）、last_test_result（图标+文字）、last_test_latency（ms）、purchase_channel、sale_customer、password（默认掩码 `******`，提供眼睛图标切换可见性）
    - 每行操作列：测试（点击后显示加载状态，完成后更新当前行）、编辑、删除（确认对话框）
    - 支持分页（`el-pagination`）
    - _需求：8.1、8.4、8.5、8.6、8.11、8.12_

  - [x] 10.4 实现批量操作工具栏
    - 当有选中行时显示工具栏：批量测试、批量删除（确认对话框）、批量修改状态（下拉选择目标状态）
    - _需求：8.7_

  - [x] 10.5 实现添加/编辑节点对话框
    - 使用 `el-dialog` + `el-form` 实现，支持所有字段的输入
    - 字段分组展示：原始节点信息、中转节点信息（可折叠）、采购信息（可折叠）、出售信息（可折叠）
    - ip 和 port 为必填，port 范围 1–65535 的表单验证
    - 编辑时预填充当前数据
    - _需求：8.3、8.4、1.2、1.3、1.4、1.5_

  - [x] 10.6 实现导入对话框
    - 使用 `el-dialog` 包含 `el-upload` 组件，支持 `.csv` 和 `.xlsx` 文件
    - 提供"下载模板"链接
    - 导入完成后展示结果摘要（成功数/失败数），失败详情可展开查看（`el-collapse`）
    - _需求：8.8、4.1、4.2、4.9_

  - [x] 10.7 实现导出功能
    - 提供"导出"按钮，点击后弹出格式选择（CSV / Excel）
    - 导出时携带当前筛选条件，仅导出符合条件的节点
    - _需求：8.9、5.1、5.2、5.4_

  - [ ]* 10.8 为到期日期高亮工具函数编写单元测试
    - **属性 15：到期日期高亮逻辑正确性**
    - **验证：需求 8.12**
    - 将高亮判断逻辑提取为纯函数 `isExpiringSoon(expireDate, thresholdDays = 7)`
    - 使用 Vitest 测试：距今 0 天（今天）→ 高亮，6 天 → 高亮，7 天 → 高亮，8 天 → 不高亮，null → 不高亮
    - 测试文件：`frontend/src/utils/proxyNodeUtils.test.js`

  - [ ]* 10.9 为密码掩码切换行为编写组件测试
    - 使用 Vue Test Utils 验证：初始状态密码显示为 `******`，点击眼睛图标后显示原始值，再次点击恢复掩码
    - _需求：8.11_

- [x] 11. 注册路由与侧边菜单
  - 在 `frontend/src/router/index.js` 中新增路由（在 `/op-accounts` 之后）：
    ```javascript
    {
      path: '/proxy-nodes',
      name: 'ProxyNodeManage',
      component: () => import('../views/ProxyNodeManage.vue'),
      meta: { requiresAuth: true, breadcrumb: '节点管理' }
    }
    ```
  - 在 `frontend/src/components/Layout.vue` 的侧边菜单中，在"运营账号"菜单项之后新增"节点管理"菜单项：
    ```html
    <el-menu-item index="/proxy-nodes">
      <el-icon><Connection /></el-icon>
      <template #title><span>节点管理</span></template>
    </el-menu-item>
    ```
    并在 `script setup` 中导入 `Connection` 图标
  - 在 `frontend/src/components/MobileTabBar.vue` 中，在"运营"标签之后新增"节点"标签（使用 `Connection` 图标），并更新 `activeTab` 计算属性以处理 `/proxy-nodes` 路径
  - _需求：8.1_

- [x] 12. 最终检查点 — 确保所有测试通过
  - 确保所有测试通过，如有问题请向用户说明并等待指示

## 备注

- 标有 `*` 的子任务为可选任务，可跳过以加快 MVP 交付
- 每个任务均引用了具体的需求条款，确保可追溯性
- 后端任务（1–8）与前端任务（9–11）相互独立，可并行开发
- 所有新文件均为新增，不修改现有业务逻辑文件（`main.py` 除外，仅新增一行路由注册）
- 属性测试使用 `hypothesis` 库，单元测试使用 `pytest`，前端测试使用 `Vitest`
