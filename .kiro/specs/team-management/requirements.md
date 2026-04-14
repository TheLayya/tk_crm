# 需求文档

## 简介

本文档描述为现有 TikTok Monitor 系统新增团队管理模块的功能需求。现有系统（FastAPI + Vue3）目前无任何认证机制，所有接口均为公开访问。本次新增功能包括：用户认证（JWT）、多级部门管理、成员管理、基于 RBAC 的角色权限管理（菜单级 + 按钮级）、敏感数据加密存储、API 限流、以及登录日志与操作日志。

**安全背景**：系统存储运营账号的密码、2FA 密钥、邮箱密码等高度敏感信息，安全防护是最高优先级。一旦数据库泄露，所有账号将面临被一锅端的风险，因此必须在存储层、传输层、认证层三个维度同时加固。

## 词汇表

- **System**：整个 TikTok Monitor 后端服务
- **Auth_Service**：负责用户认证、Token 签发与校验的服务模块
- **User**：系统中的登录账号，对应一名团队成员
- **Super_Admin**：系统内置的超级管理员账号，拥有全部权限，不可删除，不受权限控制
- **Department**：组织架构中的部门节点，支持无限层级嵌套，形成树形结构
- **Member**：归属于某个部门的用户账号
- **Role**：自定义角色，包含一组菜单权限和按钮权限
- **Permission**：对特定菜单或按钮操作的访问授权
- **Menu_Permission**：对某个菜单页面的访问权限
- **Button_Permission**：对某个操作按钮（新增/编辑/删除/导出/重置密码/采集/账号检查等）的执行权限
- **JWT_Token**：JSON Web Token，用于无状态身份认证的访问令牌
- **Refresh_Token**：用于在 Access Token 过期后换取新 Access Token 的长效令牌
- **Login_Log**：记录用户登录行为的日志条目
- **Operation_Log**：记录用户对系统数据执行增删改导出等操作的日志条目
- **RBAC**：基于角色的访问控制（Role-Based Access Control）
- **Encryption_Service**：负责对敏感字段进行 AES-256-GCM 加密/解密的服务模块
- **Encryption_Key**：AES-256 加密主密钥，通过环境变量 `FIELD_ENCRYPTION_KEY` 注入，不得硬编码在代码中
- **Rate_Limiter**：API 限流中间件，基于 IP + 用户名对高风险接口进行请求频率限制
- **Sensitive_Field**：运营账号中需要加密存储的字段：password、totp_secret、email_password

---

## 需求

### 需求 1：用户认证

**用户故事：** 作为团队成员，我希望通过用户名和密码登录系统，以便安全地访问我有权限的功能。

#### 验收标准

1. WHEN 用户提交有效的用户名和密码，THE Auth_Service SHALL 返回一个 Access Token（有效期 **30 分钟**）和一个 Refresh Token（有效期 7 天）。
2. WHEN 用户提交不存在的用户名或错误的密码，THE Auth_Service SHALL 返回 HTTP 401 状态码及错误描述，不得泄露具体失败原因（用户名不存在 vs 密码错误）。
3. WHEN 用户账号处于禁用状态时提交登录请求，THE Auth_Service SHALL 返回 HTTP 403 状态码及"账号已禁用"提示。
4. WHEN 客户端携带有效且未过期的 Refresh Token 请求刷新，THE Auth_Service SHALL 签发新的 Access Token 和新的 Refresh Token，并**立即使旧 Refresh Token 失效**（单次使用，Refresh Token Rotation）。
5. WHEN 客户端携带已过期或无效的 Refresh Token 请求刷新，THE Auth_Service SHALL 返回 HTTP 401 状态码，要求重新登录。
5a. IF 一个 Refresh Token 被使用超过一次（检测到 Token 重用），THEN THE Auth_Service SHALL 立即吊销该用户的所有 Refresh Token，强制全部设备重新登录，并记录安全告警日志。
6. WHEN 用户请求登出，THE Auth_Service SHALL 将该用户的 Refresh Token 加入黑名单，使其立即失效。
7. THE Auth_Service SHALL 对存储的用户密码使用 bcrypt 算法进行哈希处理，不得以明文形式存储密码。
8. WHEN 连续 5 次登录失败（同一用户名，15 分钟内），THE Auth_Service SHALL 锁定该账号 15 分钟，并返回 HTTP 429 状态码。

#### 正确性属性

- **Round-Trip（Token 解析）**：对任意有效用户，Auth_Service 签发的 JWT_Token 经解析后，所得用户 ID、用户名、权限列表与签发时的输入数据完全一致。
- **不变量（密码哈希）**：对任意明文密码，bcrypt 哈希结果与原始明文不相等，且对同一明文多次哈希结果不同（加盐），但验证函数均返回 true。

---

### 需求 2：多级部门管理

**用户故事：** 作为管理员，我希望创建和维护多级树形部门结构，以便按组织架构管理团队成员。

#### 验收标准

1. THE System SHALL 支持无限层级的部门嵌套，每个部门节点包含：部门名称、父部门 ID（顶级部门为 null）、创建时间、更新时间。
2. WHEN 管理员创建部门时指定父部门 ID，THE System SHALL 验证父部门存在，并将新部门挂载为其子节点。
3. WHEN 管理员创建部门时不指定父部门 ID，THE System SHALL 将新部门创建为顶级部门。
4. WHEN 管理员请求部门树，THE System SHALL 返回完整的树形结构数据，包含每个节点的子节点列表。
5. WHEN 管理员更新部门名称，THE System SHALL 保存更新后的名称，不影响其父子关系。
6. WHEN 管理员删除一个含有子部门的部门，THE System SHALL 返回 HTTP 400 错误，提示"请先删除或迁移子部门"。
7. WHEN 管理员删除一个含有成员的部门，THE System SHALL 返回 HTTP 400 错误，提示"请先移除部门成员"。
8. WHEN 管理员删除一个无子部门且无成员的部门，THE System SHALL 将该部门从数据库中删除。
9. IF 部门名称在同一父部门下已存在，THEN THE System SHALL 返回 HTTP 409 错误，提示"同级部门名称重复"。

#### 正确性属性

- **不变量（无环）**：对任意部门树操作（创建、更新父节点），System 不得产生循环引用（部门 A 的祖先链中不包含 A 自身）。
- **不变量（树完整性）**：对任意部门节点，其 parent_id 所指向的父部门必须存在于数据库中，或为 null（顶级节点）。

---

### 需求 3：成员管理

**用户故事：** 作为管理员，我希望管理团队成员账号，包括创建、编辑、禁用和分配角色，以便控制人员访问权限。

#### 验收标准

1. THE System SHALL 为每个成员存储以下信息：用户名（唯一）、密码哈希、真实姓名、所属部门 ID、角色列表、账号状态（启用/禁用）、创建时间、更新时间。
2. WHEN 管理员创建成员时提供已存在的用户名，THE System SHALL 返回 HTTP 409 错误，提示"用户名已存在"。
3. WHEN 管理员创建成员时，THE System SHALL 要求密码长度不少于 8 个字符。
4. IF 管理员提交的密码长度少于 8 个字符，THEN THE System SHALL 返回 HTTP 422 错误，提示"密码长度不得少于 8 个字符"。
5. WHEN 管理员为成员分配角色，THE System SHALL 支持一个成员同时持有多个角色，其有效权限为所有角色权限的并集。
6. WHEN 管理员禁用成员账号，THE System SHALL 将该成员的所有有效 Refresh Token 加入黑名单，使其立即下线。
7. WHEN 管理员重置成员密码，THE System SHALL 将新密码以 bcrypt 哈希后存储，并使该成员的所有有效 Refresh Token 失效。
8. THE System SHALL 禁止删除或禁用 Super_Admin 账号。
9. WHEN 管理员查询成员列表，THE System SHALL 支持按部门、用户名、账号状态进行过滤，并返回分页结果。

#### 正确性属性

- **不变量（权限并集）**：对任意持有多个角色的成员，其有效权限集合等于所有角色权限集合的并集，不多也不少。
- **幂等性（禁用操作）**：对已处于禁用状态的成员再次执行禁用操作，System 返回成功，成员状态保持禁用，不产生副作用。

---

### 需求 4：角色与权限管理

**用户故事：** 作为管理员，我希望创建自定义角色并为其分配菜单权限和按钮权限，以便实现精细化的访问控制。

#### 验收标准

1. THE System SHALL 支持管理员创建自定义角色，每个角色包含：角色名称（唯一）、描述、菜单权限列表、按钮权限列表。
2. THE System SHALL 内置以下菜单权限定义：
   - `monitor:view`（监控管理-查看）
   - `monitor:check`（监控管理-账号检查）
   - `op_account:view`（运营账号-查看）
   - `op_account:create`（运营账号-新增）
   - `op_account:edit`（运营账号-编辑）
   - `op_account:delete`（运营账号-删除）
   - `op_account:import`（运营账号-导入）
   - `op_account:export`（运营账号-导出）
   - `op_account:collect`（运营账号-采集）
   - `settings:view`（系统设置-查看）
   - `settings:edit`（系统设置-编辑）
   - `team:dept:view`（部门管理-查看）
   - `team:dept:create`（部门管理-新增）
   - `team:dept:edit`（部门管理-编辑）
   - `team:dept:delete`（部门管理-删除）
   - `team:member:view`（成员管理-查看）
   - `team:member:create`（成员管理-新增）
   - `team:member:edit`（成员管理-编辑）
   - `team:member:delete`（成员管理-删除）
   - `team:member:reset_password`（成员管理-重置密码）
   - `team:role:view`（角色管理-查看）
   - `team:role:create`（角色管理-新增）
   - `team:role:edit`（角色管理-编辑）
   - `team:role:delete`（角色管理-删除）
   - `team:log:view`（日志查看-查看）
3. WHEN 管理员为角色分配权限，THE System SHALL 仅接受上述已定义的权限标识符，拒绝未知权限标识符并返回 HTTP 422 错误。
4. WHEN 管理员删除一个已被成员使用的角色，THE System SHALL 返回 HTTP 400 错误，提示"该角色已被 N 名成员使用，请先解除关联"。
5. WHEN 管理员更新角色的权限列表，THE System SHALL 立即使持有该角色的所有在线用户的权限缓存失效，确保下次请求时使用最新权限。
6. IF 角色名称已存在，THEN THE System SHALL 返回 HTTP 409 错误，提示"角色名称已存在"。

#### 正确性属性

- **不变量（权限标识符合法性）**：System 存储的所有角色权限列表中，每个权限标识符必须属于系统预定义的权限集合。
- **Metamorphic（权限更新传播）**：角色 R 的权限更新后，持有角色 R 的成员 M 在下一次 API 请求中获取到的有效权限，必须反映最新的角色权限，而非更新前的旧权限。

---

### 需求 5：后端 API 权限校验

**用户故事：** 作为系统，我希望对每个 API 接口进行权限校验，以便确保用户只能访问其被授权的功能。

#### 验收标准

1. WHEN 请求携带有效 JWT_Token 且用户持有所需权限，THE Permission_Decorator SHALL 允许请求通过，执行业务逻辑。
2. WHEN 请求未携带 JWT_Token 或携带无效 JWT_Token，THE Permission_Decorator SHALL 返回 HTTP 401 状态码。
3. WHEN 请求携带有效 JWT_Token 但用户不持有所需权限，THE Permission_Decorator SHALL 返回 HTTP 403 状态码。
4. WHILE Super_Admin 发起请求，THE Permission_Decorator SHALL 跳过权限检查，直接允许所有请求通过。
5. THE System SHALL 为以下操作绑定对应权限：
   - GET /api/monitor/* → `monitor:view`
   - POST /api/monitor/*/check → `monitor:check`
   - GET /api/op-accounts/* → `op_account:view`
   - POST /api/op-accounts → `op_account:create`
   - PUT /api/op-accounts/* → `op_account:edit`
   - DELETE /api/op-accounts/* → `op_account:delete`
   - POST /api/op-accounts/import → `op_account:import`
   - GET /api/op-accounts/export → `op_account:export`
   - POST /api/op-accounts/collect → `op_account:collect`
   - GET /api/settings → `settings:view`
   - PUT /api/settings → `settings:edit`
   - 团队管理各接口 → 对应 `team:*` 权限
6. THE System SHALL 对登录接口（POST /api/auth/login）和健康检查接口（GET /health）不进行权限校验。

#### 正确性属性

- **属性（权限拒绝完备性）**：对任意不持有权限 P 的非 Super_Admin 用户，访问需要权限 P 的任意接口，Permission_Decorator 必须返回 HTTP 403，不得因权限标识符格式或接口路径的变化而产生漏洞。
- **属性（Super_Admin 全通）**：Super_Admin 访问系统中任意已定义接口，Permission_Decorator 必须返回允许，不得因权限列表为空或其他条件而拒绝。

---

### 需求 6：前端动态权限渲染

**用户故事：** 作为登录用户，我希望前端界面根据我的权限动态显示菜单和操作按钮，以便获得清晰的操作界面。

#### 验收标准

1. WHEN 用户登录成功，THE System SHALL 在登录响应中返回该用户的完整权限列表（权限标识符数组）。
2. WHEN 前端加载布局，THE System SHALL 仅在侧边栏渲染用户持有 `view` 权限的菜单项（如无 `monitor:view` 则不显示"监控管理"菜单）。
3. WHEN 前端渲染操作按钮，THE System SHALL 仅显示用户持有对应按钮权限的操作按钮（如无 `op_account:delete` 则不显示"删除"按钮）。
4. WHEN 用户直接通过 URL 访问无权限的页面，THE System SHALL 重定向至 403 提示页面。
5. WHILE Super_Admin 登录，THE System SHALL 渲染所有菜单和所有操作按钮。
6. WHEN 用户的权限在后端被更新，THE System SHALL 在用户下次刷新页面或 Token 刷新时获取最新权限列表。

#### 正确性属性

- **不变量（菜单可见性一致）**：前端渲染的菜单集合，必须是用户权限列表中所有 `*:view` 权限对应菜单的子集，不得渲染用户无权访问的菜单。

---

### 需求 7：登录日志

**用户故事：** 作为管理员，我希望查看所有用户的登录记录，以便审计系统访问情况和排查安全问题。

#### 验收标准

1. WHEN 用户尝试登录（无论成功或失败），THE System SHALL 记录一条 Login_Log，包含：用户名、登录时间（UTC）、客户端 IP 地址、登录结果（成功/失败）、失败原因（如适用）。
2. WHEN 用户账号被锁定后尝试登录，THE System SHALL 记录登录结果为"失败"，失败原因为"账号已锁定"。
3. THE System SHALL 支持按用户名、时间范围、登录结果对登录日志进行过滤查询，并返回分页结果。
4. THE System SHALL 将登录日志保留至少 90 天。
5. THE System SHALL 禁止任何用户（包括 Super_Admin）删除或修改登录日志记录。

#### 正确性属性

- **不变量（日志完整性）**：每次登录尝试（成功或失败）必须对应恰好一条 Login_Log 记录，不得遗漏，不得重复。

---

### 需求 8：操作日志

**用户故事：** 作为管理员，我希望查看所有用户的操作记录，以便追溯数据变更来源和审计操作行为。

#### 验收标准

1. WHEN 用户执行新增、编辑、删除、导出操作，THE System SHALL 记录一条 Operation_Log，包含：操作人用户名、操作时间（UTC）、操作模块（如"运营账号"、"部门管理"）、操作类型（CREATE/UPDATE/DELETE/EXPORT）、操作内容摘要（如"新增用户 zhangsan"）、客户端 IP 地址、操作结果（成功/失败）。
2. THE System SHALL 通过 FastAPI 中间件或装饰器自动记录操作日志，不依赖业务代码手动调用。
3. THE System SHALL 支持按操作人、时间范围、操作模块、操作类型对操作日志进行过滤查询，并返回分页结果。
4. THE System SHALL 将操作日志保留至少 90 天。
5. THE System SHALL 禁止任何用户（包括 Super_Admin）删除或修改操作日志记录。
6. IF 操作执行失败（业务异常或系统异常），THEN THE System SHALL 仍然记录该操作日志，操作结果标记为"失败"，并记录错误摘要。

#### 正确性属性

- **不变量（日志不可篡改）**：Operation_Log 表不提供 UPDATE 或 DELETE 接口，任何通过 API 发起的修改或删除操作日志的请求，System 必须返回 HTTP 405 或 HTTP 403。
- **不变量（操作覆盖完整性）**：对系统中所有标记为需要记录日志的操作类型（CREATE/UPDATE/DELETE/EXPORT），每次成功或失败的执行均对应恰好一条 Operation_Log 记录。

---

### 需求 9：超级管理员

**用户故事：** 作为系统，我希望内置一个不受权限控制的超级管理员账号，以便在任何情况下都能管理系统。

#### 验收标准

1. THE System SHALL 在首次启动时自动创建 Super_Admin 账号，默认用户名为 `admin`，默认密码通过环境变量 `SUPER_ADMIN_PASSWORD` 配置，若未配置则使用 `admin123456`。
2. THE System SHALL 禁止通过任何 API 接口删除 Super_Admin 账号。
3. THE System SHALL 禁止通过任何 API 接口禁用 Super_Admin 账号。
4. WHILE Super_Admin 发起 API 请求，THE System SHALL 跳过所有权限检查，允许访问全部接口。
5. THE System SHALL 允许 Super_Admin 修改自身密码。
6. IF 管理员尝试通过 API 删除或禁用 Super_Admin，THEN THE System SHALL 返回 HTTP 403 错误，提示"超级管理员不可删除或禁用"。

#### 正确性属性

- **属性（Super_Admin 不可删除不变量）**：无论执行多少次删除或禁用操作，Super_Admin 账号始终存在于数据库中且处于启用状态。

---

### 需求 10：敏感字段加密存储

**用户故事：** 作为系统，我希望将运营账号的密码、2FA 密钥、邮箱密码等敏感字段加密后存储，以便即使数据库文件泄露，攻击者也无法直接获取明文凭证。

#### 验收标准

1. THE Encryption_Service SHALL 使用 AES-256-GCM 算法对以下 `op_accounts` 表字段进行加密存储：`password`、`totp_secret`、`email_password`。
2. THE Encryption_Service SHALL 从环境变量 `FIELD_ENCRYPTION_KEY` 读取加密主密钥（32 字节 hex 字符串），若未配置则拒绝启动并抛出配置错误。
3. WHEN 写入敏感字段时，THE Encryption_Service SHALL 为每条记录生成唯一的随机 IV（初始化向量），与密文一起存储，不得复用 IV。
4. WHEN 读取敏感字段时，THE Encryption_Service SHALL 使用对应 IV 和主密钥解密，返回明文给授权调用方。
5. WHEN 通过 API 返回敏感字段时，THE System SHALL 仅在用户明确请求查看（点击显示按钮）时返回解密后的明文，列表接口默认不返回敏感字段明文。
6. THE System SHALL 提供密钥轮换机制：管理员可通过命令行工具使用新密钥重新加密所有敏感字段，轮换过程中系统保持可用。
7. IF `FIELD_ENCRYPTION_KEY` 环境变量格式不正确（非 64 位 hex 字符串），THEN THE System SHALL 拒绝启动并输出明确的错误信息。

#### 正确性属性

- **Round-Trip（加密解密一致性）**：对任意明文字符串 P，经 Encryption_Service 加密后再解密，结果必须与 P 完全相同。
- **不变量（IV 唯一性）**：对任意两条不同的加密记录，其存储的 IV 值不得相同（概率上保证，基于随机生成）。
- **不变量（密文不可读）**：数据库中存储的敏感字段值，不得包含原始明文的任何可识别片段。

---

### 需求 11：API 限流

**用户故事：** 作为系统，我希望对高风险接口进行请求频率限制，以便防止暴力破解攻击和资源滥用。

#### 验收标准

1. THE Rate_Limiter SHALL 对登录接口（POST /api/auth/login）按 IP 限制：同一 IP 每分钟最多 10 次请求，超出后返回 HTTP 429 状态码，响应头包含 `Retry-After` 字段。
2. THE Rate_Limiter SHALL 对登录接口按用户名限制：同一用户名每分钟最多 5 次登录尝试，超出后返回 HTTP 429 状态码。
3. THE Rate_Limiter SHALL 对采集接口（POST /api/op-accounts/collect）按用户限制：同一用户每分钟最多 3 次采集触发请求，超出后返回 HTTP 429 状态码。
4. THE Rate_Limiter SHALL 对导出接口（GET /api/op-accounts/export）按用户限制：同一用户每分钟最多 5 次导出请求，超出后返回 HTTP 429 状态码。
5. THE Rate_Limiter SHALL 对所有 API 接口设置全局限流：同一 IP 每分钟最多 300 次请求，超出后返回 HTTP 429 状态码。
6. WHEN 请求被限流，THE System SHALL 在操作日志中记录限流事件（IP、接口、时间）。
7. THE Rate_Limiter SHALL 使用内存存储（基于 `slowapi` 或等效库）实现限流计数，重启后计数重置。

#### 正确性属性

- **不变量（限流阈值）**：对任意 IP 在任意连续 60 秒窗口内，登录接口的请求次数不得超过 10 次（超出的请求必须被拒绝，不得执行业务逻辑）。
- **不变量（限流不影响合法请求）**：在未超出限流阈值的情况下，Rate_Limiter 不得拒绝任何合法请求。

---

### 需求 12：敏感操作二次确认

**用户故事：** 作为系统，我希望对批量删除和全量导出等高风险操作要求用户进行二次确认，以便防止误操作和未授权的数据泄露。

#### 验收标准

1. WHEN 用户触发以下操作时，THE System SHALL 要求用户在前端输入当前登录密码进行二次验证，验证通过后方可执行：
   - 批量删除运营账号（选中数量 ≥ 10 条）
   - 导出运营账号数据（导出数量 ≥ 100 条）
   - 删除成员账号
   - 重置成员密码
2. WHEN 用户提交二次确认密码，THE System SHALL 通过后端接口验证密码正确性，不得仅在前端校验。
3. WHEN 二次确认密码错误，THE System SHALL 返回 HTTP 401 错误，拒绝执行操作，并记录操作日志（操作结果：失败，原因：二次确认失败）。
4. WHEN 二次确认密码正确，THE System SHALL 签发一个有效期为 5 分钟的一次性操作令牌（Operation Token），客户端携带此令牌执行实际操作。
5. WHEN 操作令牌过期或已被使用，THE System SHALL 拒绝执行操作并返回 HTTP 401 错误，要求重新进行二次确认。
6. THE System SHALL 在前端对需要二次确认的操作按钮添加视觉提示（如锁形图标），明确告知用户该操作需要二次验证。

#### 正确性属性

- **不变量（操作令牌单次使用）**：同一个 Operation Token 只能被使用一次，使用后立即失效，不得被重放。
- **不变量（后端强制验证）**：对任意需要二次确认的操作，即使前端跳过二次确认直接发送请求，后端必须拒绝未携带有效 Operation Token 的请求。
