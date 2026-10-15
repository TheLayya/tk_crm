# 2026-10-15 邮箱混合格式导入

用户反馈邮箱管理缺少“账号/密码/辅助邮箱/国家”格式，并给出混合五项、空列、第三项为 2FA、第三四项重复密钥及同批重复账号的样例。用户确认第四项始终为 2FA。使用同形合成数据回归，真实样例中的登录资料没有写入源码、测试或服务器。

## 实现

- 复用 `parse_email_import_line`，自动按行解析三、四、五、六项；连续 `----` 保留空字段，五项明确为邮箱/密码/辅助邮箱或错列密钥/2FA/国家。
- 自动四项遇到明确国家代码或常见名称时保存到国家；新增 `country_4` 和 `country_5` 手动格式，显式 `credentials_3`、`credentials_4`、`full_6` 保留原字段含义。第四项为短字符串也保留为 2FA，不因验证码生成失败丢弃。
- 自动三项如果第三项是邮箱，保存为辅助邮箱；其他内容按原有逻辑保留为 2FA。自动四/五项的第三项通过长度、Base32 字符集及解码检查后才识别为错列密钥：第四项空时补齐、归一化后相同时去重、不同则本行失败并显示固定说明。六项旧解析保持原样。
- 分隔符增加英文逗号、中文逗号和 Tab；继续使用 csv.reader 处理单字符分隔及引号，密码按原文保留。既有冒号完整时间兼容。
- 错误原因使用固定白名单说明，日期异常不回显原字段；已有账号/同批重复仍跳过，其他行独立保存。
- 导入框新增混合格式说明与选项，文档同步；没有新增依赖或数据库迁移。

## 验证

- `pytest tests/test_emails.py tests/test_gmail_check_api.py tests/test_op_account_import_export.py -q --disable-warnings`：99 passed，exit 0。
- `mypy app/api/emails.py app/services/op_account_service.py app/schemas/op_account.py --strict`：3 文件零错误，exit 0；compileall 通过。
- `npm.cmd run build`：exit 0，日志 `.orchestration/email-import-build.log`；既有 bundle 警告保留。
- `node frontend/tests/email-import.cjs`：exit 0，API 全部模拟，验证混合原文提交、空列/密码保留、新格式和分隔符值、成功/重复结果、权限及运行错误。截图 `.orchestration/email-import-mixed.png` 已检查。
- 独立只读审查 CODEX SAYS `[P1] none; [P2] none; GATE PASS; APPROVE`。

## 当前范围

本轮仅修改源码、测试和说明，没有提交、发布或重建本地/远端运行实例。版本仍为 1.1.19，演示站当前运行已发布版本。工作区原有查询、样式、页面修改和备份均保留；`op_account_service.py` 与 `EmailList.vue` 同时含其他未提交改动，后续发布需要按 hunk 选择本轮修改。
