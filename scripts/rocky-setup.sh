#!/usr/bin/env bash
# ============================================================
# SignReader — Rocky Linux VPS 初期セットアップスクリプト
# 前提: nginx は既存サービスがネイティブで使用中
# 対象OS: Rocky Linux 8.x / 9.x
# 実行方法: sudo bash rocky-setup.sh
# ============================================================

set -euo pipefail

# ─────────────────────────────── 設定（変更可）──────────────────────────────

DEPLOY_USER="${DEPLOY_USER:-signreader}"
DEPLOY_DIR="${DEPLOY_DIR:-/opt/signreader}"
SSH_PORT="${SSH_PORT:-22}"
ALLOWED_SSH_IP="${ALLOWED_SSH_IP:-}"
TIMEZONE="${TIMEZONE:-Asia/Tokyo}"
DOMAIN="${DOMAIN:-}"                          # 例: api.example.com

# ─────────────────────────────── ヘルパー ────────────────────────────────────

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
STEP=0
info()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
error() { echo -e "${RED}[✗]${NC} $*"; exit 1; }
step()  { STEP=$((STEP+1)); echo -e "\n${CYAN}━━━ Step ${STEP}: $* ━━━${NC}"; }

[[ $EUID -ne 0 ]] && error "root または sudo で実行してください"
grep -qi "rocky" /etc/os-release 2>/dev/null || warn "Rocky Linux 以外の OS の可能性があります"
OS_VERSION=$(rpm -E %{rhel} 2>/dev/null || echo "8")
info "Rocky Linux ${OS_VERSION} を検出"

# ─────────────────────────────── Step 1: システム更新 ────────────────────────

step "システムパッケージの更新"
dnf update -y --quiet
dnf install -y --quiet \
    curl wget git vim nano htop \
    tar unzip zip \
    net-tools bind-utils \
    bash-completion \
    epel-release
info "完了"

# ─────────────────────────────── Step 2: タイムゾーン ────────────────────────

step "タイムゾーンの設定"
timedatectl set-timezone "$TIMEZONE"
timedatectl set-ntp true
info "タイムゾーン: $(timedatectl show --property=Timezone --value)"

# ─────────────────────────────── Step 3: SSH セキュリティ ────────────────────

step "SSH のセキュリティ設定"
SSHD_CONF="/etc/ssh/sshd_config"
cp -n "${SSHD_CONF}" "${SSHD_CONF}.bak"

declare -A SSH_SETTINGS=(
    ["Port"]="$SSH_PORT"
    ["PermitRootLogin"]="no"
    ["PasswordAuthentication"]="no"
    ["PubkeyAuthentication"]="yes"
    ["MaxAuthTries"]="3"
    ["ClientAliveInterval"]="300"
    ["ClientAliveCountMax"]="2"
    ["X11Forwarding"]="no"
)
for key in "${!SSH_SETTINGS[@]}"; do
    value="${SSH_SETTINGS[$key]}"
    if grep -q "^#\?${key}" "$SSHD_CONF"; then
        sed -i "s|^#\?${key}.*|${key} ${value}|" "$SSHD_CONF"
    else
        echo "${key} ${value}" >> "$SSHD_CONF"
    fi
done
systemctl reload sshd
info "SSH 設定完了（ポート: ${SSH_PORT}）"

# ─────────────────────────────── Step 4: ファイアウォール ────────────────────

step "firewalld の設定"
systemctl enable --now firewalld

if [[ "$SSH_PORT" != "22" ]]; then
    firewall-cmd --permanent --remove-service=ssh 2>/dev/null || true
    firewall-cmd --permanent --add-port="${SSH_PORT}/tcp"
else
    firewall-cmd --permanent --add-service=ssh
fi
firewall-cmd --permanent --add-service=http
firewall-cmd --permanent --add-service=https

# SignReader の Docker ポートは外部に公開しない（localhost のみ）
# nginx が 80/443 でリバースプロキシするため不要

[[ -n "$ALLOWED_SSH_IP" ]] && \
    firewall-cmd --permanent --add-rich-rule="rule family='ipv4' source address='${ALLOWED_SSH_IP}' port port='${SSH_PORT}' protocol='tcp' accept"

firewall-cmd --reload
info "ファイアウォール設定完了"

# ─────────────────────────────── Step 5: SELinux ─────────────────────────────

step "SELinux の設定"
SELINUX_STATUS=$(getenforce)
info "SELinux モード: ${SELINUX_STATUS}"

if [[ "$SELINUX_STATUS" == "Enforcing" ]]; then
    # nginx → Docker コンテナへのプロキシを許可
    setsebool -P httpd_can_network_connect 1
    setsebool -P httpd_can_network_relay 1
    info "nginx → Docker プロキシを SELinux で許可"
fi

# ─────────────────────────────── Step 6: Docker ──────────────────────────────

step "Docker のインストール"
if command -v docker &>/dev/null; then
    info "Docker は既にインストール済み: $(docker --version)"
else
    dnf config-manager --add-repo https://download.docker.com/linux/rhel/docker-ce.repo
    dnf install -y --quiet docker-ce docker-ce-cli containerd.io docker-compose-plugin
    systemctl enable --now docker
    info "Docker インストール完了: $(docker --version)"
fi
docker compose version &>/dev/null || error "Docker Compose のインストールに失敗"
info "Docker Compose: $(docker compose version)"

# ─────────────────────────────── Step 7: デプロイユーザー ────────────────────

step "デプロイユーザー（${DEPLOY_USER}）の作成"
if ! id "$DEPLOY_USER" &>/dev/null; then
    useradd -m -s /bin/bash "$DEPLOY_USER"
    info "ユーザー ${DEPLOY_USER} を作成"
else
    info "ユーザー ${DEPLOY_USER} は既に存在"
fi
usermod -aG docker "$DEPLOY_USER"

SSH_DIR="/home/${DEPLOY_USER}/.ssh"
mkdir -p "$SSH_DIR"
chmod 700 "$SSH_DIR"
touch "${SSH_DIR}/authorized_keys"
chmod 600 "${SSH_DIR}/authorized_keys"
chown -R "${DEPLOY_USER}:${DEPLOY_USER}" "$SSH_DIR"

mkdir -p "$DEPLOY_DIR"
chown -R "${DEPLOY_USER}:${DEPLOY_USER}" "$DEPLOY_DIR"
chmod 750 "$DEPLOY_DIR"
info "完了"

# ─────────────────────────────── Step 8: システムチューニング ────────────────

step "システムパラメータのチューニング"
cat > /etc/sysctl.d/99-signreader.conf << 'EOF'
net.core.somaxconn = 65535
net.ipv4.tcp_max_syn_backlog = 65535
net.ipv4.tcp_tw_reuse = 1
net.ipv4.tcp_fin_timeout = 15
vm.swappiness = 10
vm.overcommit_memory = 1
fs.file-max = 65535
EOF
sysctl -p /etc/sysctl.d/99-signreader.conf --quiet

cat > /etc/security/limits.d/99-signreader.conf << EOF
${DEPLOY_USER} soft nofile 65535
${DEPLOY_USER} hard nofile 65535
EOF
info "完了"

# ─────────────────────────────── Step 9: Swap ────────────────────────────────

step "Swap の設定（PaddleOCR のメモリ対策）"
if ! swapon --show | grep -q "/swapfile"; then
    TOTAL_MEM=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
    if [[ "$TOTAL_MEM" -lt 4096 ]]; then
        fallocate -l 2G /swapfile
        chmod 600 /swapfile
        mkswap /swapfile
        swapon /swapfile
        echo '/swapfile none swap sw 0 0' >> /etc/fstab
        info "Swap 2GB 作成（メモリ: ${TOTAL_MEM}MB）"
    else
        info "メモリ十分のためスキップ（${TOTAL_MEM}MB）"
    fi
else
    info "Swap は設定済み"
fi

# ─────────────────────────────── Step 10: nginx サブドメイン設定 ─────────────

step "nginx サブドメイン設定の配置"

# 既存 nginx の確認
if ! command -v nginx &>/dev/null; then
    warn "nginx が見つかりません。インストールするか手動で設定してください"
else
    NGINX_CONF_DIR=""
    [[ -d "/etc/nginx/conf.d" ]]       && NGINX_CONF_DIR="/etc/nginx/conf.d"
    [[ -d "/etc/nginx/sites-available" ]] && NGINX_CONF_DIR="/etc/nginx/sites-available"

    if [[ -n "$NGINX_CONF_DIR" && -n "$DOMAIN" ]]; then
        CONF_FILE="${NGINX_CONF_DIR}/signreader.conf"
        cat > "$CONF_FILE" << NGINXCONF
# SignReader — ${DOMAIN}
server {
    listen 80;
    server_name ${DOMAIN};

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }
    location / {
        return 301 https://\$host\$request_uri;
    }
}

server {
    listen 443 ssl;
    http2  on;
    server_name ${DOMAIN};

    ssl_certificate     /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_session_cache   shared:SSL:10m;

    add_header Strict-Transport-Security "max-age=63072000" always;
    add_header X-Frame-Options           DENY;
    add_header X-Content-Type-Options    nosniff;

    client_max_body_size 20M;
    proxy_read_timeout   120s;

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header   Host              \$host;
        proxy_set_header   X-Real-IP         \$remote_addr;
        proxy_set_header   X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto \$scheme;
        proxy_set_header   Connection        "";
    }

    location = /health {
        proxy_pass http://127.0.0.1:8000;
        access_log off;
    }
}
NGINXCONF

        # sites-available の場合は sites-enabled にシンボリックリンク
        [[ "$NGINX_CONF_DIR" == "/etc/nginx/sites-available" ]] && \
            ln -sf "$CONF_FILE" "/etc/nginx/sites-enabled/signreader.conf"

        # 設定テスト
        if nginx -t 2>/dev/null; then
            info "nginx 設定ファイルを配置: ${CONF_FILE}"
            warn "SSL 証明書取得後に nginx をリロードしてください: systemctl reload nginx"
        else
            warn "nginx 設定テストに失敗。手動で確認してください: nginx -t"
        fi
    else
        warn "DOMAIN が未設定のため nginx 設定をスキップ"
        info "後から設定する場合: scripts/nginx-signreader.conf を /etc/nginx/conf.d/ に配置"
    fi
fi

# ─────────────────────────────── Step 11: SSL 証明書 ─────────────────────────

step "SSL 証明書の取得（certbot）"
if [[ -n "$DOMAIN" ]]; then
    if ! command -v certbot &>/dev/null; then
        dnf install -y --quiet certbot python3-certbot-nginx
        info "certbot インストール完了"
    fi

    # 既存証明書の確認
    if [[ -f "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" ]]; then
        info "証明書は既に存在: /etc/letsencrypt/live/${DOMAIN}/"
    else
        # nginx を止めずに webroot 方式で取得
        mkdir -p /var/www/certbot
        # 一時的に HTTP のみの設定を先に nginx に読み込ませる必要があるため案内のみ
        warn "SSL 証明書は以下のコマンドで取得してください（nginx リロード後）:"
        warn "  certbot --nginx -d ${DOMAIN} --non-interactive --agree-tos -m admin@${DOMAIN}"
    fi

    # 自動更新の設定
    systemctl enable --now certbot-renew.timer 2>/dev/null || \
        (crontab -l 2>/dev/null; echo "0 3 * * * certbot renew --quiet --deploy-hook 'systemctl reload nginx'") | crontab -
    info "SSL 自動更新を設定"
else
    warn "DOMAIN が未設定のため SSL 設定をスキップ"
fi

# ─────────────────────────────── Step 12: systemd サービス ───────────────────

step "systemd サービスの登録（自動起動）"
cat > /etc/systemd/system/signreader.service << EOF
[Unit]
Description=SignReader Application (Docker)
Requires=docker.service
After=docker.service network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
User=${DEPLOY_USER}
WorkingDirectory=${DEPLOY_DIR}/backend
ExecStart=/usr/bin/docker compose -f docker-compose.prod.yml up -d --remove-orphans
ExecStop=/usr/bin/docker compose -f docker-compose.prod.yml down
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable signreader.service
info "systemd 登録完了（OS 起動時に自動起動）"

# ─────────────────────────────── Step 13: fail2ban ───────────────────────────

step "fail2ban のインストール"
if ! command -v fail2ban-server &>/dev/null; then
    dnf install -y --quiet fail2ban
fi
cat > /etc/fail2ban/jail.local << EOF
[DEFAULT]
bantime  = 3600
findtime = 600
maxretry = 5
backend  = systemd

[sshd]
enabled = true
port    = ${SSH_PORT}
EOF
systemctl enable --now fail2ban
info "fail2ban 設定完了"

# ─────────────────────────────── Step 14: 自動セキュリティアップデート ────────

step "自動セキュリティアップデートの設定"
dnf install -y --quiet dnf-automatic
sed -i 's/^apply_updates.*$/apply_updates = yes/' /etc/dnf/automatic.conf
sed -i 's/^upgrade_type.*$/upgrade_type = security/' /etc/dnf/automatic.conf
systemctl enable --now dnf-automatic.timer
info "完了"

# ─────────────────────────────── 完了サマリー ────────────────────────────────

echo ""
echo -e "${GREEN}╔═══════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║       Rocky Linux セットアップ完了！                   ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════════════════════╝${NC}"
echo ""
printf "  %-20s %s\n" "OS:"          "Rocky Linux ${OS_VERSION}"
printf "  %-20s %s\n" "タイムゾーン:" "${TIMEZONE}"
printf "  %-20s %s\n" "SSH ポート:"  "${SSH_PORT}"
printf "  %-20s %s\n" "デプロイUser:" "${DEPLOY_USER}"
printf "  %-20s %s\n" "デプロイDir:"  "${DEPLOY_DIR}"
printf "  %-20s %s\n" "Docker:"       "$(docker --version | awk '{print $3}' | tr -d ',')"
[[ -n "$DOMAIN" ]] && \
printf "  %-20s %s\n" "ドメイン:"    "${DOMAIN}"
echo ""
echo -e "${YELLOW}━━━ 次のステップ ━━━${NC}"
echo ""
echo "  1. SSH 公開鍵を登録"
echo "     echo '<your_public_key>' >> /home/${DEPLOY_USER}/.ssh/authorized_keys"
echo ""
echo "  2. 新しいターミナルで接続確認（このセッションを閉じる前に！）"
echo "     ssh -p ${SSH_PORT} ${DEPLOY_USER}@<SERVER_IP>"
echo ""
echo "  3. ローカルからデプロイ実行"
echo "     export SERVER_HOST=<SERVER_IP>"
echo "     export SERVER_USER=${DEPLOY_USER}"
echo "     export SERVER_PORT=${SSH_PORT}"
echo "     cp backend/.env.prod.example backend/.env.prod"
echo "     # .env.prod を編集してパスワード・SECRET_KEY を設定"
echo "     ./deploy.sh deploy"
echo ""
if [[ -n "$DOMAIN" ]]; then
echo "  4. SSL 証明書の取得（nginx リロード後）"
echo "     certbot --nginx -d ${DOMAIN} --non-interactive --agree-tos -m admin@${DOMAIN}"
echo "     systemctl reload nginx"
echo ""
fi
echo -e "${RED}  注意: SSH ポートを変更した場合、新しいターミナルで接続できることを必ず確認してください${NC}"
echo ""
