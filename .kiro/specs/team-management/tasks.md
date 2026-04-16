# 实现计划：团队管理模块

## 概述

基于 FastAPI + SQLAlchemy + SQLite + Alembic（后端）和 Vue3 + Element Plus + Pinia（前端）实现团队管理模块，包含 JWT 认证、RBAC 权限、AES-256-GCM 加密、API 限流、操作日志和二次确认。

## 任务

- [x] 1. 配置与依赖准备
  - 在 `backend/app/core/config.py` 中新增 `JWT_SECRET`、`JWT_ALGORITHM`、`ACCESS_TOKEN_EXPIRE_MINUTES`、`REFRESH_TOKEN_EXPIRE_DAYS`、`FIELD_ENCRYPTION_KEY`、`SUPER_ADMIN_PASSWORD` 配置项，启动时校验 `FIELD_ENCRYPTION_KEY` 格式（64位hex），不合法则抛出 `ValueError` 拒绝启动
  - 在 `backend/.env.example` 中补充上述环境变量示例
  - 在 `backend/requirements.txt` 中新增：`python-jose[cryptography]`、`passlib[bcrypt]`、`cryptography`、`slowapi`
  - _需求：1.7、10.2、10.7_

- [x] 2. 数据模型
  - [x] 2.1 创建 `backend/app/models/team.py`，定义 `User`、`Department`、`Role`、`RolePermission`、`UserRole`、`RefreshToken`、`OperationToken`、`LoginLog`、`OperationLog` 九张表，字段与设计文档完全一致，`Department` 加 `UniqueConstraint("parent_id", "name")`
    - _需求：1、2.1、3.1、4.1、7.1、8.1、12.4_
  - [ ]* 2.2 为 `User` 模型编写单元测试：验证 `is_super_admin` 默认值、`is_active` 默认值、`username` 唯一约束
    - _需求：3.1、9.1_

- [x] 3. AES-256-GCM 加密服务
  - [x] 3.1 创建 `backend/app/services/encryption_service.py`，实现 `EncryptionService.encrypt()` 和 `decrypt()`，存储格式 `base64(iv[12] + tag[16] + ciphertext)`；实现 `EncryptedType` SQLAlchemy TypeDecorator，透明处理 `process_bind_param` / `process_result_value`
    - _需求：10.1、10.3、10.4_
  - [ ]* 3.2 编写属性测试：加密解密 Round-Trip（Property 3）
    - **Property 3: Round-Trip（加密解密一致性）**
    - **Validates: 需求 10.1、10.3、10.4**
  - [ ]* 3.3 编写属性测试：IV 唯一性（Property 4）
    - **Property 4: IV 唯一性**
    - **Validates: 需求 10.3**
  - [x] 3.4 修改 `backend/app/models/op_account.py`，将 `password`、`totp_secret`、`email_password` 字段类型替换为 `EncryptedType`
    - _需求：10.1_

- [x] 4. Alembic 迁移脚本
  - [x] 4.1 在 `backend/alembic/env.py` 中导入 `team.py` 中的所有模型，确保 Alembic 能检测到新表
  - [x] 4.2 创建 `backend/alembic/versions/20260501_0001_add_team_tables.py`，手动编写迁移脚本，`upgrade()` 创建 `users`、`departments`、`roles`、`role_permissions`、`user_roles`、`refresh_tokens`、`operation_tokens`、`login_logs`、`operation_logs` 九张表；`downgrade()` 按依赖顺序删除
    - _需求：2.1、3.1、4.1_

- [x] 5. JWT 认证服务
  - [x] 5.1 创建 `backend/app/core/security.py`，实现：`hash_password()`、`verify_password()`（bcrypt）、`create_access_token()`、`decode_access_token()`（python-jose）
    - _需求：1.1、1.7_
  - [ ]* 5.2 编写属性测试：Token Round-Trip（Property 1）
    - **Property 1: Token Round-Trip（JWT 解析一致性）**
    - **Validates: 需求 1.1**
  - [ ]* 5.3 编写属性测试：密码哈希不可逆（Property 2）
    - **Property 2: 密码哈希不可逆**
    - **Validates: 需求 1.7**
  - [x] 5.4 创建 `backend/app/services/auth_service.py`，实现：
    - `login(username, password, ip, db)` — 验证密码、检查账号状态、登录失败计数（15分钟内5次锁定15分钟）、签发 Access Token + Refresh Token（UUID，SHA-256 哈希存库）、记录 `login_log`
    - `refresh_token(token, db)` — 查库验证、检测重放攻击（已使用则吊销全部 token）、Rotation 签发新 token 对
    - `logout(user_id, token, db)` — 吊销当前 Refresh Token
    - `get_current_user(token, db)` — JWT 解码，返回 User 对象，401 on invalid
    - _需求：1.1、1.2、1.3、1.4、1.5、1.5a、1.6、1.8_

- [x] 6. 权限依赖与 Super_Admin 初始化
  - [x] 6.1 在 `backend/app/services/auth_service.py` 中新增 `require_permission(perm: str)` FastAPI 依赖工厂，Super_Admin 直接放行，否则检查用户角色权限并集；无权限返回 403
    - _需求：5.1、5.2、5.3、5.4_
  - [x] 6.2 在 `backend/app/main.py` 的 `lifespan` 中新增 `create_super_admin(db)` 调用：若 `users` 表中不存在 `is_super_admin=True` 的用户，则创建 `admin` 账号（密码取自 `SUPER_ADMIN_PASSWORD` 环境变量，默认 `admin123456`，bcrypt 哈希存储）
    - _需求：9.1、9.4_

- [x] 7. API 限流中间件
  - [x] 7.1 创建 `backend/app/middleware/rate_limit.py`，使用 `slowapi` 配置：
    - 登录接口 IP 限流：10次/分钟
    - 登录接口用户名限流：5次/分钟
    - 采集接口用户限流：3次/分钟
    - 导出接口用户限流：5次/分钟
    - 全局 IP 限流：300次/分钟
    - 超出返回 429，响应头含 `Retry-After`
    - _需求：11.1、11.2、11.3、11.4、11.5_
  - [x] 7.2 在 `backend/app/main.py` 中注册 `slowapi` Limiter 和 `_rate_limit_exceeded_handler`
    - _需求：11.1_

- [x] 8. 操作日志中间件
  - [x] 8.1 创建 `backend/app/middleware/operation_log.py`，实现 `OperationLogMiddleware`（Starlette BaseHTTPMiddleware）：
    - 拦截 POST/PUT/DELETE 请求及导出接口
    - 从 JWT 解析操作人用户名（未登录则跳过）
    - 根据请求路径映射 `module` 和 `action`（CREATE/UPDATE/DELETE/EXPORT）
    - 执行请求后记录 `operation_log`，无论成功失败均记录，失败时记录 `error` 摘要
    - _需求：8.1、8.2、8.6_
  - [x] 8.2 在 `backend/app/main.py` 中注册 `OperationLogMiddleware`
    - _需求：8.2_

- [x] 9. 认证 API
  - [x] 9.1 创建 `backend/app/api/auth.py`，实现以下路由（均无需权限校验）：
    - `POST /api/auth/login` — 调用 `auth_service.login()`，返回 `access_token`、`refresh_token`、`user` 信息、`permissions` 列表
    - `POST /api/auth/refresh` — 调用 `auth_service.refresh_token()`
    - `POST /api/auth/logout` — 调用 `auth_service.logout()`，需要已登录
    - `POST /api/auth/verify-password` — 验证当前用户密码，正确则签发 `OperationToken`（有效期5分钟，存 `operation_tokens` 表），返回 `operation_token`
    - _需求：1.1、1.4、1.6、12.2、12.4_
  - [x] 9.2 在 `backend/app/main.py` 中注册 `auth.router`，前缀 `/api/auth`
    - _需求：5.6_

- [x] 10. 团队管理服务层
  - [x] 10.1 创建 `backend/app/services/team_service.py`，实现部门服务：
    - `get_dept_tree(db)` — 递归构建树形结构
    - `create_dept(data, db)` — 验证父部门存在、同级名称唯一，创建节点
    - `update_dept(id, data, db)` — 更新名称，检查循环引用（祖先链不含自身）
    - `delete_dept(id, db)` — 检查子部门和成员，均为空才删除
    - _需求：2.1、2.2、2.3、2.4、2.5、2.6、2.7、2.8、2.9_
  - [x] 10.2 在 `team_service.py` 中实现成员服务：
    - `list_members(dept_id, username, is_active, page, size, db)` — 分页过滤查询
    - `create_member(data, db)` — 用户名唯一校验、密码长度校验、bcrypt 哈希、分配角色
    - `update_member(id, data, db)` — 更新信息，禁止操作 Super_Admin
    - `delete_member(id, db)` — 禁止删除 Super_Admin，吊销其所有 Refresh Token
    - `disable_member(id, db)` — 禁止禁用 Super_Admin，吊销 Refresh Token，幂等
    - `reset_password(id, new_password, db)` — bcrypt 哈希，吊销 Refresh Token
    - _需求：3.1、3.2、3.3、3.4、3.5、3.6、3.7、3.8、3.9_
  - [x] 10.3 在 `team_service.py` 中实现角色服务：
    - `list_roles(db)` — 返回角色列表含权限
    - `create_role(data, db)` — 名称唯一校验、权限标识符合法性校验（仅接受预定义权限集）
    - `update_role(id, data, db)` — 更新权限，权限标识符合法性校验
    - `delete_role(id, db)` — 检查是否有成员使用，有则返回 400
    - _需求：4.1、4.2、4.3、4.4、4.5、4.6_

- [x] 11. 团队管理 API
  - [x] 11.1 创建 `backend/app/api/team.py`，实现部门路由（绑定对应权限依赖）：
    - `GET /api/team/dept/tree` → `team:dept:view`
    - `POST /api/team/dept` → `team:dept:create`
    - `PUT /api/team/dept/{id}` → `team:dept:edit`
    - `DELETE /api/team/dept/{id}` → `team:dept:delete`
    - _需求：2、5.5_
  - [x] 11.2 在 `team.py` 中实现成员路由：
    - `GET /api/team/member` → `team:member:view`
    - `POST /api/team/member` → `team:member:create`
    - `PUT /api/team/member/{id}` → `team:member:edit`
    - `DELETE /api/team/member/{id}` → `team:member:delete`（需携带有效 Operation Token）
    - `POST /api/team/member/{id}/reset-password` → `team:member:reset_password`（需携带有效 Operation Token）
    - _需求：3、5.5、12.1、12.5_
  - [x] 11.3 在 `team.py` 中实现角色路由：
    - `GET /api/team/role` → `team:role:view`
    - `POST /api/team/role` → `team:role:create`
    - `PUT /api/team/role/{id}` → `team:role:edit`
    - `DELETE /api/team/role/{id}` → `team:role:delete`
    - _需求：4、5.5_
  - [x] 11.4 在 `team.py` 中实现日志路由（只读，无 UPDATE/DELETE）：
    - `GET /api/team/log/login` → `team:log:view`，支持按用户名/时间范围/结果过滤，分页
    - `GET /api/team/log/operation` → `team:log:view`，支持按操作人/时间范围/模块/类型过滤，分页
    - _需求：7.3、8.3、8.5_
  - [x] 11.5 在 `backend/app/main.py` 中注册 `team.router`，前缀 `/api/team`；为现有 `op_accounts`、`settings`、`monitor` 等路由添加 `require_permission` 依赖（按需求 5.5 映射）
    - _需求：5.5、5.6_

- [x] 12. 检查点 — 后端核心功能验证
  - 确保所有后端测试通过，检查 `EncryptionService`、`auth_service`、`team_service` 的核心逻辑，向用户确认是否有疑问。

- [x] 13. 前端认证 Store 与 API 层
  - [x] 13.1 创建 `frontend/src/api/auth.js`，封装：`login(username, password)`、`refreshToken(token)`、`logout()`、`verifyPassword(password)`
    - _需求：1.1、12.2_
  - [x] 13.2 创建 `frontend/src/api/team.js`，封装部门、成员、角色、日志的 CRUD 请求
    - _需求：2、3、4、7.3、8.3_
  - [x] 13.3 创建 `frontend/src/stores/auth.js`（Pinia store），包含：
    - state: `token`、`refreshToken`、`user`、`permissions`
    - actions: `login()`、`logout()`、`refreshAccessToken()`（自动刷新）
    - getters: `hasPermission(perm)`、`isLoggedIn`
    - 持久化到 `localStorage`
    - _需求：1.1、6.1、6.5_
  - [x] 13.4 修改 `frontend/src/api/request.js`（axios 实例），添加请求拦截器（自动附加 `Authorization: Bearer token`）和响应拦截器（401 时自动调用 `refreshAccessToken()`，刷新失败则跳转 `/login`）
    - _需求：1.4、6.6_

- [ ] 14. 前端路由守卫与权限指令
  - [ ] 14.1 修改 `frontend/src/router/index.js`：
    - 新增路由：`/login`、`/403`、`/team/dept`、`/team/member`、`/team/role`、`/team/log`，各路由设置 `meta.requiresAuth` 和 `meta.permission`
    - 添加 `beforeEach` 守卫：未登录跳 `/login`，无权限跳 `/403`
    - _需求：6.2、6.4_
  - [ ] 14.2 创建 `frontend/src/directives/permission.js`，实现 `v-permission` 指令：无权限时从 DOM 移除元素；在 `frontend/src/main.js` 中全局注册
    - _需求：6.3_

- [ ] 15. 前端登录页与 403 页
  - [ ] 15.1 创建 `frontend/src/views/Login.vue`：用户名/密码表单、调用 `authStore.login()`、成功后跳转首页、失败显示错误信息
    - _需求：1.1、1.2、1.3_
  - [ ] 15.2 创建 `frontend/src/views/Forbidden.vue`：403 提示页，含返回首页按钮
    - _需求：6.4_

- [ ] 16. 修改 Layout.vue — 动态菜单与登出
  - 修改 `frontend/src/components/Layout.vue`：
    - 从 `useAuthStore` 读取 `permissions`，按权限动态渲染菜单项（`v-if="authStore.hasPermission('xxx:view')"`）
    - 新增团队管理子菜单（部门/成员/角色/日志），按对应 `team:*:view` 权限控制显示
    - 右上角新增用户名显示和登出按钮，点击调用 `authStore.logout()` 后跳转 `/login`
    - _需求：6.2、6.5_

- [ ] 17. 团队管理前端页面
  - [ ] 17.1 创建 `frontend/src/views/team/DeptManage.vue`：
    - 左侧 `el-tree` 展示部门树，支持新增/编辑/删除节点
    - 删除时若有子部门或成员则显示错误提示
    - _需求：2.4、2.6、2.7、2.8_
  - [ ] 17.2 创建 `frontend/src/views/team/MemberManage.vue`：
    - 顶部部门筛选 + 用户名/状态搜索，分页表格
    - 新增/编辑对话框（含角色多选）
    - 删除和重置密码按钮添加锁形图标，触发二次确认弹窗（输入当前登录密码 → 调用 `verifyPassword` → 携带 `operation_token` 执行操作）
    - _需求：3.9、12.1、12.6_
  - [ ] 17.3 创建 `frontend/src/views/team/RoleManage.vue`：
    - 角色列表表格，新增/编辑对话框
    - 权限矩阵：按模块分组展示所有预定义权限，复选框勾选
    - _需求：4.1、4.2、4.3_
  - [ ] 17.4 创建 `frontend/src/views/team/LogView.vue`：
    - `el-tabs` 切换登录日志/操作日志
    - 各 tab 含时间范围选择器、关键字过滤、分页表格
    - _需求：7.3、8.3_

- [ ] 18. 最终检查点 — 全链路验证
  - 确保所有测试通过，验证登录流程、权限控制、加密存储、限流、日志记录端到端正常，向用户确认是否有疑问。

## 备注

- 标有 `*` 的子任务为可选测试任务，可跳过以加快 MVP 交付
- 每个任务均引用具体需求条款，确保可追溯性
- 检查点任务确保增量验证，避免集成时出现大量问题
- Property 测试验证设计文档中定义的正确性属性（Property 1-4）
- Operation Token 验证逻辑：后端在需要二次确认的接口中检查请求头 `X-Operation-Token`，查库验证 `is_used=False` 且未过期，验证通过后立即标记 `is_used=True`
