# 2026-10-07：全站表格排序、筛选和列设置

## 结果与当前状态

接续 `main` / `8367e01`，用户授权按此前计划实施全站表格控件。28 个现有 Element Plus 表格定义已统一接入，其中 25 个定义在当前路由可达，3 个旧页面同时兼容。代码保留在本地，未提交、推送、发布或部署；版本仍为 1.1.16，公开资产未改。

后续用户确认查看本地 Docker 后，已于本轮重建 `tk-crm-local` 前后端，`127.0.0.1:8080` 含新表格能力；采集健壮性继续实施并更新同一本地环境，最新状态见 [采集实跑交接](2026-10-07-collection-resilience.md)。公开服务器和 Windows 包没有部署变更。

使用说明见 [TABLE_CONTROLS.md](../TABLE_CONTROLS.md)。新增公共组件 `CrmTable.vue`、查询 composable `useTableQuery.js`、纯状态模块 `tableState.js`；新增后端 `table_query_service.py`。没有新依赖或数据库迁移。

表头支持排序、按类型筛选、复合字段选择、条件标签和查询重置。列设置支持显隐、顺序、拖放、上下移动、列宽保存和默认恢复。选择、展开和操作列固定；密码、2FA、图片和纯趋势图仅提供布局配置。运营账号旧列配置按组自动迁移。布局和会话查询按站点、用户和表格分别保存。

普通字段在 SQL 中先查询再分页；监控/运营的部分派生字段以及加密卡密内容按完整权限范围集合处理后分页。昨日视频播放数组按合计数值排序、筛选，页面注明口径。代理配置小表通过连续页加载完整集合；本地报表先查询完整数据再分页。

## 验证

以下均为本次实际执行结果，使用合成凭据、内存测试 fixtures 和隔离 API mock；未读取或修改真实业务数据。

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| compileall | exit 0 | `.orchestration/table-compileall.log` / `.exitcode` |
| 全量 pytest + 80% 覆盖率门禁 | 464 passed，84.23%，exit 0 | `.orchestration/table-pytest-final.log` / `.exitcode` |
| strict mypy | 74 文件、0 错误，exit 0 | `.orchestration/table-mypy.log` / `.exitcode` |
| 前端构建 | exit 0，保留既有 CJS、动态导入及大 bundle 告警 | `.orchestration/table-frontend-build.log` / `.exitcode` |
| 浏览器控件回归 | exit 0，无页面错误，无未模拟 API | `.orchestration/table-browser.log` / `.exitcode`；`frontend/tests/table-controls.cjs` |
| 纯状态回归 | exit 0 | `frontend/tests/table-state.cjs` |
| 原有回归 | 邮箱复制、运营视频浏览器专项；运营刷新与更新恢复 Node 专项均通过 | `frontend/tests/email-copy.cjs`、`op-account-videos.cjs`、`op-account-refresh.cjs`、`update-recovery.cjs` |
| 源码差异检查 | `git diff --check` exit 0 | 保留既有用户截图删除状态及未跟踪产物 |

浏览器覆盖文本、数值、日期、枚举、复合字段、排序请求和清空、防请求循环、列显隐和移动、原生列宽拖动、布局修改后排序箭头、复制、行选择和展开、刷新保存、用户隔离、主要路由、详情及报表查询后分页。截图 `.orchestration/table-email-layout.png` 已目视检查。

首次全量 pytest 的 3 个失败由 Windows PATH 误选失效 WSL bash 引起；显式优先 Git Bash 后全量通过。首次 mypy 的 3 个 `Any` 返回值错误已通过明确返回类型修复。首次浏览器检查发现表头插槽单 VNode 及无条件排序同步引起循环，均已修复并完整重跑。

## 独立审查

使用当前协作代理进行独立只读审查，不恢复或修改旧 Orca provider 会话。后端资源查询和权限、前端元数据契约、公共控件分别交叉审查。

发现并处理：非法筛选类型 500、日期和时区溢出、Date 枚举转换、派生布尔校验、节点凭据白名单、播放数组文本排序、状态值错误、代理小表 100 条截断、页面重置未清表头查询、业务固定列影响重排、列重建后排序状态丢失。最终审查输出：

```text
CODEX SAYS
[P1] none
[P2] none
GATE PASS
APPROVE
```

## 限制与后续

- 复杂派生查询和加密卡密查询会处理完整权限集合，已有 `ponytail:` 性能上限记录；大数据量时可改 SQL 派生计算及索引。
- 浏览器偏好只在当前浏览器保存；未实现跨设备偏好同步。现有手机卡片布局保持可用，新增表头交互适用于表格布局。
- 原监控历史/视频接口的认证与对象权限缺口属于既存问题，本次仅记录，未扩大此次表格功能的改造范围。
- 真实 Windows 干净机、混合 DPI 等设备验收、Docker 更新停机窗口、演示 HTTPS 仍按前次交接处理。
- 团队服务器更新继续由用户网页点击。本次没有调用 apply、SSH 重启、构建或覆盖源码，也没有改公开 Release。
- 后续提交逐文件选择，不使用 `git add .`；保留历史备份、压缩包、staging、截图删除状态，避免把配置、数据库、日志或凭据加入版本。
