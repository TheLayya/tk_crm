# TikTok Monitor

> 更新机制说明：`docs/ONE_CLICK_UPDATES.md`

TikTok 账号监控、终端资产与团队运营管理系统。当前版本覆盖账号采集、设备/节点关联、邮箱与卡密资产、数据总览及可配置登录场景。

> 文档更新日期：2026-10-05

## 技术栈

- 后端：FastAPI、SQLAlchemy、APScheduler
- 前端：Vue 3、Element Plus、ECharts、Vite
- 数据库：SQLite（默认）

## 当前功能

- 数据总览：资产状态、人员与终端关联、金额时间维度、数据质量和未关联资产
- 运营账号：TikTok、YouTube、Instagram、Facebook 账号管理、采集与趋势数据
- 终端资产：手机/电脑、所属成员、节点和运营账号关联；关联账号以头像卡片展示
- 代理节点：节点测试、关联管理、CSV/Excel 批量导入导出；新增节点或导入时要求国家和完整采购信息
- 邮箱资产：批量导入、Gmail 检测、设备/节点及运营账号关联、已注册平台标签
- 卡密项目可设置目标平台：成员领取未注册该平台的闲置邮箱，注册完成自动添加标签并释放；未使用可归还。同一邮箱领取期间不会分配给其他成员，释放后仍可用于其他平台。
- 团队权限：项目、部门、角色、成员和细粒度权限
- 工作项、备忘提醒与卡密生命周期管理
- 登录页：全屏三面屏幕场景，屏幕文字可在“系统设置 → 登录屏幕文字”中自定义

## 本地启动（Windows）

推荐 Python 3.12。先进入项目根目录（即包含 `backend` 和 `frontend` 的目录）。

```bat
cd backend
python -m venv .venv312
.\.venv312\Scripts\python.exe -m pip install -r requirements.txt
```

首次安装时复制 `backend/.env.example` 为 `backend/.env`，填写 JWT 密钥和字段加密密钥；管理员初始密码预设为 `Admin123!`，也可以在首次启动前自行替换。已有 `.env` 时不要覆盖。填写完成后，在 `backend` 目录继续执行：

```bat
.\.venv312\Scripts\python.exe -m alembic upgrade head
.\.venv312\Scripts\python.exe run.py
```

另开终端启动前端：

```bat
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5174
```

前端：<http://localhost:5174/>  
后端文档端口以 `backend/.env` 的 `PORT` 为准，未配置时为 `8000`；本机若配置 `PORT=8801`，则访问 `http://localhost:8801/docs`。

## Windows 桌面版

Windows 用户无需安装 Python、Node.js 或 Docker。可用安装包以 GitHub Release 和根目录 `version.json` 为准；安装器会检测并引导安装 Microsoft Edge WebView2 Runtime，用户数据保存在本地应用数据目录，不随卸载删除。

发布前在项目根目录执行以下单入口审计命令：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File desktop/tests/release-audit.ps1
```

阶段性本地打包按 [Windows 本地打包指引](docs/WINDOWS-LOCAL-PACKAGING.md) 执行；实际推进、测试证据及未验证边界见 [Windows 打包记录](docs/WINDOWS-PACKAGING.md)。

## 发布维护

发布模块由项目内 [tk-crm-release skill](.agents/skills/tk-crm-release/SKILL.md)、[发布工具](tools/release.py) 和既有 `desktop/` 构建验收脚本组成。以后可直接要求“使用 `$tk-crm-release` 发布双端更新”；普通发布同步准备服务器 / Docker 归档和 Windows 安装器，各自验收、公开下载校验通过后才更新统一清单。

技能和脚本随仓库维护。新会话会通过项目 `AGENTS.md` 读取该流程，避免依赖之前的聊天记忆；固定提交来源、真实哈希、迁移、回滚和团队网页点击升级等边界均记录在技能中。

## 登录账号与初始密码

首次启动会创建超级管理员：

- 用户名：`admin`
- 统一初始密码：`Admin123!`

使用当前 `deploy.sh` 新安装，或复制当前 `backend/.env.example` 后首次启动，均使用上述初始密码。**这是公开的初始密码，部署完成后请立即进入“团队管理 → 成员管理”，找到 `admin`，点击“重置密码”，设置自己的强密码；改密前不要向公网开放服务。**

如果首次部署前自定义了 `SUPER_ADMIN_PASSWORD`，则使用自定义密码。升级不会把已有管理员密码改成 `Admin123!`，旧版本部署时设置的密码仍然有效。

如果忘记了部署时填写的密码，可以在服务器安装目录查看配置文件中的密码值（不要把输出发到群聊或提交到 Git）：

```bash
grep '^SUPER_ADMIN_PASSWORD=' backend/.env
```

Windows PowerShell：

```powershell
Select-String '^SUPER_ADMIN_PASSWORD=' .\backend\.env
```

如果配置文件中的密码仍无法登录，说明管理员账号已经创建过，修改 `SUPER_ADMIN_PASSWORD` **不会重置已有管理员密码**；请登录其他超级管理员账号，在“团队管理”中重置密码，或联系维护人员按数据库维护流程处理。不要删除数据库或直接重建管理员，否则可能影响现有数据。

JWT 密钥和管理员密码没有代码内置后备值，缺少配置时后端会拒绝启动。

## 演示环境

- 地址：http://154.201.73.162
- 用户名：`admin`
- 初始密码：`5A5ssBoqMRzjKCn2hTpu8cah`

以上凭据仅用于演示环境，请勿用于生产部署；如果演示环境对外公开，建议定期更换密码。

## 配置

后端配置文件为 `backend/.env`，可先复制 `backend/.env.example`，再替换所有占位值。默认数据库：

```env
DATABASE_URL=sqlite:///./data/monitor.db
```

生成字段加密密钥：`python -c "import secrets; print(secrets.token_hex(32))"`；生成 JWT 密钥：`python -c "import secrets; print(secrets.token_urlsafe(48))"`。将输出分别填入 `FIELD_ENCRYPTION_KEY` 和 `JWT_SECRET`，不要提交真实 `.env`。模板中的加密密钥占位符无效，未替换时后端会拒绝启动。

首次部署前配置 JWT 密钥和字段加密密钥，然后执行 `alembic upgrade head`。已有数据升级时必须保留原字段加密密钥，否则历史密码、2FA、备忘和卡密将无法解密；不要直接更换密钥。

当前数据库迁移版本包含 `20261005_0020`。升级已有数据时只执行迁移，不删除 `backend/data/`。

## Docker 部署

团队服务器和演示服务器建议在 Ubuntu 上使用仓库内的 `deploy.sh` 完成首次部署。脚本会安装或检查 Docker，生成 `backend/.env`，为本机更新代理生成随机令牌，并注册 `tiktok-monitor-updater.service` 作为开机服务：

```bash
git clone https://github.com/TheLayya/tk_crm.git ~/tk-crm-deploy
cd ~/tk-crm-deploy
bash deploy.sh
```

按提示填写 GitHub 仓库地址、访问令牌、安装目录和域名，安装目录可使用默认的 `/opt/tiktok-monitor`。部署后核对容器与更新代理：

```bash
cd /opt/tiktok-monitor
docker compose ps
sudo systemctl status tiktok-monitor-updater --no-pager
```

后续发布新 GitHub Release 并更新根目录 `version.json` 后，管理员直接在网页侧边栏点击版本号 → “检查更新” → “立即更新”。无需逐版本 SSH 执行 `git pull`；更新代理会备份 SQLite、保留 `backend/.env`、`backend/data/` 和管理员密码，迁移或健康检查失败时自动回滚。更新期间服务会短暂重启。

已有服务器升级或不使用网页更新时，可手动执行：

```bash
cd /opt/tiktok-monitor
git pull
docker compose up -d --build
curl http://127.0.0.1:8000/health
docker compose ps
```

手动升级必须保留服务器上的 `backend/.env` 和 `backend/data/`，不要用本地空配置覆盖。没有 Git 工作树的发布归档安装、更新代理 systemd 配置及故障排查见 [一键更新说明](docs/ONE_CLICK_UPDATES.md)。

SQLite 数据库位于 `backend/data/` 持久化目录，代码更新不会删除该目录。

## 开发检查

```bat
cd backend
.\.venv312\Scripts\python.exe -m pytest -q
cd ..\frontend
npm run build
```

后端测试会覆盖权限、迁移、导入、关联、公开设置和安全配置；前端构建使用 Vue 3、Element Plus 和 Vite。

## 数据总览口径

- 资产状态和数据质量是当前用户可见范围内的快照，不受金额日期筛选影响。
- 金额支持全部、今天、本周、本月和自定义日期；采购按采购日期、出售按出售日期统计。
- 缺少业务日期的金额只纳入“全部”；不使用创建时间或修改时间代替业务日期。
- 金额来自当前资产记录，不是历史收支流水或净利润；设备采购、节点续费等费用尚不包含。
- 人员与终端关联、采购渠道、出售客户和未关联资产提供分页。

模块使用说明见 `docs/DATA_OVERVIEW.md`、`docs/EMAIL_MANAGEMENT.md`、`docs/MEMO_MANAGEMENT.md` 和 `docs/CARD_KEY_MANAGEMENT.md`。

## 许可证

MIT License

## 社区与支持

欢迎加入交流群，获取使用帮助、版本更新和问题排查信息：

如果这个项目对你有帮助，欢迎通过微信支持项目维护和持续开发：

![支持作者](docs/community/support.png)

项目交流与作者联系方式：

![作者微信](docs/community/author-wechat.png)


交流群：

![](orca-paste-1790930327639-35d0b30e-4dae-40f0-80e6-928883e156af.png)
