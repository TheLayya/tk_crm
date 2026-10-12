# 2026-10-12 邮箱批量售出

用户确认本次售卖场景指邮箱。工作区已有未提交的邮箱批量售出实现，本轮核对、修正验收脚本与 strict mypy 类型问题，并将当前代码更新到本地 `tk-crm-local` Docker。入口 `http://127.0.0.1:8080/emails`，应用版本仍为 1.1.18。没有提交、发布或操作团队服务器。

## 使用与实现

- 勾选邮箱后点击“批量售出”，客户和单价只填一次；出售人默认当前账号、日期默认本地今天，显示数量和总金额。每页支持 50/100/200/500 条。
- `POST /api/emails/batch-sale` 沿用邮箱权限和数据范围，整批检查，拒绝已出售、领取中、缺失及不可访问的邮箱；条件更新和行数检查避免并发覆盖或部分保存。
- 保存成功自动复制 `邮箱----密码----辅助邮箱----2FA 密钥`，每行一个邮箱，仅包含交付凭据；交付窗口保留快照，售出邮箱被筛选隐藏后仍可复制。
- 复制失败保留已保存的成交信息及手动复制窗口，重试复制不再提交售卖请求；另有“复制选中资料”入口。
- 本轮 API 修正把更新字典的字符串键转换为映射字段，满足 SQLAlchemy strict mypy 类型要求，行为保持一致。

## 验证

- `backend/.venv312/Scripts/python.exe -m pytest tests/test_emails.py tests/test_sale_validation.py -q`：80 passed，exit 0。
- 类型修正后 `pytest tests/test_emails.py -k batch_sale -q --disable-warnings`：10 passed，58 deselected，exit 0。
- `mypy app/api/emails.py app/schemas/op_account.py`：通过，exit 0。前端构建与相关 diff 检查通过。
- `frontend/tests/email-sale.cjs` 在 Vite 5186 和实际 Docker 8080 均通过；API 使用隔离模拟数据，没有对真实邮箱执行售出。覆盖本地日期、默认售卖人、批量复制、选择快照、重复提交、整批失败、交付回执及复制重试。
- 修正测试中重复切换全选、隐藏下拉选项定位、日期弹窗遮挡等操作问题，保留原有断言。`frontend/tests/email-copy.cjs` 修正时钟暂停竞态后在 8080 通过，保留复制/TOTP 行为验证。
- 截图 `.orchestration/email-sale-docker.png`、`email-sale-docker-receipt.png` 已目视检查。
- 独立只读审查未发现批量售出主流程阻断问题。

## 本地更新与数据

SQLite 在线备份：`backups/email-sale-local-20261012-155740/monitor.db`；目录内保存前后数据库摘要、邮箱内容摘要、环境文件摘要和 verification JSON。完整性 ok、迁移仍为 `20261007_0024`，表结构、全部表行数、邮箱记录及 `docker-local/.env` 校验一致。

`docker compose -p tk-crm-local -f docker-compose.local.yml build` 与 `up -d --no-build --wait --wait-timeout 180` 均 exit 0，前后端 healthy。保留原 `docker-local/data:/app/data` 挂载，运行实例已包含 batch-sale 路由和本轮类型修正。保留工作区其他未提交修改、备份和归档。

## 已知边界

- 售卖成功但 HTTP 响应丢失时，重试会报告已出售；可通过现有“复制选中资料”重新交付。当前没有请求幂等键或交易回执恢复接口。
- 单条旧编辑表单没有版本检查，可能覆盖之后保存的交易；本次没有扩展到通用编辑并发控制。
- 沿用现有规则允许出售“使用中”等非已售、非领取中邮箱，未额外改变业务状态策略。
