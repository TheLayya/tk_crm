# 2026-10-10 邮箱详情 2FA 验证码

用户要求邮箱展开区直接显示验证码，并保留复制 2FA 密钥。已完成并更新本地 `tk-crm-local` Docker（`docker-compose.local.yml`），入口 `http://127.0.0.1:8080/emails`。未发布、提交或部署团队服务器；应用版本仍为 1.1.18。

## 实现

- `backend/app/services/totp_service.py` 复用卡密原有标准库 TOTP 算法；卡密 API 契约保持兼容。
- `GET /api/emails/{email_id}/totp` 要求 `email:view` 并沿用邮箱 self/dept/all 对象范围，返回 code、整数倒计时和精确 `valid_for`，`Cache-Control: no-store`。无效密钥返回 422；验证码不存入数据库或列表响应。
- `EmailTotp.vue` 在详情展开时自动取码、倒计时到期换码，支持复制验证码；密钥仍遮罩并可显示或复制。收起、翻页或页面卸载销毁组件，晚响应不能重启计时器；复制时重新检查有效期。无效密钥显示提示并支持重试。

## 验证

- 邮箱与卡密后端专项 78 passed；补充亚秒到期测试后 TOTP 专项 11 passed、68 deselected，exit 0。
- 修改的三个后端源文件 strict mypy 通过；Python 编译及 diff 检查通过。
- 邮箱浏览器回归在 Vite 和实际 Docker 8080 均通过（合成 API 数据），覆盖自动换码、验证码/密钥复制、错误重试、过期及晚响应、收起/卸载和不同宽度。
- 合成截图 `.orchestration/email-totp.png` / `email-totp-docker.png` 已用于目视验证；真实 Orca 8080 页面仅检查控件及六位格式，未输出业务密钥或验证码。
- Docker 镜像构建及 `up -d --no-build --wait` exit 0，前后端 healthy。

## 数据保护

更新前 SQLite 在线备份 `backups/email-totp-local-20261010-204421/monitor.db`。该目录 evidence、before/after、verification JSON 记录真实检查结果；所有表行数和 schema 摘要一致，完整性 ok、迁移 20261007_0024，`docker-local/.env` 摘要一致。数据仍挂载原 `docker-local/data:/app/data`。

保留前序运营账号筛选/导出修改和其他工作区文件；本轮没有整体暂存、清理或恢复用户删除的截图。
