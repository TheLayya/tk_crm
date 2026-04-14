#!/bin/bash
# =============================================================================
# TikTok Monitor - Ubuntu 一键部署脚本
# 支持从 GitHub 私有仓库部署，Cloudflare 域名解析
#
# 用法:
#   首次部署:  bash deploy.sh
#   更新部署:  bash deploy.sh --update
#   查看日志:  bash deploy.sh --logs
#   停止服务:  bash deploy.sh --stop
#   重启服务:  bash deploy.sh --restart
#   查看状态:  bash deploy.sh --status
# =============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

log()   { echo -e "${GREEN}[✓]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
error() { echo -e "${RED}[✗]${NC} $1"; exit 1; }
info()  { echo -e "${BLUE}[→]${NC} $1"; }
title() { echo -e "${CYAN}$1${NC}"; }

# =============================================================================
# GitHub Token 管理（首次输入后保存，后续自动读取）
# =============================================================================
TOKEN_FILE="$HOME/.github_token"
SCRIPT_URL="https://raw.githubusercontent.com/TheLayya/tk_crm/main/deploy.sh"

# 如果通过 curl | bash 执行（没有脚本文件路径），先处理 token 再重新拉取执行
if [ -z "$BASH_SOURCE" ] || [ "$BASH_SOURCE" = "bash" ] || [ "$0" = "bash" ]; then
  if [ ! -f "$TOKEN_FILE" ]; then
    echo -e "${BLUE}[?]${NC} 首次运行，请输入 GitHub Personal Access Token:"
    read -rsp "  Token: " _token
    echo ""
    [ -z "$_token" ] && echo -e "${RED}[✗]${NC} Token 不能为空" && exit 1
    echo "$_token" > "$TOKEN_FILE"
    chmod 600 "$TOKEN_FILE"
    echo -e "${GREEN}[✓]${NC} Token 已保存到 $TOKEN_FILE，后续无需重复输入"
  fi
  _saved_token=$(cat "$TOKEN_FILE")
  exec bash <(curl -fsSL -H "Authorization: token $_saved_token" "$SCRIPT_URL") "$@"
fi

# 读取已保存的 token（本地执行时使用）
if [ -f "$TOKEN_FILE" ]; then
  SAVED_GITHUB_TOKEN=$(cat "$TOKEN_FILE")
fi

# =============================================================================
# 子命令处理（在项目目录内执行）
# =============================================================================
case "$1" in
  --update)
    info "拉取最新代码..."
    git pull
    info "重新构建并重启服务..."
    docker compose down
    docker compose up -d --build
    log "更新完成！"
    docker compose ps
    exit 0
    ;;
  --logs)
    docker compose logs -f
    exit 0
    ;;
  --stop)
    docker compose down
    log "服务已停止"
    exit 0
    ;;
  --restart)
    docker compose restart
    log "服务已重启"
    exit 0
    ;;
  --status)
    docker compose ps
    exit 0
    ;;
esac

# =============================================================================
# 首次部署流程
# =============================================================================
echo ""
title "=============================================="
title "   TikTok Monitor - Ubuntu 一键部署脚本"
title "=============================================="
echo ""

# --- 1. 检查系统依赖 ---
info "检查系统依赖..."
sudo apt-get update -qq
sudo apt-get install -y -qq curl git python3 openssl

# --- 2. 安装 Docker ---
if ! command -v docker &>/dev/null; then
  warn "未检测到 Docker，开始自动安装..."
  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  sudo chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
    https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
  sudo apt-get update -qq
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
  sudo systemctl enable docker
  sudo systemctl start docker
  sudo usermod -aG docker "$USER"
  log "Docker 安装完成（需重新登录 SSH 才能免 sudo 使用 docker）"
else
  log "Docker 已安装: $(docker --version | head -1)"
fi

if ! docker compose version &>/dev/null; then
  error "docker compose 插件未安装，请升级 Docker 到 20.10+"
fi
log "Docker Compose: $(docker compose version --short)"

# --- 3. 收集配置信息 ---
echo ""
title "--- 配置信息 ---"
echo ""

# GitHub 仓库
read -rp "$(echo -e "${BLUE}[?]${NC} GitHub 仓库地址 (例: https://github.com/yourname/tiktok-monitor): ")" GITHUB_REPO
[ -z "$GITHUB_REPO" ] && error "仓库地址不能为空"

# Personal Access Token（优先使用已保存的 token）
if [ -n "$SAVED_GITHUB_TOKEN" ]; then
  GITHUB_TOKEN="$SAVED_GITHUB_TOKEN"
  log "使用已保存的 GitHub Token"
else
  read -rsp "$(echo -e "${BLUE}[?]${NC} GitHub Personal Access Token: ")" GITHUB_TOKEN
  echo ""
  [ -z "$GITHUB_TOKEN" ] && error "Token 不能为空"
  # 保存供下次使用
  echo "$GITHUB_TOKEN" > "$TOKEN_FILE"
  chmod 600 "$TOKEN_FILE"
  log "Token 已保存到 $TOKEN_FILE"
fi

# 安装目录
read -rp "$(echo -e "${BLUE}[?]${NC} 安装目录 [默认: /opt/tiktok-monitor]: ")" INSTALL_DIR
INSTALL_DIR="${INSTALL_DIR:-/opt/tiktok-monitor}"

# 域名（可选）
read -rp "$(echo -e "${BLUE}[?]${NC} 域名 (例: monitor.example.com，留空则用 IP 访问): ")" DOMAIN

# 管理员密码
read -rsp "$(echo -e "${BLUE}[?]${NC} 管理员初始密码 [默认: admin123456]: ")" ADMIN_PASSWORD
echo ""
ADMIN_PASSWORD="${ADMIN_PASSWORD:-admin123456}"

echo ""

# --- 4. Clone 仓库 ---
info "克隆仓库到 ${INSTALL_DIR}..."

# 将 token 嵌入 URL（支持私有仓库）
# 格式: https://<token>@github.com/user/repo.git
REPO_WITH_TOKEN=$(echo "$GITHUB_REPO" | sed "s|https://|https://${GITHUB_TOKEN}@|")

if [ -d "$INSTALL_DIR/.git" ]; then
  warn "目录已存在，执行 git pull 更新..."
  cd "$INSTALL_DIR"
  # 更新 remote URL（token 可能变了）
  git remote set-url origin "$REPO_WITH_TOKEN"
  git pull
else
  sudo mkdir -p "$(dirname "$INSTALL_DIR")"
  sudo git clone "$REPO_WITH_TOKEN" "$INSTALL_DIR"
  sudo chown -R "$USER:$USER" "$INSTALL_DIR"
  cd "$INSTALL_DIR"
fi

log "代码已就绪: $INSTALL_DIR"

# 从 remote URL 中移除 token（安全起见，存储不含 token 的地址）
git remote set-url origin "$GITHUB_REPO"

# --- 5. 生成 backend/.env ---
info "配置环境变量..."
if [ ! -f backend/.env ]; then
  cp backend/.env.example backend/.env

  JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null \
    || openssl rand -hex 32)
  FIELD_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null \
    || openssl rand -hex 32)

  sed -i "s|your-secret-key-change-in-production|${JWT_SECRET}|g" backend/.env
  sed -i "s|9b7d1f8a2c5e07394628abcfed1056798024bdf671ea5c0392785601dafb4729|${FIELD_KEY}|g" backend/.env
  sed -i "s|SUPER_ADMIN_PASSWORD=admin123456|SUPER_ADMIN_PASSWORD=${ADMIN_PASSWORD}|g" backend/.env

  log "backend/.env 已生成（密钥已随机生成）"
else
  log "backend/.env 已存在，跳过生成"
fi

# --- 6. 生成 frontend/.env ---
if [ ! -f frontend/.env ]; then
  cp frontend/.env.example frontend/.env
  log "frontend/.env 已生成"
fi

# --- 7. 创建数据目录 ---
mkdir -p data
log "数据目录已就绪: ${INSTALL_DIR}/data"

# --- 8. 构建并启动 ---
info "构建 Docker 镜像（首次约需 3-5 分钟）..."
docker compose build --no-cache

info "启动服务..."
docker compose up -d

# --- 9. 等待健康检查 ---
info "等待服务启动..."
MAX_WAIT=90
WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
  STATUS=$(docker inspect --format='{{.State.Health.Status}}' tiktok-monitor-backend 2>/dev/null || echo "starting")
  [ "$STATUS" = "healthy" ] && break
  sleep 3
  WAITED=$((WAITED + 3))
  echo -n "."
done
echo ""

# --- 10. 配置开机自启（systemd）---
info "配置开机自启..."
COMPOSE_BIN=$(which docker)
cat > /tmp/tiktok-monitor.service << EOF
[Unit]
Description=TikTok Monitor
Requires=docker.service
After=docker.service network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=${INSTALL_DIR}
ExecStart=${COMPOSE_BIN} compose up -d
ExecStop=${COMPOSE_BIN} compose down
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target
EOF

sudo mv /tmp/tiktok-monitor.service /etc/systemd/system/tiktok-monitor.service
sudo systemctl daemon-reload
sudo systemctl enable tiktok-monitor.service
log "开机自启已配置"

# --- 11. 输出结果 ---
HOST_IP=$(hostname -I | awk '{print $1}')

echo ""
title "=============================================="
docker compose ps
title "=============================================="
echo ""
log "部署完成！"
echo ""

if [ -n "$DOMAIN" ]; then
  echo -e "  ${GREEN}前端界面:${NC}  http://${DOMAIN}"
  echo -e "  ${GREEN}后端 API:${NC}  http://${DOMAIN}/api"
  echo -e "  ${GREEN}API 文档:${NC}  http://${DOMAIN}:8000/docs"
  echo ""
  echo -e "  ${YELLOW}Cloudflare 配置提示:${NC}"
  echo "    1. 在 Cloudflare DNS 添加 A 记录: ${DOMAIN} → ${HOST_IP}"
  echo "    2. 代理状态设为「已代理」（橙色云朵）"
  echo "    3. SSL/TLS 模式设为「灵活」或「完全」"
else
  echo -e "  ${GREEN}前端界面:${NC}  http://${HOST_IP}"
  echo -e "  ${GREEN}后端 API:${NC}  http://${HOST_IP}:8000"
  echo -e "  ${GREEN}API 文档:${NC}  http://${HOST_IP}:8000/docs"
fi

echo ""
echo -e "  ${GREEN}管理员账号:${NC}  admin"
echo -e "  ${GREEN}管理员密码:${NC}  ${ADMIN_PASSWORD}"
echo ""
echo -e "  ${CYAN}安装目录:${NC}  ${INSTALL_DIR}"
echo ""
echo "  常用命令（在 ${INSTALL_DIR} 目录下执行）:"
echo "    更新部署:  bash deploy.sh --update"
echo "    查看日志:  bash deploy.sh --logs"
echo "    停止服务:  bash deploy.sh --stop"
echo "    重启服务:  bash deploy.sh --restart"
echo "    查看状态:  bash deploy.sh --status"
echo ""
