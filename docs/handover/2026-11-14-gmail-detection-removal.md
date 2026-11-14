# Gmail 检测移除与本地邮箱收尾

## 范围

按用户要求完全移除 Gmail 检测能力，同时保留数据库历史列、Gmail 邮箱账号兼容、CK 栏、Flow 加号提取和邮箱新增/编辑清空。本轮仅做本地实现与验收，未提交、未推送、未打包、未部署。

## 代码变更

- 后端删除 Gmail 检测 API、SMTP/HTTP 检测服务、`email:check` 权限、检测锁、检测请求模型、检测批量字段和各响应/导出字段。
- `OpAccount`、`EmailAccount` 的六个 `gmail_check_*` 历史列继续保留 ORM 映射和数据库列，但不再出现在 API 响应、导出、表格筛选/排序字段中；不新增删列迁移。
- 卡密邮箱领取不再要求 `gmail_check_status == "正常"`，统计中的“正常可用”与领取条件一致。
- 前端删除邮箱管理/运营账号页的检测按钮、列、批量检测入口、API 和权限项；保留 CK 列、详情遮罩、复制 CK、取加号、编辑/新增清空与 Flow 解析。
- 删除仅服务于 Gmail 检测/Google 登录探针的文件：`backend/app/services/gmail_checker_service.py`、`backend/check_gmail.py`、`backend/app/services/google_rpc_response.py`、`backend/probe_google_*`、`backend/scripts/google_identifier_vm.cjs`、`backend/scripts/compare_identifier_runtimes.py`、`backend/scripts/api_call_breakpoints.cjs`、`backend/scripts/api_surface_trace.cjs`、`backend/scripts/audit_*.{py,cjs}` 及对应测试；保留 `test_gmail_accounts.py` 的 Gmail 账号兼容覆盖。
- 文档更新：`README.md`、`docs/EMAIL_MANAGEMENT.md` 移除检测说明并补充 CK；删除 `docs/GMAIL_CHECKER.md`。

## 验证结果

- `backend/.venv312/Scripts/python.exe -m compileall app`：exit 0。
- 定向 pytest（邮箱、卡密、表格资产、CK、CK 迁移）：`141 passed`，exit 0。
- 追加移除面回归后全量 pytest（排除既有 `tests/test_update_tools.py` 收集问题）：`576 passed`，exit 0。该文件从 `backend/` 运行时报 `ModuleNotFoundError: No module named 'tools'`，与本轮改动无关。
- `node frontend/tests/flow-cookie.cjs`：54 个合成用例通过，exit 0。
- `npm run build`：exit 0（仅有既有动态/静态导入与大块体积提示）。
- `node frontend/tests/email-import.cjs`（本地 Vite 8081，隔离 API）：通过，exit 0，确认已到达 `POST /api/emails/import`。
- `node frontend/tests/email-ck.cjs`（本地 Vite 8081，隔离 API）：通过，exit 0；覆盖 CK 列/详情遮罩/复制/取加号/编辑清空/新建/权限/360px。

## 批量导入故障定位

- 复现：对 `docker-local/data/monitor.db` 副本直接调用 `POST /api/emails/import` 对应的 `import_emails`，在 `backend/app/api/emails.py:254` 的 `db.query(EmailAccount).filter_by(email=...)` 抛出 `sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) no such column: email_accounts.ck`，HTTP 500。
- 根因：8080 使用的数据库停留在 Alembic `20261016_0026`，缺少 CK 迁移 `20261114_0027`；当时后端模型已包含 `ck` 列，所有邮箱查询与导入都会失败。与移除 Gmail 字段无关。
- 验证：对同一副本执行 `alembic upgrade head` 后，同一导入返回 `total=1 success=1 failed=0`。随后 `docker-local/data/monitor.db` 已由协调方升级到 `20261114_0027`，导入 POST 实测 200 success=1，合成邮箱已清理。
- 前端导入无需代码修复：`EmailList.importData` 的请求体与 `EmailImportRequest` 完全匹配，回归已覆盖实际 POST。

## 未完成项与环境限制

- `127.0.0.1:8080` 当前由 `com.docker.backend.exe`（PID 52056）占用，只有 `CloseWait/Established` 连接且 HTTP 无响应；`docker ps`/`docker version` 超时，Docker Desktop 管理命令无响应。Vite 自动回退到 8081 完成浏览器回归，未能在 8080 做真实 UI 核对。
- 因 Docker daemon 无响应，未重启容器；未执行 `mypy`、全量覆盖率门禁或真实 8080 UI 截图（本轮任务要求为定向 pytest/compileall、Node 单测、前端构建和浏览器回归）。
- 需协调方/用户重启 Docker Desktop 或 backend 容器后，在 8080 复跑一次邮箱页面与导入。
- 事故记录：验证迁移时，`alembic` 子进程按 `alembic.ini` 默认 URL 将非活动的 `backend/data/monitor.db` 从 `20261002_0019` 增量升级到 `20261114_0027`；仅新增列/表，无数据改写。发现后已停止所有真实数据库操作。
- 本轮未执行独立对抗审查；审查结论与后续轮次由协调方安排。
