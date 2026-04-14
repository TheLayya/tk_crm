# 需求文档

## 简介

本功能为现有 TikTok 监控系统扩展一个**多平台账号管理模块**，用于替代团队当前使用 Excel/表格管理多平台运营账号（TikTok、YouTube、Instagram、Facebook 等）的方式。

该模块独立于现有的监控账号列表，专注于运营账号的凭证管理、权限标记、采购/出售记录、人员归属及自动化信息采集，支持多人协作查看与编辑。

---

## 词汇表

- **Account_Manager**：多平台账号管理模块，本文档描述的新系统
- **Op_Account**：运营账号，即团队在各平台上运营的账号实体，区别于现有监控账号
- **Platform**：账号所属平台，如 TikTok、YouTube、Instagram、Facebook 等
- **Collector**：采集器，负责通过代理从平台 API 自动获取账号公开信息（sec_uid、user_id 等）
- **Proxy_Pool**：代理池，即现有系统中已管理的 SOCKS 代理集合
- **Importer**：批量导入器，负责解析 CSV 文件并批量创建运营账号
- **Exporter**：批量导出器，负责将账号数据导出为 CSV/Excel 文件
- **User**：系统操作用户（注册人、使用人等角色）
- **AuditLog**：操作日志，记录字段变更历史

---

## 需求

### 需求 1：运营账号数据模型

**用户故事：** 作为运营团队成员，我希望系统能存储每个运营账号的完整信息，以便替代 Excel 表格进行统一管理。

#### 验收标准

1. THE Account_Manager SHALL 为每个 Op_Account 存储以下手动维护字段：账号（登录用户名/ID）、密码、2FA 密钥、绑定邮箱、邮箱密码、邮箱登录地址、绑定手机号、手机管理链接、国家/地区、账号来源（自注册/采购/其他）、备注、当前状态、注册人、使用人、自定义标签。
2. WHEN Op_Account 的 Platform 为 tiktok，THE Account_Manager SHALL 额外存储以下 TikTok 专属权限字段：是否开通中视频、是否开通橱窗、手机直播权限、伴侣直播权限。
3. WHEN Op_Account 的 Platform 为非 tiktok，THE Account_Manager SHALL 不展示 TikTok 专属权限字段，前端隐藏这些列。
4. THE Account_Manager SHALL 为每个 Op_Account 存储以下采集字段：平台用户 ID（user_id）、平台安全 UID（sec_uid/sec_id）、昵称、头像 URL、粉丝数、关注数、点赞数、视频数、账号注册时间、最近采集时间、采集状态。
5. THE Account_Manager SHALL 支持 Platform 字段，取值范围至少包含：tiktok、youtube、instagram、facebook，并支持后续扩展。
6. WHEN 创建 Op_Account 时未提供 Platform 字段，THE Account_Manager SHALL 拒绝创建并返回字段缺失错误。
7. THE Account_Manager SHALL 将 Op_Account 与现有 Project（项目）关联，每个 Op_Account 必须归属于一个项目。
8. THE Account_Manager SHALL 支持 status 字段，枚举值为：正常、自用、封禁、已售。

---

### 需求 2：采购与出售记录

**用户故事：** 作为运营团队成员，我希望记录账号的采购来源和出售信息，以便追踪账号资产的完整生命周期和财务数据。

#### 验收标准

1. THE Account_Manager SHALL 为每个 Op_Account 存储以下采购字段：采购渠道、采购金额、采购日期。
2. THE Account_Manager SHALL 为每个 Op_Account 存储以下出售字段：出售客户、出售金额、出售日期。
3. THE Account_Manager SHALL 支持养号成本字段，记录除采购外的运营投入（如充值、广告费等）。
4. WHEN Op_Account 的 status 被更新为"已售"，THE Account_Manager SHALL 在前端提示用户填写出售客户、出售金额、出售日期字段。
5. THE Account_Manager SHALL 支持按采购渠道、出售客户对账号列表进行过滤查询。

---

### 需求 3：运营账号 CRUD

**用户故事：** 作为运营团队成员，我希望能够新增、查看、编辑和删除运营账号，以便维护账号信息的准确性。

#### 验收标准

1. WHEN 用户提交合法的 Op_Account 创建请求，THE Account_Manager SHALL 创建该账号并返回完整账号信息。
2. WHEN 同一项目下已存在相同平台和相同账号名的 Op_Account，THE Account_Manager SHALL 拒绝创建并返回 409 冲突错误。
3. WHEN 用户提交 Op_Account 更新请求，THE Account_Manager SHALL 仅更新请求中包含的字段，其余字段保持不变。
4. WHEN 用户删除 Op_Account，THE Account_Manager SHALL 级联删除该账号的所有采集历史记录和操作日志。
5. THE Account_Manager SHALL 支持按项目、平台、状态、标签、关键词（账号名/昵称）、采购渠道、出售客户对 Op_Account 列表进行过滤和分页查询。
6. THE Account_Manager SHALL 在列表查询中返回账号的所有手动维护字段、采购/出售字段和采集字段。

---

### 需求 4：批量操作

**用户故事：** 作为运营团队成员，我希望能够批量修改账号状态、批量导入和导出账号数据，以提高操作效率。

#### 验收标准

1. THE Account_Manager SHALL 支持多选账号后批量修改 status 字段，状态枚举为：正常、自用、封禁、已售。
2. WHEN 批量修改状态为"已售"时，THE Account_Manager SHALL 提示用户可选填出售客户、出售金额、出售日期，并批量写入选中账号。
3. THE Importer SHALL 支持通过上传 CSV 文件批量导入 Op_Account，CSV 列头与账号字段对应。
4. WHEN CSV 文件中某行数据缺少必填字段（账号名、平台），THE Importer SHALL 将该行标记为失败并记录原因，不影响其他行的导入。
5. WHEN CSV 文件中某行账号在同一项目下已存在（相同平台+账号名），THE Importer SHALL 将该行标记为重复，不覆盖现有数据。
6. WHEN 批量导入完成，THE Importer SHALL 返回汇总结果，包含：总行数、成功数、重复数、失败数及每行的处理状态。
7. WHEN 批量导入成功创建 Op_Account 后，THE Collector SHALL 自动对新创建的账号触发一次信息采集。
8. THE Exporter SHALL 支持将当前过滤条件下的账号数据导出为 CSV 文件，导出字段包含所有手动维护字段、采购/出售字段和采集字段（敏感字段明文导出）。
9. THE Exporter SHALL 支持导出为 Excel（.xlsx）格式。

---

### 需求 5：自动信息采集

**用户故事：** 作为运营团队成员，我希望系统能自动从平台采集账号的公开信息（如 user_id、sec_uid、粉丝数等），以便减少手动录入工作。

#### 验收标准

1. WHEN Op_Account 首次创建（单个创建或批量导入），THE Collector SHALL 自动触发一次信息采集，采集该账号在对应平台的公开信息。
2. WHEN 采集成功，THE Collector SHALL 将 user_id、sec_uid、昵称、头像 URL、粉丝数、关注数、点赞数、视频数、账号注册时间写入对应 Op_Account 的采集字段，并更新最近采集时间和采集状态为"成功"。
3. IF 采集失败，THEN THE Collector SHALL 将采集状态更新为"失败"并记录错误信息，不修改已有采集字段的值。
4. WHILE 采集任务执行中，THE Collector SHALL 从 Proxy_Pool 中随机选取一个状态为启用的 SOCKS 代理用于请求。
5. IF Proxy_Pool 中无可用代理，THEN THE Collector SHALL 不使用代理直接发起采集请求，并在采集结果中标注"无代理"。
6. WHERE 平台为 tiktok，THE Collector SHALL 复用现有 scraper_service 的 fetch_user_info 方法进行采集。
7. WHERE 平台为非 tiktok（youtube、instagram、facebook），THE Collector SHALL 将采集状态标记为"不支持"，并跳过采集，不报错。采集能力后续按需扩展。

---

### 需求 6：手动触发采集

**用户故事：** 作为运营团队成员，我希望能够手动选择多个账号并触发信息采集，以便在需要时更新账号数据。

#### 验收标准

1. WHEN 用户选择一个或多个 Op_Account 并触发采集，THE Collector SHALL 对每个选中账号依次执行信息采集。
2. THE Collector SHALL 以异步方式执行批量采集任务，不阻塞前端界面响应。
3. WHEN 批量采集任务执行中，THE Account_Manager SHALL 向前端提供任务进度查询接口，返回总数、已完成数、成功数、失败数。
4. WHEN 批量采集全部完成，THE Account_Manager SHALL 将任务状态标记为已完成。
5. WHEN 某个 Op_Account 正在采集中，THE Account_Manager SHALL 拒绝对同一账号的重复采集请求并返回提示信息。

---

### 需求 7：操作日志与状态变更历史

**用户故事：** 作为运营团队管理员，我希望能查看每个账号的操作记录和状态变更历史，以便在多人协作时追溯变更来源。

#### 验收标准

1. WHEN 任意用户对 Op_Account 执行创建、更新、删除操作，THE Account_Manager SHALL 自动记录一条操作日志，包含：操作类型、变更字段名、变更前值、变更后值、操作时间。
2. THE Account_Manager SHALL 提供按账号 ID 查询操作日志的接口，返回该账号的完整变更历史，按时间倒序排列。
3. WHEN Op_Account 的 status 字段发生变更，THE Account_Manager SHALL 在操作日志中单独记录状态变更事件，包含：旧状态、新状态、变更时间。
4. THE Account_Manager SHALL 在前端账号详情或列表中提供"操作历史"入口，展示该账号的状态变更时间线。

---

### 需求 8：账号列表展示与多人协作

**用户故事：** 作为运营团队成员，我希望在一个统一的表格界面中查看和编辑所有运营账号，支持多人同时操作，以便替代 Excel 协作方式。

#### 验收标准

1. THE Account_Manager SHALL 在前端提供运营账号列表页面，以表格形式展示所有账号字段（手动维护字段 + 采购/出售字段 + 采集字段）。
2. THE Account_Manager SHALL 支持在列表页面直接内联编辑账号的手动维护字段（密码、2FA、邮箱、手机、权限标记、备注、状态、注册人、使用人、标签等）。
3. THE Account_Manager SHALL 支持列表页面的列显示/隐藏配置，用户可选择显示哪些列，配置持久化到 localStorage。
4. WHEN 多个用户同时编辑不同账号时，THE Account_Manager SHALL 各自独立保存，不产生数据覆盖冲突。
5. THE Account_Manager SHALL 支持按平台、项目、状态、标签、关键词、采购渠道、出售客户进行列表筛选。
6. THE Account_Manager SHALL 支持列表数据的分页展示，每页默认显示 50 条，支持调整每页数量。

---

### 需求 9：敏感信息安全

**用户故事：** 作为系统管理员，我希望账号密码等敏感信息在界面上默认隐藏，以防止信息泄露。

#### 验收标准

1. THE Account_Manager SHALL 在列表和详情页面中，对密码、邮箱密码、2FA 密钥字段默认以掩码（`******`）显示。
2. WHEN 用户点击显示按钮，THE Account_Manager SHALL 展示对应字段的明文内容。
3. THE Account_Manager SHALL 在数据库中以明文存储密码字段（当前阶段，不做加密处理）。

---

### 需求 10：与现有系统集成

**用户故事：** 作为开发者，我希望新模块能无缝集成到现有系统中，复用已有的项目管理、代理管理等基础设施。

#### 验收标准

1. THE Account_Manager SHALL 复用现有 Project 模型，Op_Account 通过 project_id 与项目关联。
2. THE Account_Manager SHALL 复用现有 Proxy_Pool（MonitorProxy 表）中的代理，采集时从中随机选取启用的 SOCKS 代理。
3. THE Account_Manager SHALL 在前端侧边栏菜单中新增"运营账号"菜单项（路由 `/op-accounts`），与"监控管理"、"系统设置"并列，作为独立页面展示。
4. THE Account_Manager SHALL 使用现有 FastAPI + SQLAlchemy + SQLite 技术栈，新增独立的数据库表和 API 路由，不修改现有表结构。
5. THE Account_Manager SHALL 通过 Alembic 迁移脚本管理新增数据库表的版本控制。
