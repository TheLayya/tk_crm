# 实现计划：多平台运营账号管理模块

## 概述

按照设计文档，逐步实现后端数据模型、服务层、API 路由，再实现前端列表页、API 封装及路由集成，最后完成端到端串联。每个任务均可独立执行，后续任务在前序任务基础上递进。

---

## 任务列表

- [ ] 1. 数据库模型与迁移
  - [ ] 1.1 创建 `backend/app/models/op_account.py`
    - 定义 `OpAccount` 模型，包含所有手动维护字段、采购字段（purchase_channel、purchase_price、purchase_date、maintenance_cost）、出售字段（sale_customer、sale_price、sale_date）、source、tags（Text/JSON）、status 枚举（正常/自用/封禁/已售）、TikTok 专属权限字段、采集字段
    - 定义 `OpCollectTask` 模型（UUID 主键，进度字段）
    - 定义 `OpAuditLog` 模型（op_account_id 外键、action、field_name、old_value、new_value、operator、created_at）
    - 添加 `(project_id, platform, account)` 唯一约束
    - _需求：1.1、1.2、1.4、1.5、1.7、1.8、2.1、2.2、2.3、7.1_

  - [ ]* 1.2 为 `OpAccount` 数据模型编写属性测试
    - **属性 1：账号数据 round-trip**
    - **属性 2：平台枚举合法性**
    - **属性 3：项目唯一性约束**
    - **验证：需求 1.1、1.5、3.2**

  - [ ] 1.3 创建 Alembic 迁移脚本 `backend/alembic/versions/xxx_add_op_accounts.py`
    - 迁移脚本创建 `op_accounts`、`op_collect_tasks`、`op_audit_logs` 三张表
    - 包含 upgrade 和 downgrade 方法
    - _需求：10.5_

- [ ] 2. Pydantic Schema 层
  - [ ] 2.1 创建 `backend/app/schemas/op_account.py`
    - 定义 `OpAccountCreate`（必填：platform、account、project_id；可选：所有其他字段含采购/出售/source/tags）
    - 定义 `OpAccountUpdate`（所有字段可选，支持部分更新）
    - 定义 `OpAccountResponse`（含所有字段，含 id、created_at、updated_at）
    - 定义 `OpImportResult`（total、success、duplicates、failed、rows 详情）
    - 定义 `CollectTaskResponse`（task_id、status、total、completed、success、failed）
    - 定义 `BatchStatusUpdate`（ids: list[int]、status、sale_customer、sale_price、sale_date 可选）
    - 定义 `AuditLogResponse`（id、action、field_name、old_value、new_value、operator、created_at）
    - _需求：1.1、2.1、2.2、3.1、4.1、4.2、6.3、7.1_

  - [ ]* 2.2 为 Schema 层编写单元测试
    - 测试必填字段缺失时的验证错误（422）
    - 测试 platform 非法值的验证错误
    - 测试 BatchStatusUpdate 中 status="已售" 时出售字段可选填
    - _需求：1.5、1.6、3.2_

- [ ] 3. 核心服务层（CRUD + 审计日志）
  - [ ] 3.1 创建 `backend/app/services/op_account_service.py`，实现基础 CRUD
    - `create_op_account(db, data)` → 创建账号，写入 create 审计日志
    - `get_op_account(db, id)` → 按 ID 查询，不存在返回 None
    - `update_op_account(db, id, data)` → 部分更新，逐字段对比写入 update 审计日志
    - `delete_op_account(db, id)` → 删除账号（级联删除审计日志）
    - `list_op_accounts(db, filters, skip, limit)` → 支持 platform/project_id/status/keyword/tags/purchase_channel/sale_customer 过滤，分页返回
    - _需求：3.1、3.2、3.3、3.4、3.5、3.6、7.1、7.3_

  - [ ]* 3.2 为 CRUD 服务编写属性测试
    - **属性 4：部分更新不影响其他字段**
    - **属性 5：删除级联清理**
    - **属性 6：过滤结果一致性**
    - **验证：需求 3.3、3.4、3.5_**

  - [ ]* 3.3 为 CRUD 服务编写单元测试
    - 测试创建时写入审计日志（action=create）
    - 测试更新时仅变更字段写入审计日志（action=update）
    - 测试删除后审计日志级联清理
    - _需求：7.1、3.4_

- [ ] 4. 批量操作服务
  - [ ] 4.1 在 `op_account_service.py` 中实现批量状态更新
    - `batch_update_status(db, ids, status, sale_info)` → 批量修改 status，status="已售" 时写入 sale_customer/sale_price/sale_date，每条写入审计日志
    - _需求：4.1、4.2、7.1_

  - [ ]* 4.2 为批量状态更新编写单元测试
    - 测试批量修改为"已售"时出售字段正确写入
    - 测试每条账号均生成审计日志
    - _需求：4.1、4.2_

- [ ] 5. 导出服务
  - [ ] 5.1 在 `op_account_service.py` 中实现导出功能
    - `export_op_accounts(db, filters, format)` → 按过滤条件查询，format="csv" 使用 `csv` 模块生成，format="xlsx" 使用 `openpyxl` 生成，导出字段包含所有手动维护字段、采购/出售字段、采集字段
    - _需求：4.8、4.9_

  - [ ]* 5.2 为导出服务编写单元测试
    - 测试 CSV 导出行数与过滤结果一致
    - 测试 Excel 导出文件可被 openpyxl 正常读取
    - _需求：4.8、4.9_

- [ ] 6. CSV 导入服务
  - [ ] 6.1 在 `op_account_service.py` 中实现 CSV 批量导入
    - `import_from_csv(db, project_id, csv_content)` → 解析 CSV，逐行校验必填字段，重复行标记 duplicate，失败行记录原因，成功行创建账号并写入审计日志，返回 `OpImportResult`
    - _需求：4.3、4.4、4.5、4.6_

  - [ ]* 6.2 为 CSV 导入编写属性测试
    - **属性 7：CSV 导入汇总数字一致性**（total = success + duplicates + failed）
    - **属性 8：CSV 导入错误隔离**
    - **属性 9：重复导入幂等性**
    - **验证：需求 4.4、4.5、4.6_**

- [ ] 7. 采集器服务
  - [ ] 7.1 创建 `backend/app/services/op_collector_service.py`
    - `collect_account(db, account, proxy)` → 按 platform 路由到对应采集方法
    - `_collect_tiktok(account, proxy)` → 调用 `scraper_service.fetch_user_info`，成功写入采集字段，失败仅更新 collect_status/collect_error，不覆盖已有采集字段
    - `_collect_unsupported(account)` → 将 collect_status 设为 "unsupported"，不修改其他字段
    - `select_proxy(db)` → 从 monitor_proxies 随机选取 is_active=True 的代理，无可用代理返回 None
    - _需求：5.1、5.2、5.3、5.4、5.5、5.6、5.7_

  - [ ]* 7.2 为采集器编写属性测试
    - **属性 10：采集失败不覆盖已有数据**
    - **属性 11：代理选取合法性**
    - **属性 12：非 TikTok 平台采集跳过**
    - **验证：需求 5.3、5.4、5.7_**

  - [ ]* 7.3 为采集器编写单元测试
    - 测试 TikTok 采集调用 scraper_service.fetch_user_info（mock）
    - 测试采集成功后字段正确写入
    - 测试采集失败后已有字段不变
    - _需求：5.2、5.3_

- [ ] 8. 采集任务调度服务
  - [ ] 8.1 在 `op_account_service.py` 中实现采集任务调度
    - `trigger_collect(db, account_ids, background_tasks)` → 创建 OpCollectTask（UUID），通过 BackgroundTasks 异步执行 `run_collect_task`，立即返回 task_id
    - `run_collect_task(task_id, account_ids)` → 逐个调用 `collect_account`，更新 OpCollectTask 进度（completed/success/failed），完成后 status="completed"
    - `get_collect_task(db, task_id)` → 查询任务进度
    - 创建/导入账号时自动调用 `trigger_collect`
    - _需求：5.1、6.1、6.2、6.3、6.4、6.5_

  - [ ]* 8.2 为采集任务调度编写属性测试
    - **属性 13：批量采集进度数字一致性**（completed = success + failed，completed <= total）
    - **验证：需求 6.3_**

  - [ ]* 8.3 为采集任务调度编写单元测试
    - 测试创建账号后自动触发采集（mock BackgroundTasks）
    - 测试正在采集中的账号拒绝重复采集（409）
    - _需求：5.1、6.5_

- [ ] 9. 操作日志查询服务
  - [ ] 9.1 在 `op_account_service.py` 中实现审计日志查询
    - `get_audit_logs(db, account_id)` → 按 op_account_id 查询，按 created_at 倒序返回完整变更历史
    - _需求：7.2_

  - [ ]* 9.2 为审计日志查询编写单元测试
    - 测试创建/更新/删除操作后日志条目正确生成
    - 测试按账号 ID 查询返回倒序结果
    - _需求：7.1、7.2、7.3_

- [ ] 10. 检查点 — 后端服务层完成
  - 确保所有测试通过，服务层各方法可独立调用，询问用户是否有问题。

- [ ] 11. API 路由层
  - [ ] 11.1 创建 `backend/app/api/op_accounts.py`，实现所有路由
    - `GET /api/op-accounts` → 调用 `list_op_accounts`，支持 platform/project_id/status/keyword/tags/purchase_channel/sale_customer/skip/limit 查询参数
    - `POST /api/op-accounts` → 调用 `create_op_account`，返回 201
    - `PUT /api/op-accounts/{id}` → 调用 `update_op_account`，不存在返回 404
    - `DELETE /api/op-accounts/{id}` → 调用 `delete_op_account`，不存在返回 404
    - `POST /api/op-accounts/batch-status` → 调用 `batch_update_status`
    - `POST /api/op-accounts/import` → 接收 multipart/form-data CSV 文件，调用 `import_from_csv`
    - `GET /api/op-accounts/export` → 调用 `export_op_accounts`，返回文件流（Content-Disposition）
    - `POST /api/op-accounts/collect` → 调用 `trigger_collect`，返回 task_id
    - `GET /api/op-accounts/tasks/{task_id}` → 调用 `get_collect_task`，不存在返回 404
    - `GET /api/op-accounts/{id}/logs` → 调用 `get_audit_logs`，不存在返回 404
    - _需求：3.1、3.2、3.3、3.4、3.5、4.1、4.3、4.8、4.9、6.1、6.2、6.3、7.2_

  - [ ]* 11.2 为 API 路由编写集成测试
    - 测试完整 CSV 导入流程（含文件上传）
    - 测试批量采集任务异步执行和进度查询
    - 测试 409 冲突、404 不存在等错误响应
    - _需求：3.2、4.3、4.6、6.3_

- [ ] 12. 注册路由到主应用
  - [ ] 12.1 修改 `backend/app/main.py`
    - 导入 `op_accounts` 路由模块
    - 注册 router，prefix="/api/op-accounts"
    - _需求：10.4_

- [ ] 13. 检查点 — 后端 API 完成
  - 确保所有测试通过，API 路由可正常响应，询问用户是否有问题。

- [ ] 14. 前端 API 封装
  - [ ] 14.1 创建 `frontend/src/api/op_accounts.js`
    - 封装所有运营账号 API：`listOpAccounts(params)`、`createOpAccount(data)`、`updateOpAccount(id, data)`、`deleteOpAccount(id)`、`batchUpdateStatus(data)`、`importOpAccounts(formData)`、`exportOpAccounts(params, format)`、`triggerCollect(ids)`、`getCollectTask(taskId)`、`getAuditLogs(id)`
    - 导出函数使用 `request.js` 封装的 axios 实例
    - _需求：3.1、4.1、4.3、4.8、6.1、7.2_

- [ ] 15. 前端路由与侧边栏集成
  - [ ] 15.1 修改 `frontend/src/router/index.js`
    - 新增 `/op-accounts` 路由，懒加载 `OpAccountList.vue`
    - _需求：10.3_

  - [ ] 15.2 修改 `frontend/src/components/Layout.vue`
    - 在侧边栏菜单中新增"运营账号"菜单项，路由指向 `/op-accounts`，与"监控管理"、"系统设置"并列
    - _需求：10.3_

- [ ] 16. 运营账号列表主视图（基础功能）
  - [ ] 16.1 创建 `frontend/src/views/OpAccountList.vue`，实现基础列表与过滤
    - 过滤栏：平台、项目、状态、标签、关键词、采购渠道、出售客户下拉/输入框
    - `el-table` 展示账号列表，列包含所有手动维护字段、采购/出售字段、采集字段
    - 列显示/隐藏配置，配置持久化到 `localStorage`（key: `op_accounts_column_config`）
    - 分页组件，默认每页 50 条，支持调整
    - 密码、邮箱密码、2FA 密钥字段默认掩码显示，点击眼睛图标切换明文
    - _需求：8.1、8.2、8.3、8.5、8.6、9.1、9.2_

  - [ ]* 16.2 为列配置持久化编写单元测试（Vitest）
    - 测试列配置写入/读取 localStorage 正确
    - 测试密码掩码显示/切换逻辑
    - _需求：8.3、9.1、9.2_

- [ ] 17. 运营账号列表主视图（新增/编辑表单）
  - [ ] 17.1 在 `OpAccountList.vue` 中实现新增/编辑账号对话框
    - 表单字段分组：基础信息、账号凭证、TikTok 权限（仅 platform=tiktok 时显示）、采购信息（purchase_channel/purchase_price/purchase_date/maintenance_cost）、出售信息（sale_customer/sale_price/sale_date，status="已售" 时高亮提示）、其他（source、tags、remark）
    - 提交调用 `createOpAccount` 或 `updateOpAccount`
    - _需求：1.2、1.3、2.1、2.2、2.4、8.2_

- [ ] 18. 运营账号列表主视图（批量操作）
  - [ ] 18.1 在 `OpAccountList.vue` 中实现批量修改状态
    - 多选账号后显示批量操作工具栏
    - 点击"批量修改状态"弹出状态选择对话框
    - 选择"已售"时额外弹出出售信息填写表单（sale_customer、sale_price、sale_date）
    - 提交调用 `batchUpdateStatus`，刷新列表
    - _需求：4.1、4.2_

  - [ ] 18.2 在 `OpAccountList.vue` 中实现导出功能
    - 过滤栏旁添加"导出"按钮
    - 点击弹出格式选择（CSV / Excel），按当前过滤条件调用 `exportOpAccounts`
    - 触发浏览器文件下载
    - _需求：4.8、4.9_

  - [ ] 18.3 在 `OpAccountList.vue` 中实现手动触发采集
    - 多选账号后工具栏显示"采集"按钮，调用 `triggerCollect`
    - 轮询 `getCollectTask` 显示进度（el-progress 或进度文字）
    - _需求：6.1、6.2、6.3_

- [ ] 19. 运营账号列表主视图（操作历史）
  - [ ] 19.1 在 `OpAccountList.vue` 中实现操作历史时间线
    - 每行操作列添加"历史"按钮
    - 点击弹出对话框，调用 `getAuditLogs(id)`，以 `el-timeline` 展示变更记录（action、field_name、old_value → new_value、时间）
    - _需求：7.2、7.4_

- [ ] 20. 检查点 — 前端功能完成
  - 确保所有测试通过，前端页面可正常访问，询问用户是否有问题。

- [ ] 21. 端到端串联验证
  - [ ] 21.1 验证完整创建流程
    - 创建账号 → 自动触发采集 → 采集结果写回 → 审计日志生成
    - _需求：5.1、7.1_

  - [ ] 21.2 验证 CSV 导入流程
    - 上传 CSV → 解析 → 批量创建 → 自动采集 → 返回汇总结果
    - _需求：4.3、4.4、4.5、4.6、4.7_

  - [ ]* 21.3 编写端到端集成测试
    - 测试与现有 Project 和 MonitorProxy 的关联查询
    - 测试批量采集任务的异步执行和进度查询
    - _需求：10.1、10.2_

- [ ] 22. 最终检查点 — 确保所有测试通过
  - 确保所有测试通过，询问用户是否有问题。

---

## 备注

- 标有 `*` 的子任务为可选测试任务，可跳过以加快 MVP 交付
- 每个任务均引用具体需求条款，确保可追溯性
- 检查点任务确保增量验证，避免集成问题积压
- 属性测试使用 Hypothesis 框架，每个属性对应设计文档中的编号属性
- 单元测试使用 pytest，前端测试使用 Vitest
