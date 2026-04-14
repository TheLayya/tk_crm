# TikTok Monitor Standalone

> 🎯 TikTok 账号监控系统 - 独立部署版本

一个功能完整的 TikTok 账号数据监控系统，支持多账号管理、历史数据追踪、视频监控、代理配置等功能。

## ✨ 功能特性

- 🎯 **账号监控**：自动定时采集 TikTok 账号数据（粉丝数、关注数、点赞数、视频数等）
- 📊 **趋势分析**：历史数据可视化图表，追踪账号增长趋势
- 🎬 **视频监控**：自动采集账号最新视频及互动数据变化
- 🌐 **代理管理**：支持 HTTP/HTTPS/SOCKS5 代理配置，规避 IP 限制
- 📁 **项目分组**：按项目组织监控账号，支持批量操作
- 📥 **导入导出**：支持 CSV/Excel 格式批量导入导出账号列表
- ⚙️ **灵活配置**：自定义监控间隔、并发数、超时时间等参数
- 🎨 **界面定制**：支持自定义站点名称和 Logo

## 🛠 技术栈

- **后端**：FastAPI (Python 3.11+)
- **前端**：Vue 3 + Element Plus + ECharts
- **数据库**：SQLite（默认）/ PostgreSQL（可选）
- **部署**：Docker + Docker Compose

## 🚀 快速启动

### 方式一：Docker Compose（推荐）

#### 前置要求

- Docker 20.10+
- Docker Compose 2.0+

#### 一键部署

**Linux/Mac：**

```bash
# 克隆项目
git clone https://github.com/TheLayya/tiktok-monitor.git
cd tiktok-monitor

# 使用部署脚本（自动构建、启动并检查服务状态）
chmod +x deploy.sh
./deploy.sh
```

**Windows：**

```powershell
# 克隆项目
git clone https://github.com/TheLayya/tiktok-monitor.git
cd tiktok-monitor

# 启动服务
docker-compose up -d --build

# 查看日志
docker-compose logs -f
```

或者手动执行（所有平台通用）：

```bash
# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f
```

服务启动后访问：
- **前端界面**：http://localhost
- **后端 API**：http://localhost:8000
- **API 文档**：http://localhost:8000/docs

#### 停止服务

```bash
docker-compose down

# 停止并删除数据
docker-compose down -v
```

### 方式二：本地开发

#### 一键启动（推荐）

```bash
cd tiktok-monitor

# 首次运行：创建并激活后端虚拟环境
cd backend
python -m venv venv

# Windows
venv\Scripts\activate
# Linux/Mac
# source venv/bin/activate

# 安装后端依赖
pip install -r requirements.txt

# 初始化数据库（首次运行必须执行）
alembic upgrade head

cd ..

# 一键启动前后端（需在虚拟环境激活状态下运行）
python start.py
```

脚本会自动：
- 检测端口占用，自动切换可用端口
- 检查并安装前端依赖
- 同时启动前端和后端
- 启动完成后自动打开浏览器
- `Ctrl+C` 同时停止所有服务

#### 手动分开启动

```bash
cd tiktok-monitor/backend

# 创建虚拟环境
python -m venv venv

# Windows 激活虚拟环境
venv\Scripts\activate
# Linux/Mac 激活虚拟环境
# source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 复制环境变量配置
copy .env.example .env  # Windows
# cp .env.example .env  # Linux/Mac

# 初始化数据库
alembic upgrade head

# 启动服务
python run.py
```

后端服务运行在 http://localhost:8000

#### 前端启动

```bash
cd tiktok-monitor/frontend

# 安装依赖
npm install

# 复制环境变量配置
copy .env.example .env  # Windows
# cp .env.example .env  # Linux/Mac

# 启动开发服务器
npm run dev
```

前端服务运行在 http://localhost:5173

### 数据持久化

数据存储在 `./data` 目录下，包含 SQLite 数据库文件。

**备份数据**：
```bash
# Windows 备份数据库
xcopy /E /I data data_backup_%date:~0,4%%date:~5,2%%date:~8,2%

# Linux/Mac 备份数据库
# cp -r ./data ./data_backup_$(date +%Y%m%d)
# tar -czf data_backup_$(date +%Y%m%d).tar.gz ./data
```

## ⚙️ 配置说明

### 环境变量

**后端配置** (`backend/.env`)：

```bash
# 数据库连接
DATABASE_URL=sqlite:///./data/monitor.db

# 服务配置
HOST=0.0.0.0
PORT=8000
DEBUG=true
```

**前端配置** (`frontend/.env`)：

```bash
# API 地址（开发环境）
VITE_API_BASE_URL=http://localhost:8000
```

### Docker 配置

在 `docker-compose.yml` 中修改环境变量：

```yaml
services:
  backend:
    environment:
      - DATABASE_URL=sqlite:////app/data/monitor.db
      - HOST=0.0.0.0
      - PORT=8000
    ports:
      - "8000:8000"  # 修改端口映射
    volumes:
      - ./data:/app/data

  frontend:
    ports:
      - "80:80"  # 修改前端端口
```

### 切换到 PostgreSQL

如需使用 PostgreSQL 替代 SQLite：

1. 修改 `docker-compose.yml`：

```yaml
version: '3.8'

services:
  db:
    image: postgres:15-alpine
    container_name: tiktok-monitor-db
    environment:
      - POSTGRES_DB=tiktok_monitor
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=your_secure_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped

  backend:
    environment:
      - DATABASE_URL=postgresql://postgres:your_secure_password@db:5432/tiktok_monitor
    depends_on:
      - db

volumes:
  postgres_data:
```

2. 重新部署：

```bash
docker-compose down
docker-compose up -d
```

## 📖 使用指南

### 1. 系统设置

首次使用建议先配置系统参数：

- **监控调度设置**：
  - 默认监控间隔：新建账号的默认检查频率（分钟）
  - 最大并发检查数：同时执行的检查任务数量上限
  - 请求超时时间：单次请求的超时时间（秒）
  - 默认监控视频数：每次检查时获取的最新视频数量

- **界面设置**：
  - 网站名称：自定义站点名称
  - 网站 Logo：上传自定义 Logo（建议尺寸 200x50px）

### 2. 代理管理

配置代理以避免 IP 限制：

- **支持格式**：
  - 单行格式：`ip:port` 或 `ip:port:username:password`
  - 批量导入：支持多行文本批量添加

- **代理类型**：HTTP、HTTPS、SOCKS5

- **批量操作**：
  - 批量启用/禁用代理
  - 批量删除代理
  - 代理测试

### 3. 项目管理

创建项目来组织监控账号：

```
项目示例：
- 竞品监控
- KOL 追踪
- 品牌账号
```

### 4. 添加账号

在项目下添加需要监控的 TikTok 账号：

- **单个添加**：填写账号用户名和配置参数
- **批量导入**：
  - 支持 CSV/Excel 文件导入
  - 支持多行文本批量添加
  - 格式：每行一个用户名

- **账号配置**：
  - 用户名（必填）：TikTok 账号用户名
  - 昵称：账号昵称（可选）
  - 监控间隔：自定义检查频率
  - 代理设置：选择代理或随机代理
  - 视频监控：是否监控视频数据

### 5. 监控管理

- **立即检查**：手动触发单个账号检查
- **批量检查**：批量触发多个账号检查
- **批量操作**：
  - 批量启用/禁用账号
  - 批量删除账号
  - 批量移动到其他项目

### 6. 数据查看

- **账号列表**：
  - 查看所有监控账号的当前数据
  - 显示粉丝数、关注数、点赞数、视频数
  - 显示代理状态、视频监控状态
  - 迷你趋势图表

- **账号详情**：
  - 历史趋势图表（可选择指标）
  - 视频列表及详细数据
  - 检查历史记录

### 7. 导入导出

- **导出账号**：导出为 CSV/Excel 文件
- **导入账号**：从 CSV/Excel 文件批量导入

## 🔧 开发说明

### 项目结构

```
tiktok-monitor/
├── backend/                 # 后端服务
│   ├── app/
│   │   ├── api/            # API 路由
│   │   ├── core/           # 核心配置
│   │   ├── models/         # 数据模型
│   │   ├── schemas/        # Pydantic 模型
│   │   └── services/       # 业务逻辑
│   ├── alembic/            # 数据库迁移
│   ├── requirements.txt    # Python 依赖
│   └── run.py             # 启动脚本
├── frontend/               # 前端应用
│   ├── src/
│   │   ├── api/           # API 调用
│   │   ├── components/    # Vue 组件
│   │   ├── router/        # 路由配置
│   │   └── views/         # 页面视图
│   ├── package.json       # Node 依赖
│   └── vite.config.js     # Vite 配置
├── data/                   # 数据目录（SQLite）
├── docker-compose.yml      # Docker 编排
└── deploy.sh              # 部署脚本
```

### API 文档

启动后端服务后，访问 http://localhost:8000/docs 查看完整的 API 文档（Swagger UI）。

### 数据库迁移

```bash
cd tiktok-monitor/backend

# 创建新迁移
alembic revision --autogenerate -m "description"

# 执行迁移
alembic upgrade head

# 回滚迁移
alembic downgrade -1
```

### 前端构建

```bash
cd tiktok-monitor/frontend

# 开发构建
npm run dev

# 生产构建
npm run build

# 预览生产构建
npm run preview
```

## 🐛 故障排查

### 端口被占用

**查找占用进程：**

```powershell
# Windows - 查看 8000 端口占用
netstat -ano | findstr :8000

# 根据 PID 结束进程（替换 <PID> 为实际进程号）
taskkill /PID <PID> /F
```

```bash
# Linux/Mac
lsof -i :8000
kill -9 <PID>
```

**或者修改端口（推荐）：**

1. 修改 `backend/.env`：
```bash
PORT=8001
```

2. 修改 `frontend/vite.config.js` 中的 proxy target：
```js
proxy: {
  '/api': {
    target: 'http://localhost:8001',  // 改成新端口
    changeOrigin: true
  }
}
```

前端端口 5173 被占用时，Vite 会自动尝试下一个可用端口，终端会提示实际地址。

### 服务无法启动

```bash
# 查看容器状态
docker-compose ps

# 查看详细日志
docker-compose logs backend
docker-compose logs frontend

# 重启服务
docker-compose restart
```

### 数据库初始化失败

```bash
# 进入后端容器
docker-compose exec backend bash

# 手动执行迁移
alembic upgrade head

# 退出容器
exit
```

### 前端无法访问后端 API

1. 检查 nginx 配置是否正确代理 `/api` 路径
2. 确认后端服务正常运行：`docker-compose logs backend`
3. 检查网络连接：`docker-compose exec frontend ping backend`

### 代理连接失败

1. 确认代理地址和端口正确
2. 测试代理连接性
3. 检查代理认证信息（用户名/密码）

### 账号检查失败

常见原因：
- TikTok API 限流：降低并发数或增加监控间隔
- 代理失效：更换代理或使用本地 IP
- 账号不存在：确认用户名正确

### 视频监控无数据

1. 确认账号已启用视频监控
2. 检查账号是否有公开视频
3. 查看后端日志确认采集状态

### 数据丢失或损坏

```bash
# 停止服务
docker-compose down

# Windows 恢复备份
rmdir /S /Q data
xcopy /E /I data_backup data

# Linux/Mac 恢复备份
# rm -rf ./data
# cp -r ./data_backup ./data

# 重启服务
docker-compose up -d
```

## 📊 性能优化

### 监控大量账号

- 调整最大并发检查数（系统设置）
- 增加监控间隔避免频繁请求
- 使用代理池分散请求

### 数据库优化

- 定期清理历史数据
- 使用 PostgreSQL 替代 SQLite（大规模部署）
- 配置数据库连接池参数

### 前端性能

- 启用 nginx gzip 压缩
- 配置静态资源缓存
- 使用 CDN 加速（可选）

## 🔒 安全建议

1. **修改默认端口**：避免使用默认的 80 和 8000 端口
2. **配置防火墙**：限制访问来源 IP
3. **使用 HTTPS**：配置 SSL 证书（生产环境）
4. **定期备份**：自动化备份数据库
5. **更新依赖**：定期更新 Docker 镜像和依赖包

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建特性分支：`git checkout -b feature/your-feature`
3. 提交更改：`git commit -am 'Add some feature'`
4. 推送分支：`git push origin feature/your-feature`
5. 提交 Pull Request

## 📄 许可证

MIT License

Copyright (c) 2026

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## 📮 联系方式

- 提交 Issue：[GitHub Issues](https://github.com/TheLayya/tiktok-monitor/issues)
- 邮箱：673105710@qq.com
- 微信：lly450200（找到微信组织）

---

⭐ 如果这个项目对你有帮助，请给个 Star！
