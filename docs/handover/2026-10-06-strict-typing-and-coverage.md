# 严格类型与覆盖率门禁收敛

日期：2026-10-06。接续 Windows 1.1.15 本地包与冒烟通过后的工作。构建前源码 HEAD `9745eac`；用户此前 commit/push 授权延续，团队更新仍由用户在网页操作。

## 结果

- 基线：418 项测试通过，覆盖率 71.63% 不达 80%；严格 mypy 924 个错误，73 个源码文件。
- 最终正式验证：448 项测试通过，覆盖率 **83.59%**；严格 mypy **73 文件、0 错误**；前端构建通过。
- 门禁阈值、mypy strict、现有 `backend/mypy.ini` 未降低或修改。
- 独立复审三路均 `[P1] none; [P2] none; GATE PASS; APPROVE`。
- 本轮没有数据库迁移或接口契约变更。历史 Windows 1.1.15 包尚未包含本轮源码；本轮未重新生成安装器、Release 或升级团队服务器。

## 源码改动

1. 旧式 SQLAlchemy `Column` 声明改为原生 `Mapped[T]`/`mapped_column`，准确描述可空字段、日期、Decimal、JSON 和关系。保留原列参数、枚举值、默认值、onupdate、外键、索引及级联；原来隐式 nullable=True 的字段仍保持可空。
2. 数据库依赖、FastAPI 参数、Pydantic 验证器、服务查询和回调补准确类型。稳定返回结构使用 TypedDict；JSON/Pydantic/第三方库动态边界仅局部转换，不以全局 Any 或忽略规则覆盖业务检查。
3. FastAPI 以前没有显式响应模型的未标注路由，在增加返回类型时设 `response_model=None`，避免新类型注解自动改变响应序列化。既有显式模型保持不变，完整 OpenAPI 前后相同。
4. 新增 `requirements-dev.txt`，统一 pytest/mypy 与 python-jose/passlib/openpyxl/aiofiles 类型声明包。APScheduler 3.10 没有可用类型包，两条实际导入使用精确 `import-untyped` 忽略，调度回调和 Session 工厂仍有类型。
5. 用两个新测试文件覆盖监控采集/视频/任务、项目和权限范围、代理、历史趋势、批量操作、CSV/XLSX 导入导出。网络模拟、临时 SQLite、首轮后台线程定向替换，禁止触碰真实数据库或外部采集。
6. 回归测试发现真实导出缺陷：`follower_change_24h` 等字段以前去掉后缀后读取 `follower`，实际字段是 `follower_count`，因此变化恒为 0。CSV/Excel 两处分支改成映射 `_change_24h` 到 `_count`；保留列名、顺序、成功历史窗口、正负号、零值和无历史 `-` 语义。

## 验证

正式序列从 backend 目录逐步执行，任何非零立即停止。使用合成密钥、PYTHONUTF8=1、仓库根/backend PYTHONPATH，Windows PATH 前置 Git Bash；没有修改真实 .env。PowerShell 日志为 UTF-16，读取使用 `-Encoding Unicode`。

最终日志：`desktop/build/typing-coverage-final-gate-2.log`。

| 命令 | 实际退出码 | 结果 |
| --- | --- | --- |
| `python -m pip install -r ../requirements-dev.txt` | 0 | 类型声明及验证工具安装成功 |
| `python -m compileall app` | 0 | 编译通过 |
| `python -m pytest --cov=app --cov-report=term-missing --cov-fail-under=80` | 0 | 448 passed，7635 语句/1253 未覆盖，83.59% |
| `python -m mypy app --strict` | 0 | 73 文件零错误 |
| 前端目录 `npm run build` | 0 | 既有 Vite CJS/动态导入/大 chunk 警告，构建成功 |

独立证据：

- 383 个列/关系声明构造参数前后一致；33 张表、33 个 mapper 的类型、默认值、nullable、约束、索引谓词、FK、关系 direction/uselist/cascade/backref/back_populates/lazy/passive_deletes 和 SQLite DDL 完全一致。
- 临时内存库中加密、JSON、枚举、默认值和关系 roundtrip 通过；全量 Alembic 新库升级及 `alembic.check` 无新增操作。
- OpenAPI 114 路径、147 方法路由、85 schema 与修改前 JSON 完全相同。
- API 专项 123 项、设备/关联专项 33 项、迁移/粉丝/昨日汇总专项 19 项均通过。
- 新增 30 项测试通过，CSV/XLSX 正增长 `+10`、下降 `-2`、不变 `0`、无历史 `-` 均有断言。
- 独立 teardown 审计逐项检查新测试涉及的 13 张表，30 项结束后均为空，无新数据泄漏。
- `git -c core.whitespace=cr-at-eol diff --check` 通过；仓库旧文件混合 CRLF/LF，以该命令区分行尾 CR 和真正尾部空格。

本地证据文件位于 `.orchestration/`：`model-metadata-before.json`、`model-metadata-after.json`、`verify_model_metadata.py`、`api-openapi-before.json`、`mypy-final.txt`。这些是本机核验产物，不纳入应用发布包。

## 审查记录

本轮使用运行时子代理独立只读审查，没有恢复旧 Orca 提供者会话；模型、API、服务和新增测试文件职责分开。审查提案通过后才编辑，审查者没有修改被审内容。

CODEX SAYS（模型提案）：[P1] none；[P2] 表元数据对比还需包含关系基数和 SQLite DDL。GATE PASS；APPROVE。已补前后精确对比。

CODEX SAYS（API/schema 复审）：[P1] none；[P2] none；GATE PASS；APPROVE。显式响应模型及原参数默认值保持不变，完整 OpenAPI 一致，动态类型只在实际 JSON/Pydantic 边界。

CODEX SAYS（服务/core 复审）：[P1] none；[P2] 已知 Cell 与 SQLAlchemy 更新映射可进一步收窄。GATE PASS；APPROVE。收窄后复核：[P1] none；[P2] none；GATE PASS；APPROVE。认证、权限、加密和序列化原行为保持，导出修复有真实断言。

CODEX SAYS（模型/设备/关系/测试复审）：[P1] none；[P2] none；GATE PASS；APPROVE。元数据与迁移无变化，设备/关联专项和新增测试隔离审计通过。

## 失败与限制

- 早期专项从根目录启动，未设置合成配置/PYTHONUTF8，先后在安全配置和 GBK 读取处拒绝启动；补本次进程环境后通过，未修改真实配置。
- 并发注解编辑期间曾暂时缺少 User 导入、括号未闭合；修复后重新完成全量验证，不把这些失败当作通过。
- 第一次正式序列 pytest/mypy 通过后，PowerShell `ErrorActionPreference=Stop` 把 Vite 的 stderr 警告误当命令异常；单独构建实际 exit 0。最终第二序列捕获真实工具退出码，全部通过。
- 独立初次覆盖率测量为 80.89%，最终固定正式序列连续两次均 83.59%；以最终命令及日志为准，不比较不同并发测量的逐模块计数。
- 既有弃用告警（datetime.utcnow、Pydantic Config、测试客户端等）未在类型修复中扩大处理。
- `conftest` 旧全局清理不覆盖所有运营/监控表；新测试有自己完整清理，未扩大该历史范围。全量 448 项通过不代表所有线上输入或网络可用性已验收。
- Windows 真实在线升级、跨重启更新锁、无 WebView2 干净机和物理混合 DPI 验收仍按 Windows 交接记录后续处理。

## 后续

1. 本轮源码和验证记录单独 commit/push，保留旧截图删除及备份/发布包等用户工作区内容。
2. 需要发布本轮业务源码时使用新的版本和产物，不覆盖已审计的 1.1.15 包。新后端载荷进入 Windows 包后必须重新打包及冒烟。
3. 团队服务器仍由用户点击更新；当前不会主动重启或升级服务器。
