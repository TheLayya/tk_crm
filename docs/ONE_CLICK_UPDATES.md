# 一键更新

服务器版和 Windows 本地版都支持从侧边栏点击版本号检查更新。管理员点击“检查更新”后，如果 GitHub Release 有更高版本，点击“立即更新”即可提交升级；服务会短暂重启，浏览器刷新后继续使用。更新请求只允许已登录且拥有设置编辑权限的管理员发起。

网页后端只负责鉴权、读取发布清单和提交请求。真正执行更新的是安装目录旁的本地更新代理，因此网页不会执行任意 shell 命令，也不会接触 Docker socket。代理会：

1. 从 GitHub Release 下载发布包并校验 HTTPS 和 SHA-256；
2. 停止 Docker 服务；
3. 将 SQLite 数据库备份到 `backups/update-*`；
4. 只替换发布包中的代码，保留 `backend/.env`、`backend/data/`、日志、备份和运行时依赖；
5. 执行数据库迁移，启动服务并检查 `/health`；
6. 迁移或健康检查失败时恢复代码和数据库，并重新启动旧版本。

## 团队服务器和演示服务器（Ubuntu + Docker）

推荐在服务器上使用仓库根目录的 `deploy.sh` 完成首次部署。脚本会安装或检查 Docker，克隆仓库，生成 `backend/.env`，创建随机的 `UPDATE_AGENT_TOKEN`，写入更新代理配置，并注册为开机自动启动的 `tiktok-monitor-updater.service`。首次部署完成后不需要为每个版本手动 SSH，也不需要手动启动更新代理。

在 Ubuntu 服务器执行：

```bash
git clone https://github.com/TheLayya/tk_crm.git ~/tk-crm-deploy
cd ~/tk-crm-deploy
bash deploy.sh
```

按提示填写 GitHub 仓库地址、访问令牌、安装目录和域名，安装目录可使用默认的 `/opt/tiktok-monitor`。私有仓库需要 GitHub Personal Access Token；令牌只用于拉取代码，不要写入仓库或发到群聊。脚本完成后会打印访问地址。

首次部署后立即完成以下检查：

```bash
cd /opt/tiktok-monitor
docker compose ps
sudo systemctl status tiktok-monitor-updater --no-pager
```

两个 Docker 容器应为 `healthy`，更新代理服务应为 `active (running)`。首次登录后请立刻在“团队管理 → 成员管理”中修改公开的初始管理员密码。团队服务器和演示服务器都应保留服务器上的 `backend/.env` 与 `backend/data/`；不要用本地空配置覆盖它们。

以后发布新版本时，维护者发布新的 GitHub Release 并更新仓库根目录的 `version.json`。服务器管理员登录网页，点击侧边栏版本号 → “检查更新” → “立即更新”即可。更新期间页面会短暂不可用，完成后刷新页面；SQLite 数据、管理员密码、团队配置和更新代理令牌会保留。

如果界面显示“本地更新器未初始化”或“更新器不可用”，先通过 SSH 检查：

```bash
sudo systemctl status tiktok-monitor-updater --no-pager
sudo journalctl -u tiktok-monitor-updater -n 100 --no-pager
```

确认服务恢复后再从网页检查更新。只有首次部署、故障排查或恢复备份才需要 SSH；正常版本发布不需要逐版本执行 `git pull` 或 `bash deploy.sh --update`。

## 从发布归档安装 Docker

没有 Git 工作树时也可以使用 GitHub Release 的 `release-vX.Y.Z.tar.gz`。将归档解压到固定安装目录，复制 `backend/.env.example` 为 `backend/.env` 并填写密钥，然后在 `backend/.env` 中配置一个至少 32 个字符的随机更新令牌：

```dotenv
UPDATE_AGENT_URL=http://host.docker.internal:8765
UPDATE_AGENT_TOKEN=在服务器本地生成的随机长令牌
```

归档安装没有 `deploy.sh` 自动生成的 systemd 单元时，按以下命令创建并启用同等服务；`UPDATE_AGENT_TOKEN` 必须与 `backend/.env` 完全一致：

```bash
sudo tee /etc/systemd/system/tiktok-monitor-updater.service >/dev/null <<'UNIT'
[Unit]
Description=Tk CRM Update Agent
Requires=docker.service
After=docker.service network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/tiktok-monitor
EnvironmentFile=/opt/tiktok-monitor/backend/.env
ExecStart=/usr/bin/python3 /opt/tiktok-monitor/tools/update_agent.py --root /opt/tiktok-monitor --lifecycle /opt/tiktok-monitor/tools/lifecycle.docker.json --token ${UPDATE_AGENT_TOKEN} --host 0.0.0.0 --port 8765
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now tiktok-monitor-updater
cd /opt/tiktok-monitor
docker compose up -d --build
```

更新代理端口只应允许 Docker 主机内部访问，并始终使用令牌鉴权；不要把 8765 端口直接暴露给公网。若归档安装目录或 Python 路径不同，应同步修改 systemd 单元中的路径。Compose 默认使用 `host.docker.internal:8765` 访问代理；如需自定义地址，在项目根目录 `.env` 中设置 `UPDATE_AGENT_URL`。

## Windows 本地运行

Windows 原生运行不需要用户编辑 JSON，也不需要手动启动更新代理。继续使用：

```powershell
python start.py
```

`start.py` 会生成本地随机令牌、写入 `backend/.env`、启动更新代理，并记录后端和前端进程。以后从网页点击版本号即可检查和更新；更新器会停止当前进程、迁移数据库并重新启动 `start.py`。更新代理只监听 `127.0.0.1`。

## 发布新版本

维护者使用项目内 [tk-crm-release skill](../.agents/skills/tk-crm-release/SKILL.md) 和 `python tools/release.py --help`。普通版本一起准备服务器 / Docker 源码包与 Windows 安装器；步骤、来源验证、验收和 GitHub 清单顺序分别在技能引用中维护，避免另写临时打包命令。

发布包必须是 GitHub Release 资产，不能使用分支源码压缩包。发布时同步更新：

- `backend/app/version.py` 的 `APP_VERSION`；
- `frontend/src/components/Layout.vue` 的前端版本；
- `version.json` 的版本、日期、变更记录、发布包地址和真实 SHA-256。

发布包只应包含代码和配置模板，不包含 `.env`、数据库、日志、备份、`node_modules` 或 Python 虚拟环境。服务器更新器会拒绝非 GitHub Release 地址、错误校验值和缺少必要文件的归档。

Windows 构建先运行 `desktop/publish.ps1`，再把本次服务器候选清单传给 `desktop/build-installer.ps1 -BaseManifestPath ...`。安装器脚本会生成 Windows 候选清单并运行完整审计；随后还需隔离安装验收和构建前后来源审计。使用发布工具合成双端候选，上传两个资产并校验实际公开下载后，才更新根目录 `version.json`。具体命令和证据格式以技能的 [Windows 引用](../.agents/skills/tk-crm-release/references/windows.md) 为准。

## 失败处理

每次更新都会在安装目录的 `backups/update-*` 保留恢复目录。不要在更新过程中删除该目录；自动回滚后仍需人工处理时，可使用其中的数据库备份和代码恢复文件。更新代理令牌只应保存在服务器本地受保护的环境文件或 systemd 配置中。
