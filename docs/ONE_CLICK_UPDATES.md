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

## Windows 本地运行

Windows 原生运行不需要用户编辑 JSON，也不需要手动启动更新代理。继续使用原来的启动方式：

```powershell
python start.py
```

`start.py` 会自动生成本地随机令牌、写入 `backend/.env`、启动更新代理，并记录后端和前端进程。以后从网页点击版本号即可检查和更新；更新器会自动停止当前进程、迁移数据库并重新启动 `start.py`。

更新代理只监听本机地址 `127.0.0.1`。用户只需要保证 Python、Node.js 和项目依赖可正常启动即可。

## 高级配置

只有不使用 `start.py`、而是通过 NSSM、任务计划程序或自定义服务管理器启动项目时，才需要提供固定生命周期配置。网页不能传入任意 shell 命令。

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

## 发布新版本

发布包必须是 GitHub Release 资产，不使用分支源码压缩包。发布时同步更新：

- `backend/app/version.py` 的 `APP_VERSION`；
- `frontend/src/components/Layout.vue` 的前端版本；
- `version.json` 的版本、日期、变更记录、发布包地址和真实 SHA-256。

发布包应只包含代码和配置模板，不包含 `.env`、数据库、日志、备份、`node_modules` 或 Python 虚拟环境。用户点击更新前会看到版本号和变更记录。

## 失败处理

每次更新都会在 `backups/update-*` 保留恢复目录。不要在更新过程中删除该目录；若自动回滚后仍需人工处理，可使用其中的数据库备份和代码恢复文件。更新代理的令牌只应保存在本机环境变量或受保护的服务配置中。
