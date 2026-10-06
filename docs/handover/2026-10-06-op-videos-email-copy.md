# 2026-10-06：运营账号视频采集、邮箱复制与更新提示

## 当前状态

在 `main` / `5648200` 基线上继续。用户本轮报告：运营账号不自动采集视频；邮箱管理复制邮箱、密码等资料难用。两项生产代码已在本地修复，另补完上轮未完成的更新提示逻辑。以下验证和暂停状态记录于发布前；用户随后明确要求 commit、push、发布，发布续接见文末。服务器本轮没有部署。

保留原有未跟踪发布包、desktop、backups 和已删除历史截图。不要 `git add .`。新的迁移和测试文件要逐项包含。

团队服务器继续由用户在网页点击更新；没有调用 `/api/updates/apply`，没有重启服务器或覆盖服务器源码。

## 业务修复

- 运营账号旧 collector 只调用 `fetch_user_info`；视频摘要来自同名 MonitorAccount 且受监控项目权限限制，独立运营账号无法取得视频。
- 新增 `op_account_videos`，按 `(account_id, video_id)` 唯一并随运营账号删除级联；复用现有视频保存、查询和北京时间昨日摘要逻辑，监控视频与统计快照保持原路径。
- 新增 `op_accounts.video_collected_at`，成功空结果与未采集区分；采集资料后抓取视频，失败保留有效资料、旧视频和旧视频时间，rollback 后记录 `VIDEO_COLLECTION_FAILED:`。
- 旧账号缺视频时间时在下次定时任务补采；失败重试仍遵循系统采集间隔，已售/封禁仍不自动采集。
- 视频接口 `/api/op-accounts/{id}/videos` 验证 op_account:view 和 self/dept/all；账号自己的视频优先，未取得自己视频时仍允许原有授权监控回退。
- 桌面展开和手机详情复用 InlineAccountVideos 展示独立运营视频，昨日更新不再要求关联监控。
- 邮箱列表新增复制邮箱、复制密码、复制资料；展开区新增辅助邮箱、2FA 单项复制，密码/2FA 默认遮罩。复用现有 copyText 的 Clipboard API / HTTP fallback，没有增加依赖。
- 历史迁移测试改用历史 schema 的 SQL 插入，避免当前 ORM 的新列污染旧库测试；新视频测试同时在前后清理隔离业务账号。

新迁移：`backend/alembic/versions/20261006_0021_add_op_account_videos.py`。运行本地或未来发布版本前需要执行 `alembic upgrade head`，不能只换前端。

## 更新提示补丁

单次 setTimeout 轮询替代 async setInterval；记录目标版本、开始时间和是否确认接受，刷新续接，卸载清理。提交响应丢失不重发 POST，旧失败记录不确认本次任务。完成须匹配目标版本、后端版本及可加载前端 HTML。

10 分钟超时保留任务锁、停止自动轮询，提供只读查询；查询失败也不解锁。明确 400/401/403/404/422 提交拒绝解锁；409/500/501 等不确定响应保留锁。更新窗口内网络和 502/503/504 错误静默，窗口外正常显示。

**尚未改变 Docker 更新生命周期：停机后构建镜像的窗口仍存在。** 本轮仅处理前端提示、恢复和防重复提交。此前提出的镜像预构建/维护入口需要独立实现与回滚验收。

## 只读服务器复核

本轮公开 HTTP 从本机请求，两站均 200。SSH 只读取 health、更新状态、监听及 systemd active，没有读取业务数据库。

| 服务器 | 本轮实际版本 | 更新状态 | 监听与可用入口 |
| --- | --- | --- | --- |
| 团队 156.233.227.231 | 1.1.12 | completed / latest_version 1.1.12 | 80、8000；HTTP 200 |
| 演示 154.201.73.162 | 1.1.12 | completed / latest_version 1.1.12 | 80、8000；HTTP 200，HTTPS 连接失败，无 443 |

演示版本已不同于旧交接的 1.1.11，以本轮证据为准。README 演示链接本来就是 HTTP。HTTPS 尚未配置，本轮未更改证书/代理。

## 审查记录

采用当前运行时 Codex 协作子代理直接只读审查，未恢复旧 Orca provider session，没有向旧 pane 发命令；读取历史 transcript 仅为核对已有更新授权/约束。未另起 Orca CLI/orchestration worker。实现代理分别负责视频、邮箱、更新前端，审查方不修改被审代码。

CODEX SAYS — 视频方案预审：
[P1] none.
[P2] 正常空列表与平台限制须区分；持久化异常须 rollback；自己视频与监控回退必须保持归属、权限及 freshness；source watcher 和迁移验证须覆盖。
GATE PASS; APPROVE。上述 P2 本轮全部处理。

CODEX SAYS — 邮箱方案及最终视频 diff：
[P1] none; [P2] none; GATE PASS; APPROVE。

CODEX SAYS — 更新第一次 diff 复审：
[P1] 超时清任务锁会允许仍运行任务重复提交；提交前 confirmed=true 会将响应丢失误判为上次相同版本失败。
[P2] none; GATE FAIL。
两项已修复，并修正非终态读取错误、409/5xx 不确定提交错误和手动查询并发。

CODEX SAYS — 最终更新 diff 与历史迁移测试修正复审：
[P1] none; [P2] none; GATE PASS; APPROVE。

## 验证与退出码

| 检查 | 结果 |
| --- | --- |
| 后端 pip install pytest pytest-cov mypy | exit 0，已有依赖 |
| 后端 compileall app | exit 0 |
| 首次全量 pytest | exit 1，backend cwd 未设置仓库根 PYTHONPATH，tools import 失败 |
| 环境修正后的第一次全量 | exit 1，366 passed / 6 failed，覆盖率 69.40%；3 项误选 WSL Bash、3 项测试隔离/旧迁移模型问题 |
| 修复并使用 Git Bash PATH 的全量 | exit 1，**372 passed**，覆盖率 **69.51% < 80%** |
| 严格 mypy（规定序列） | NOT RUN，前一覆盖率门禁失败即停 |
| 最终前端构建（规定序列） | NOT RUN，同上 |
| 实现代理早期独立 frontend npm.cmd run build | exit 0，既有 CJS、动态导入、大 bundle 警告；不代表最终规定序列通过 |
| 视频、调度、昨日摘要、关联摘要、新库迁移专项 | 21 passed，exit 0 |
| 迁移/隔离修正专项 | 19 passed，exit 0 |
| node frontend/tests/update-recovery.cjs | exit 0，目标匹配、断连/网关、旧失败、响应丢失、防重复、超时锁、手动查询、恢复、清理均通过 |
| 邮箱 Playwright | 功能断言全部通过；浏览器关闭挂起后中止 exit 1，不能记完整通过 |
| 运营视频 Playwright | 桌面独立/监控回退/手机断言全部通过；关闭限制见下 |
| git diff --check | exit 0，仅 LF/CRLF 提示 |

浏览器工具在本机 bundled headless-shell、Chrome、Edge 的最小 launch/close 也复现关闭挂起。浏览器功能断言与测试进程最终退出必须分开记录。邮箱脚本不伪造 exit 0，截图 `.orchestration/2026-10-06/email-copy.png` 仅为 mock 验收证据。新测试位于 `frontend/tests/`，Playwright 从既有外部开发安装加载。

完整覆盖日志：`.orchestration-full-validation.log`（被 .gitignore 排除）。不要为过 80% 临时降低门禁，也不要把本轮说成已上线。

## 剩余事项

全仓覆盖率及最终发布门禁仍未通过；新包待验证后发布，团队升级由用户点击。Docker 更新停机窗口、演示 HTTPS、Windows 发行包仍待后续处理。原始历史 transcript 未被修改或删除。

## 发布续接

用户在已知上述门禁限制后明确要求 commit、push、发布。本轮据此继续发布 1.1.13，并单独执行当前前端构建与严格类型检查，结果不改写上一阶段的 NOT RUN 记录，也不将覆盖率门禁记为通过。团队服务器仍由用户点击升级。

发布先提交并推送已审计代码，再以该提交构建源码包。包内 `version.json` 仅保存版本、日期和变更元数据，不包含自引用哈希；线上根 `version.json` 在资产公开并验证真实 SHA-256 后才更新。源码提交为 `a4394bb`，候选包 SHA-256 为 `57a09b8ba85e1613cc5d668a5b3e05f661e74065f1494137aef7aa9fb0f6d544`。详细发布结果记录在 `2026-10-06-release-1.1.13.md`。
