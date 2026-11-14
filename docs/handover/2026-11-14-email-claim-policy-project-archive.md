# 邮箱卡密领取开关与项目归档删除

## 规则

- `EmailAccount.allow_card_key_claim` 默认关闭（模型/迁移 `false`，历史行同样写 0），只有 `email:manage` 明确批量开启后才进入领取池；`email:view` 普通用户看不到状态列和批量按钮，接口返回 403。
- 关闭开关时：选中集合中只要有已领取邮箱（`claimed_by` 非空）整批 409 拒绝，不修改任何行；并发领取通过 `claimed_by IS NULL` 条件更新识别，冲突整批回滚。开启不受已领取限制。
- 卡密统计 `email_available` 和领取候选只接受：开关开启、使用状态“闲置”、未领取、目标平台标签未注册。领取条件更新同时校验开关，避免并发关闭后仍被领取。
- 项目删除：无任何领取/归还/消耗/待处理历史、无卡密邮箱使用记录、无售后记录时硬删除项目及未使用卡密/批次；存在任一历史则归档（`archived_at/archived_by`，同时 `is_active=false`），保留全部卡密、批次、使用和售后记录。归档项目默认不出现在列表，`include_archived=true` 可查看，不能再导入、领取或编辑。取消原先“同平台存在领取中邮箱即阻塞”的过宽判断，干净项目不会再被其他项目/邮箱的领取状态误伤。

## 迁移

- `backend/alembic/versions/20261114_0028_email_claim_allowed.py`：`email_accounts.allow_card_key_claim`，`NOT NULL DEFAULT false`，并对已有行写 0。
- `backend/alembic/versions/20261114_0029_card_key_project_archive.py`：`card_key_projects.archived_at/archived_by` 及归档时间索引。
- `backend/alembic/versions/20261114_0030_email_claim_default_off.py`：对已经执行过 0028 的数据库统一 `UPDATE email_accounts SET allow_card_key_claim=0`，避免旧库保留 true 默认。
- 本地运行时库已升级到 `20261114_0030`，278 个历史邮箱全部为 0。

## 验证

- `compileall app`：exit 0。
- 定向 pytest：`tests/test_emails.py tests/test_card_keys.py tests/test_failure_reports.py tests/test_claim_policy_migration.py tests/test_email_ck_migration.py tests/test_permission_registry.py tests/test_table_asset_queries.py`：159 passed，exit 0。
- 迁移测试：升级到 0027、插入历史行、升级 head、`alembic check` 无差异、降级 0027、再升级 head 均通过；另测从 0029 插入 allow=1 的历史邮箱后升级 0030，全部变为 0。
- 运行时核验：项目 2（gemini pro）`email_available=0`，`claim_email` 返回 409；临时副本经管理员批量开启 1 个邮箱后 `email_available=1` 且领取成功。
- 前端 `npm run build`：exit 0。
- 此前全量 pytest 为 583 passed + 1 failed（failure-report 项目删除旧断言）；该断言已改为归档语义并单测通过，全量未再复跑。

## 未完成

- 未新增/执行卡密领取开关与项目归档的浏览器 UI 回归（按协调方要求停止扩展）；默认关闭态已由浏览器构建和响应字段覆盖，但未做 8080 点击回归。
- 未做 8080 实机浏览器核对；8080/8000 当前均已响应，运行时库已到 0029。
- 未更新 `docs/EMAIL_MANAGEMENT.md`、`docs/CARD_KEY_MANAGEMENT.md` 的用户说明。
- 未运行 mypy/覆盖率门禁，未提交或推送。
