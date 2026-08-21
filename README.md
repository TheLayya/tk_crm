# TikTok Monitor

> 🎯 TikTok 账号监控与运营管理系统

一个功能完整的 TikTok 账号数据监控与运营管理系统，支持多账号监控、运营账号管理、团队协作、历史数据追踪、视频监控、代理配置等功能，提供响应式 Web 界面，支持移动端访问。

## ✨ 功能特性

### 监控管理
- 🎯 **账号监控**：自动定时采集 TikTok 账号数据（粉丝数、关注数、点赞数、视频数等）
- 📊 **趋势分析**：历史数据可视化图表，追踪账号增长趋势
- 🎬 **视频监控**：自动采集账号最新视频及互动数据变化
- 🌐 **代理管理**：支持 HTTP/HTTPS/SOCKS5 代理配置，规避 IP 限制
- 📁 **项目分组**：按项目组织监控账号，支持协作成员管理

### 运营账号管理
- � **多平台支持**：TikTok、YouTube、Instagram、Facebook 账号统一管理
- 🔐 **凭证管理**：密码、2FA 密钥、绑定邮箱等敏感信息加密存储
- 💰 **采购/出售记录**：完整的账号交易信息追踪
- 📊 **数据采集**：自动采集账号粉丝数、关注数、点赞数等公开数据
- �📥 **批量导入导出**：支持 CSV 格式批量操作

### 团队管理
- 👥 **成员管理**：用户账号创建、权限分配、状态管理
- 🏢 **部门管理**：树形部门结构，支持多级嵌套
- 🔑 **角色权限**：细粒度权限控制，支持数据范围（全部/部门/本人）
- 📝 **操作日志**：完整的登录日志和操作审计记录

### 系统特性
- 📱 **移动端适配**：iOS 卡片风格移动端界面，底部 Tab Bar 导航
- 🎨 **界面定制**：自定义站点名称和 Logo
- 🔒 **安全认证**：JWT 认证 + 刷新令牌，登录失败锁定保护
- ⚙️ **灵活配置**：自定义监控间隔、并发数、超时时间等参数

## 🛠 技术栈

- **后端**：FastAPI (Python 3.11+) + SQLAlchemy + APScheduler
- **前端**：Vue 3 + Element Plus + ECharts + Vite
- **数据库**：SQLite（默认）
- **部署**：Docker + Docker Compose

## 🚀 快速部署

### 服务器一键部署（推荐）

> 适用于 Ubuntu 20.04+ 服务器，自动安装 Docker 并完成部署。

**首次部署**（需要 GitHub Personal Access Token）：

```bash
read -rsp "请输入 GitHub Token: " T && echo && \
echo "$T" > ~/.github_token && chmod 600 ~/.github_token && \
curl -fsSL -H "Authorization: token $T" \
  https://raw.githubusercontent.com/TheLayya/tk_crm/main/deploy.sh | sed 's/\r//' > /tmp/deploy.sh && \
bash /tmp/deploy.sh
```

**后续部署**（Token 已保存，直接执行）：

```bash
curl -fsSL -H "Authorization: token $(cat ~/.github_token)" \
  https://raw.githubusercontent.com/TheLayya/tk_crm/main/deploy.sh | sed 's/\r//' > /tmp/deploy.sh && \
bash /tmp/deploy.sh
```

部署脚本会自动完成：
- 安装 Docker 和 Docker Compose
- 克隆代码仓库
- 生成随机密钥和环境配置
- 构建并启动服务
- 配置开机自启

### 常用运维命令

在安装目录（默认 `/opt/tiktok-monitor`）下执行：

```bash
# 更新到最新版本
bash deploy.sh --update

# 查看实时日志
bash deploy.sh --logs

# 停止服务
bash deploy.sh --stop

# 重启服务
bash deploy.sh --restart

# 查看服务状态
bash deploy.sh --status
```

### 本地开发

```bash
# 克隆项目
git clone https://github.com/TheLayya/tk_crm.git
cd tk_crm

# 后端
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
python run.py

# 前端（新终端）
cd frontend
npm install
cp .env.example .env
npm run dev
```

访问地址：
- **前端界面**：http://localhost:5173
- **后端 API**：http://localhost:8000
- **API 文档**：http://localhost:8000/docs

## ⚙️ 配置说明

### 环境变量

**后端配置** (`backend/.env`)：

```bash
DATABASE_URL=sqlite:///./data/monitor.db
SECRET_KEY=your-secret-key          # JWT 签名密钥（部署脚本自动生成）
FIELD_ENCRYPTION_KEY=your-key       # 字段加密密钥（部署脚本自动生成）
SUPER_ADMIN_PASSWORD=admin123456    # 超级管理员初始密码
HOST=0.0.0.0
PORT=8000
```

**前端配置** (`frontend/.env`)：

```bash
VITE_API_BASE_URL=http://localhost:8000
```

### Docker 端口配置

修改 `docker-compose.yml` 中的端口映射：

```yaml
services:
  frontend:
    ports:
      - "80:80"     # 前端端口
  backend:
    ports:
      - "8000:8000" # 后端端口
```

## 📖 使用指南

### 初始登录

- **账号**：`admin`
- **密码**：部署时设置的管理员密码（默认 `admin123456`）

### 1. 系统设置

首次使用建议先配置：

- **监控间隔**：新建账号的默认检查频率（秒，默认 3600）
- **最大并发数**：同时执行的检查任务数量上限
- **请求超时**：单次请求超时时间（秒）
- **默认视频数**：每次检查获取的最新视频数量
- **站点名称/Logo**：自定义界面品牌

### 2. 团队管理

建议按以下顺序配置：

1. **部门管理**：创建组织架构
2. **角色管理**：定义权限角色（全部数据/部门数据/本人数据）
3. **成员管理**：创建用户账号并分配角色

### 3. 监控管理

- **项目管理**：创建项目分组，可设置协作成员
- **账号列表**：添加 TikTok 账号，配置监控参数
- **代理管理**：配置代理池，支持批量导入

### 4. 运营账号管理

管理多平台运营账号（TikTok/YouTube/Instagram/Facebook）：

- 记录账号凭证（密码、2FA、绑定邮箱等）
- 追踪采购和出售信息
- 自动采集账号公开数据
- 支持 CSV 批量导入导出

### 5. 移动端访问

直接用手机浏览器访问系统地址，自动切换为移动端界面：
- 底部 Tab Bar 导航（监控/运营/团队/设置）
- iOS 卡片风格列表
- 团队页面内置子导航（成员/部门/角色/日志）

## 🔧 开发说明

### 项目结构

```
tk_crm/
├── backend/                 # 后端服务
│   ├── app/
│   │   ├── api/            # API 路由
│   │   ├── core/           # 核心配置（数据库、安全、调度器）
│   │   ├── middleware/     # 中间件（限流、操作日志）
│   │   ├── models/         # SQLAlchemy 数据模型
│   │   ├── schemas/        # Pydantic 请求/响应模型
│   │   └── services/       # 业务逻辑
│   ├── alembic/            # 数据库迁移
│   └── requirements.txt
├── frontend/               # 前端应用
│   ├── src/
│   │   ├── api/           # API 调用封装
│   │   ├── components/    # 公共组件（Layout、Breadcrumb、MobileTabBar 等）
│   │   ├── directives/    # 自定义指令（v-permission）
│   │   ├── router/        # 路由配置
│   │   ├── stores/        # Pinia 状态管理
│   │   ├── styles/        # 全局样式（响应式、设计令牌）
│   │   └── views/         # 页面视图
│   └── vite.config.js
├── data/                   # 数据目录（SQLite 数据库）
├── docker-compose.yml
└── deploy.sh              # 一键部署脚本
```

### 数据库迁移

```bash
cd backend

# 创建新迁移
alembic revision --autogenerate -m "description"

# 执行迁移
alembic upgrade head

# 回滚一步
alembic downgrade -1
```

### API 文档

启动后端后访问 http://localhost:8000/docs（Swagger UI）。

## 🐛 故障排查

### 服务无法启动

```bash
# 查看容器状态和日志
docker compose ps
docker compose logs backend
docker compose logs frontend
```

### 数据库迁移失败

```bash
docker compose exec backend alembic upgrade head
```

### 前端无法访问后端 API

1. 确认后端服务正常：`docker compose logs backend`
2. 检查 nginx 是否正确代理 `/api` 路径
3. 确认防火墙开放了对应端口

### 账号检查失败

- **TikTok 限流**：降低并发数或增加监控间隔
- **代理失效**：在代理管理中测试并更换代理
- **账号不存在**：确认用户名拼写正确

### 调度器 `missed` 警告

日志中出现 `Run time of job was missed` 属于正常现象，表示上一次任务执行时间超过了调度间隔（5分钟），不影响实际监控功能。

## 🔒 安全建议

1. **修改默认密码**：首次登录后立即修改管理员密码
2. **配置防火墙**：限制服务器访问来源 IP
3. **使用 HTTPS**：生产环境配置 SSL 证书（推荐 Cloudflare 代理）
4. **定期备份**：备份 `data/` 目录下的数据库文件
5. **保护 Token**：`~/.github_token` 文件权限已设为 600，请勿泄露

## 📄 许可证

MIT License

## 📮 联系方式

- 提交 Issue：[GitHub Issues](https://github.com/TheLayya/tk_crm/issues)
- 邮箱：673105710@qq.com
- 微信：lly450200

---

⭐ 如果这个项目对你有帮助，请给个 Star！

## ���� Windows ����˵��

���ʹ�� SQLite���Ƽ� Python 3.12��

``bat
cd /d F:\����������\crm\tk_crm\backend
.\.venv312\Scripts\python.exe -m alembic upgrade head
.\.venv312\Scripts\python.exe run.py
`` 

ǰ�ˣ�

``bat
cd /d F:\����������\crm\tk_crm\frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5174
`` 

���� http://localhost:5174/��Ĭ���˺� admin������ admin123456��

## ����˵��

��������ʹ�� Docker Compose �� Nginx�����Ĭ�ϼ��� 8000��ǰ�˹�������λ�� frontend/dist������ǰִ�� alembic upgrade head�����޸���Կ�����Ա���롣

## �����޸�

- ��Ӫ�˺�֧�ֲ�����Ŀ������
- ͬһƽ̨��ֹ�ظ�������ͬ�˺š�
- sellers �ֶ��Զ��� JSON �ַ����� API �б���ת����
