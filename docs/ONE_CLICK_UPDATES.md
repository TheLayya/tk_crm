# 一键更新

系统支持在侧边栏点击版本号检查更新。更新流程由安装目录旁的本地更新代理执行，网页后端只负责鉴权和提交更新请求，不执行任意 shell 命令，也不接触 Docker socket。

更新代理会按以下顺序工作：

1. 下载并校验 HTTPS 发布包的 SHA-256。
2. 停止服务。
3. 备份 SQLite 数据库到 `backups/update-*`。
4. 只替换代码文件，保留 `.env`、`backend/data`、虚拟环境和日志。
5. 执行 `alembic upgrade head`。
6. 启动服务并检查 `/health`。
7. 迁移或健康检查失败时恢复代码和数据库，并重新启动旧版本。

## 首次配置

每台安装只需要配置一次更新代理。生成一个至少 32 位的随机令牌，并把同一个令牌写入后端的 `UPDATE_AGENT_TOKEN`。更新代理只监听本机地址 `127.0.0.1`；Docker 后端通过 `host.docker.internal` 访问宿主机代理。

更新代理的生命周期配置必须使用固定参数数组，不能从网页传入命令。这样可以明确控制停止、迁移和启动动作。

## Docker

在项目根目录运行：

```bash
export UPDATE_AGENT_TOKEN="replace-with-a-long-random-token"
python3 tools/update_agent.py \
  --root "$PWD" \
  --lifecycle "$PWD/tools/lifecycle.docker.json" \
  --token "$UPDATE_AGENT_TOKEN"
```

然后在 `backend/.env` 或 Compose 环境中设置同一个 `UPDATE_AGENT_TOKEN`，重启后端容器。Windows PowerShell 可用：

```powershell
$env:UPDATE_AGENT_TOKEN = "replace-with-a-long-random-token"
docker compose up -d --build
python tools/update_agent.py --root $PWD --lifecycle tools/lifecycle.docker.json --token $env:UPDATE_AGENT_TOKEN
```

## Windows 原生运行

复制 `tools/lifecycle.native.windows.example.json` 为本机配置，替换其中的停止和启动命令。命令必须能可靠地停止并重新启动当前后端、前端服务；如果是两个终端手动运行，建议先改为 NSSM、任务计划程序或统一的服务脚本。

```powershell
$env:UPDATE_AGENT_TOKEN = "replace-with-a-long-random-token"
.\tools\start-update-agent.ps1 `
  -Root (Get-Location).Path `
  -Python ".\backend\.venv312\Scripts\python.exe" `
  -Lifecycle ".\tools\lifecycle.native.windows.json" `
  -Token $env:UPDATE_AGENT_TOKEN
```

原生 Windows 后端使用 `UPDATE_AGENT_URL=http://127.0.0.1:8765`。更新器不会替换 `backend/.env`、`backend/data` 或 `backend/.venv312`。

## 发布新版本

发布包必须是 GitHub Release 资产，不使用分支源码压缩包。发布时同步更新：

- `backend/app/version.py` 的 `APP_VERSION`；
- `frontend/src/components/Layout.vue` 的前端版本；
- `version.json` 的版本、日期、变更记录、发布包地址和真实 SHA-256。

发布包应只包含代码和配置模板，不包含 `.env`、数据库、日志、备份、`node_modules` 或 Python 虚拟环境。用户点击更新前会看到版本号和变更记录。

## 失败处理

每次更新都会在 `backups/update-*` 保留恢复目录。不要在更新过程中删除该目录；若自动回滚后仍需人工处理，可使用其中的数据库备份和代码恢复文件。更新代理的令牌只应保存在本机环境变量或受保护的服务配置中。
