# 2026-10-07：发布模块与双端 1.1.18

用户要求项目内维护更新 skill，覆盖 GitHub 服务器 / Docker 包和 Windows 安装包，并明确要求补齐 Windows 发布。Windows 完整验收发现 1.1.17 表格包装层缺少查询容器，邮箱展开详情宽度越过可见表格。因此修复后统一发布 1.1.18，保留已经公开的 1.1.17 服务器资产。

## 可复用模块

- `.agents/skills/tk-crm-release/SKILL.md`，通过根 `AGENTS.md` 发现。可请求“使用 `$tk-crm-release` 发布双端更新”。按服务器、Windows、GitHub 发布三份引用维护。
- `tools/release.py`：固定 Git blob 的确定性服务器打包与验证、Windows 构建输入审计、双端候选合并、公开下载验证；使用 Python 3.11+ 标准库和现有 updater。
- Windows 输入审计涵盖 backend、frontend、desktop 与构建配置，拒绝未提交或未跟踪输入，兼容 CRLF。合并清单必须核对构建前后报告与固定提交，验收退出码必须是整数 0。
- 复用现有 desktop 发布与验收脚本；不会把旧 Windows 资产标成新版、覆盖公开资产或推送占位清单。
- 真实隔离前向演练通过：旧线上清单保持不变，误用旧清单与失败 smoke 证据被拒绝；7 项发布模块测试通过，技能格式校验通过。

## 修复和源码

来源提交为 `ffacc61a5eccbdb3a9ca36ae17e466668f2d3974`，已推送。后续清单 / 文档提交与此构建来源区分。

- `CrmTable.vue` 建立 inline-size 查询容器，邮箱展开宽度遵循可见表格。
- 安装验收将固定等待改为有界等待实际 owned server health 和 WebView2 ready；保留原安装 AppId 与运行用户应用保护。
- 页面 QA 使用公共 BrowserServer 接口，清理挂起时确认仅本次浏览器 PID 已退出，再关闭管道及连接；业务断言未放宽。该机器浏览器清理可耗时数分钟。
- 在线升级夹具旧版 1.1.15 固定核对 `20261006_0023`，新版才核对当前 head `20261007_0024`。

代码门禁：525 passed / 85.12% 覆盖率；strict mypy 74 文件零错误；前端构建通过；更新 API / 工具 29 passed。未降低门禁。

服务器候选 `release-v1.1.18.tar.gz` 为 4,619,654 字节、328 文件、8 张 PNG，SHA-256 `281c75ef003e29c500e2df3d087803d1b3d0a64f1dffa0969bd9cf6e328bd647`。非 metadata 内容逐字节匹配来源提交，现有 updater 解包校验通过。Windows 构建前审计 344 项输入，摘要 `899e0c286e83581cebd052c66438156edf36151a84c4c2d65760308d07d4bed7`。

## 本地 Docker

实际升级前健康版本为 1.1.16；以现场结果纠正之前上下文的 1.1.17 描述。仅更新 `tk-crm-local`，使用 `docker-compose.local.yml`，构建 exit 0。原 `docker-local/data` bind mount 保持不变。

SQLite 在线备份 `backups/release-1.1.18-local-20261007-220107/monitor.db`，5,423,104 字节，SHA-256 `a7e3aa0dd0a5d0cf7334cfb81e2979976ad4cd520bd195923f76ba041f3d0fd5`。升级后 34 表 schema 和全部行数不变，完整性 ok，current/head `20261007_0024`，前后端 healthy；8080 页面和截图验证版本 1.1.18、表格控件、查询容器，exit 0。

证据在 `.orchestration/release-1.1.18`。团队服务器升级仍由用户网页点击，本轮没有调用团队 apply 或 SSH 部署。

## Windows 与发布状态

双端 Release [TkCRM 1.1.18](https://github.com/TheLayya/tk_crm/releases/tag/v1.1.18) 已公开，标签指向上述 `ffacc61` 来源；不覆盖旧 1.1.17。

- Windows `TkCRM-1.1.18-win-x64-setup.exe`：99,525,919 字节，SHA-256 `dc10de3105b78da321bbeb07110ceaffa578e9b1685c4a103b80793400c76750`。
- fresh publish / complete release-audit 均实际 exit 0，含更新安全 12 项、登录 44 / 卡密 24 / 邮箱 16 组页面断言。截图在 `TkCRM-package-ui-79Qct7/screenshots`，展开邮箱细节已目视核对。
- 隔离 Windows 用户安装 / 卸载实际 exit 0：1,958 个文件逐一匹配，owned health/WebView2 1.1.18、正常退出、卸载保留原数据标记。
- 来源前后 344 输入及摘要一致，compose 核对成功；GitHub 两个资产 digest / size 和重新公开下载 SHA-256 均一致，下载 exit 0。
- 真实在线升级入口实际 exit 0：1.1.15（0023）拒绝错误 SHA 并保持旧文件与数据；正确资产下载安装并启动 1.1.18（0024），WebView2 回执、health、更新历史、原加密字段、配置和 SQLite 完整性通过；卸载后数据库和历史保持不变。该测试调用生产更新器，未模拟旧 UI 点击。
- 首次在线夹具由于隔离用户不能访问用户安装的 Python 而失败；给测试用户临时 read/execute 权限后重跑通过，未修改安装包、降低断言或绕过 AppId 保护。首轮并行安装因其他验收 Server 进程被 guard 拒绝，等待其退出后通过。失败日志保留。
- 统一线上清单从已验证的候选复制，包含两个平台的实际 URL、哈希和来源提交；在资产上传、公开下载与在线升级通过前始终保留 1.1.17。

线上清单提交 `98c4914cf1e5a6de75df558ad10c7614a2513ad8` 已推送。GitHub contents API、固定提交 Raw 和普通 main Raw 均实际返回 1.1.18，两个哈希一致。临时 QA 用户及其 DPAPI 凭据已删除，Python 临时权限恢复原描述符；Windows 保留已加载的合成测试 profile 目录作为证据，没有活动 QA 进程。用户原 Windows 安装未卸载或覆盖。

实际门禁证据为 `desktop/build/publish-1.1.18.exitcode`、`installer-audit-1.1.18.exitcode`，以及 `.orchestration/release-1.1.18` 下 `installer-smoke.exitcode`、`online-update-smoke.exitcode`、`public-download.exitcode`，均为 0。独立发布审查 `[P1] none; [P2] none; GATE PASS; APPROVE`。

物理双屏混合 DPI、缺少 WebView2 的新机器与安装器代码签名不由本次浏览器矩阵证明。
