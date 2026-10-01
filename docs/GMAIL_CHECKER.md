# Gmail 状态检测复用说明

## Gmail 批量导入

运营账号 → 导入 → Gmail 粘贴，或上传 UTF-8 `.txt` 文件。每行一个，无需表头：

```text
邮箱:邮箱密码:辅助邮箱:2FA:注册时间:国家
demo@gmail.com:password:helper@example.com:BASE32KEY:2026-10-01:美国
other@gmail.com:"password:with:colon":helper@example.com:BASE32KEY:2026-10-01 12:34:56:巴西
empty@gmail.com:password::::
```

上面的第一行是字段说明，实际导入时请删除。空字段保留冒号；密码中有冒号用双引号包住，密码中的双引号写为两个双引号。注册时间支持年份（如 `2021`）、日期（如 `2021-06-15`）或完整时间（如 `2021-06-15 12:34:56`）；只提供年份时系统按该年记录，不要求用户补日期。时间内部冒号不会错列。

也支持四字段：`邮箱----密码----辅助邮箱----2FA`，缺少注册时间和国家无需补齐。只有年份时保存到 `account_created_year`，显示年份而非虚构日期；完整日期保存到 `account_created_at`。

默认平台 Gmail，邮箱转小写；重复邮箱跳过，错误行单独报告。密码与 2FA 加密保存，导入结果不回传原始凭据。注册人记录为当前操作者；使用人可导入后批量分配。导入不会自动检测或发送邮箱给第三方，也不会触发 TikTok 采集。通用 CSV/Excel 模板导入仍然可用。

## 用途

本项目通过第三方 `gmail0918.top` 的公开批量接口探测 Gmail 地址状态。接口只接收邮箱地址，不接收密码、2FA 或恢复邮箱。

检测结果是探测信号，不是 Google 官方认证，也不代表账号当前一定可以登录。

## API

```http
POST https://gmail0918.top/api.php
Content-Type: application/json

{"emails":["example@gmail.com"]}
```

成功示例：

```json
{
  "status": true,
  "message": "Success",
  "data": [
    {"email": "example@gmail.com", "status": "live", "index": 1}
  ]
}
```

## 状态映射

| 原始状态 | 系统状态 | 含义 |
| --- | --- | --- |
| `live`、`success`、`ok` | 正常 | 第三方接口判断为可用 |
| `Disabled`、`disable` | 封禁 | 第三方接口判断为停用 |
| `Verify`、`checkpoint` | 验证 | 第三方接口判断需要验证 |
| `Unregistered`、`not_exist` | 未注册 | 第三方接口判断未注册 |
| 其他、超时、格式错误 | 检测失败 | 不应据此修改业务状态 |

## 调用约束

- 每次最多检测 50 个完整的 `@gmail.com` 地址。
- 应限制并发；本项目同一进程同时只允许一个检测请求。
- 该锁不是跨进程/跨 VPS 的限流；多 worker 或多实例部署需外部统一限流。第三方真实限额没有文档保证。
- 调用前必须向操作者说明邮箱地址会发送给第三方。
- 不要把密码、2FA、恢复邮箱或整行账号凭据发送给该接口。
- 保存检测时间和原始状态，方便复核和更换服务商。
- 不要把检测结果覆盖“正常/自用/封禁/已售”等业务状态。

## 不能推断的内容

检测结果不能证明账号密码正确、当前可登录、归属人身份，或一定触发/未触发 Google 人机验证。`验证` 只能表示第三方接口返回了验证类状态。

## 最小 Python 示例

```python
import httpx

emails = ["example@gmail.com"]
response = httpx.post(
    "https://gmail0918.top/api.php",
    json={"emails": emails},
    timeout=60,
)
response.raise_for_status()
print(response.json())
```

生产环境应增加超时、返回邮箱集合校验、速率限制、审计日志和第三方服务异常处理。不要默认自动重试，避免重复消耗第三方额度。

## 项目内复用

独立命令行测试（不会读取或写入 CRM 数据库）：

```powershell
cd backend
.venv312\Scripts\python.exe check_gmail.py --consent example@gmail.com
```

Linux 下使用 `python check_gmail.py --consent example@gmail.com`。`--consent` 明确确认邮箱地址将发送至第三方。仅检测你有权处理的邮箱。

可复制 `backend/app/services/gmail_checker_service.py` 和 `backend/check_gmail.py` 到其他项目；只依赖 `httpx`。服务函数 `check_gmail_accounts` 返回原始状态，`normalize_status` 做精确映射。未知状态归为检测失败，不猜测含义。

本项目校验完整返回的邮箱集合，忽略返回顺序；缺失、重复、陌生邮箱、非 JSON、非成功响应均报错。此类失败不覆盖已存检测结果，也不更新最近成功检测时间。原结果可能过期，需要结合时间判断。

## CRM 接口

```http
POST /api/op-accounts/gmail-check
Authorization: Bearer <token>
Content-Type: application/json

{"account_ids":[1,2],"consent":true}
```

需要 `op_account:collect` 权限，并校验本人/部门/全部数据范围。只接受 Gmail 平台账号，每次最多 50 个，正在执行其他检测时返回 `429`。

成功返回 `checked` 和 `results`；每条含 `id`、`email`、`status`、`raw_status`、`checked_at`。结果保存到 `gmail_check_status`、`gmail_check_raw_status`、`gmail_checked_at`，同时写入操作轨迹；原管理状态不变。

数据库升级：在 backend 目录执行 `python -m alembic upgrade head`。结果时间在数据库按 UTC 保存，前端沿用现有日期展示工具。

## 已验证范围（2026-10-01）

- 用虚构随机 Gmail 实测返回 `Unregistered`。
- 用户提供的 19 条样本与第三方结果全部一致：3 正常、15 封禁、1 验证，批量请求约 2.8 秒。
- 上述仅证明当时接口连通和样本一致性，不是独立验证的长期准确率。
- 回归测试使用模拟响应，不向第三方上传测试库或运行中数据库的账号。

## 限制与隐私

此接口不是 Google 官方 API，没有已确认的 SLA、公开调用协议或固定限额保证。第三方可能记录邮箱地址、修改响应或停止服务；不要传输密码、2FA、Cookie 或恢复信息。前端确认只表示用户同意当前传输，不代表获得第三方商用 API 许可。长期使用应向站点运营方确认调用授权和数据处理条款。

当前只做手动单个/批量检测，不做周期自动检测、验证码绕过或自动登录。`验证` 不是“已确认触发人机验证码”。
