# 2026-10-07：采集健壮性和本地 Docker 实跑

## 完成状态

用户要求采集健壮并明确要求真实组件代码跑通。本轮已实施、验证并重建本地 `tk-crm-local` 前后端，入口为 `http://127.0.0.1:8080`。没有提交、推送、发布或修改团队/演示服务器；公开版本仍为 1.1.16。

## 实现

- `scraper_service.py`：网络/代理错误、429、502/503/504 最多三次请求，1/2 秒指数等待与抖动，Retry-After 等待上限 10 秒；明确不存在、验证页及无有效资料不盲目重试。SOCKS 协议错误明确分类；凭据 URL 编码和错误日志脱敏。资料接口和主页回退的临时故障分类不丢失。视频初始化响应、非 JSON、受限/空响应明确分类；无 msToken 仅诊断；后续页故障使用 partial 标记。
- `op_collector_service.py`：同账号的并发请求共享跨线程 Future，取消/异常释放所有权；每账号选择代理，资料和视频共用最多两个不同代理，不自动直连绕过配置。系统超时设置生效。资料成功视频失败保留资料和上次完整视频；部分视频结果不推进完整采集时间。
- 运营账号新增 `last_attempt_at`、`next_attempt_at`、`collect_retry_count`；临时故障按 5/15/30 分钟短重试，预算耗尽回到正常周期，手动采集开启新周期。身份修改清理旧调度，旧请求不写新身份。迁移 `20261007_0024` 仅新增三列。
- `op_account_service.py` 与 `main.py`：按每账号调度，启动前结算本进程之前的 running 任务和已有尝试的 pending 账号；新建且未尝试账号不误标失败。后台异常先 rollback 再记任务失败。
- `monitor_service.py`：每个并发账号独立 Session；资料/历史先提交，视频写入使用逐条保存点；最多两个随机池代理，显式绑定代理保持不变。账号锁覆盖首次、手动和定时检查；身份在请求返回后核对，旧结果丢弃。视频失败保留已采资料，摘要返回 `partial`。
- 单独视频入口共用监控锁、设置超时和数量；缺少 SEC_UID 返回 422，未完整采集返回 502；不覆盖另一个监控账号的视频记录。
- 页面在监控视频阶段失败时显示“视频未完成”，运营失败提示包含下次尝试时间与短重试次数。

## 验证与独立审查

| 检查 | 实际结果 |
| --- | --- |
| 全量 pytest + 80% 覆盖率门禁 | 525 passed，84.74%，exit 0 |
| strict mypy | 74 文件零错误，exit 0 |
| 采集组件专题 | request MockTransport、跨线程重复任务、取消、最终提交故障、代理切换预算、短重试持久化、重启恢复、Session/保存点、身份变更等均执行通过 |
| Docker 构建 | 前后端镜像构建 exit 0，前端 Vite 通过 |
| Docker 启动 | 两容器 healthy，迁移 0024 完成 |
| 数据检查 | 备份完整性 ok，升级后 integrity ok、FK 问题 0、原表记录数未减少 |
| Docker 浏览器回归 | `table-controls.cjs` exit 0，无页面错误；原表格能力保留 |
| Node 回归 | 运营采集刷新及表格状态测试 exit 0 |
| 差异检查 | `git diff --check` exit 0 |

本地证据：`.orchestration/collector-pytest-final.log` / `.exitcode`、`collector-mypy.log` / `.exitcode`、`collector-browser.log` / `.exitcode`。数据库备份：`backups/collection-resilience-20261007-203056/monitor.db`。

首轮完整 pytest 有一个日志捕获夹具失败：Alembic 测试 `fileConfig` 禁用了已创建的 logger；显式恢复测试 logger 后整套重跑通过，没有移除日志脱敏断言。预审和实现后的独立只读交叉审查均完成，发现的异常广播成功、无默认 interval、分类丢失、重复排序/事务风险等已处理。最终：

```text
CODEX SAYS
[P1] none
[P2] none
GATE PASS
APPROVE
```

## 真实网络运行

本轮在更新后的本地 Docker 使用生产 `collect_account` 对两个本地失败账号执行网络采集；未输出账号、节点密码或令牌。

- 样本 1：视频正常取得 20 条，但资料返回缺少可解析数据；保持失败，旧资料保留，约 6.2 秒。
- 样本 2：资料和 20 条视频完整成功，约 6.09 秒。
- 另通过生产 HTTP `/api/op-accounts/collect` 发起单账号任务，再轮询 `/tasks/{id}`：status completed、total/completed/success=1、failed=0，exit 0。这验证网页点击采用的 API/后台/状态闭环，而非只调用测试替身。

证据：`.orchestration/collector-live.log` / `.exitcode`、`collector-http-live.log` / `.exitcode`。检查时本地 TikTok 账号状态为 41 success、6 failed；旧运行任务结算后为 29 completed、2 failed。这是即时状态，不等于长期成功率。

## 后续边界

有限重试和代理切换可处理临时链路错误，仍不能保证 TikTok 每次提供可用 Web 数据。验证页、限制、私密/删除等应保留明确状态，不能自动改账号业务状态或伪造成功。生产日志现在记录可分类错误，不打印代理凭据。

进程内所有权针对当前单 uvicorn worker；扩为多个 worker 前需数据库租约。身份检查到提交之间的极短编辑窗口尚不使用条件事务锁。监控视频仍全局 video_id 唯一，已加不覆盖他人记录保护，未来如需同视频跨项目独立记录再迁移为复合唯一键。

公开服务器和 Windows 安装包未更新。本地 Docker 源码已经包含表格和采集改动，后续发布应逐文件审查并制备完整包和真实哈希；团队升级仍由用户在网页点击。
