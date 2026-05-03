#!/usr/bin/env bash
# SignReader Nginx + SSL 設定スクリプト
# 使い方: ./scripts/setup-nginx.sh [setup|cert|deploy|renew]
#   setup  — nginx コンテナの設定と起動
#   cert   — Let's Encrypt SSL 証明書を取得
#   deploy — 設定をサーバーに適用（nginx 再起動）
#   renew  — SSL 証明書を更新

set -euo pipefail

# ─────────────────────────────── 設定 ─────────────────────────────────────────

SERVER_USER="${SERVER_USER:-ubuntu}"
SERVER_HOST="${SERVER_HOST:-}"
SERVER_PORT="${SERVER_PORT:-22}"
DEPLOY_DIR="${DEPLOY_DIR:-/opt/signreader}"
DOMAIN="${DOMAIN:-}"          # 例: api.signreader.example.com
EMAIL="${EMAIL:-admin@${DOMAIN}}"

# SSH キー設定
SSH_KEY_FILE=""
if [[ -n "${DEPLOY_SSH_KEY:-}" ]]; then
    SSH_KEY_FILE=$(mktemp)
    chmod 600 "$SSH_KEY_FILE"
    if [[ -f "$DEPLOY_SSH_KEY" ]]; then
        cp "$DEPLOY_SSH_KEY" "$SSH_KEY_FILE"
    else
        echo "$DEPLOY_SSH_KEY" > "$SSH_KEY_FILE"
    fi
    trap 'rm -f "$SSH_KEY_FILE"' EXIT
fi

# ─────────────────────────────── ヘルパー ─────────────────────────────────────

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

SSH_OPTS=""
if [[ -n "$SSH_KEY_FILE" ]]; then
    SSH_OPTS="-i $SSH_KEY_FILE -o StrictHostKeyChecking=no"
fi

ssh_cmd() { ssh $SSH_OPTS -p "$SERVER_PORT" "${SERVER_USER}@${SERVER_HOST}" "$@"; }
scp_file() { scp $SSH_OPTS -P "$SERVER_PORT" "$1" "${SERVER_USER}@${SERVER_HOST}:$2"; }

check_config() {
    if [[ -z "$SERVER_HOST" ]]; then error "SERVER_HOST が未設定です"; fi
    if [[ -z "$DOMAIN" ]]; then error "DOMAIN が未設定です。例: export DOMAIN=api.signreader.example.com"; fi
}

# ─────────────────────────────── nginx.conf 生成 ─────────────────────────────

generate_nginx_conf() {
    cat <<EOF
upstream signreader_api {
    server api:8000;
}

# HTTP — Let's Encrypt チャレンジ + オプションで HTTPS リダイレクト
server {
    listen 80;
    server_name ${DOMAIN};

    # Let's Encrypt 証明書更新用
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    # SSL 証明書取得前は API へのプロキシとして動作
    # 証明書取得後は HTTPS リダイレクトに切り替え
    location / {
        proxy_pass         http://signreader_api;
        proxy_set_header   Host \$host;
        proxy_set_header   X-Real-IP \$remote_addr;
        proxy_set_header   X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto \$scheme;
        client_max_body_size 20M;
    }
}

# HTTPS
server {
    listen 443 ssl http2;
    server_name ${DOMAIN};

    ssl_certificate     /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_cache   shared:SSL:10m;
    ssl_session_timeout 10m;

    # OCSP Stapling
    ssl_stapling on;
    ssl_stapling_verify on;

    # セキュリティヘッダー
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options DENY always;
    add_header X-Content-Type-Options nosniff always;

    # OCR エンドポイントはペイロードが大きいため上限を引き上げ
    client_max_body_size 20M;

    # タイムアウト（OCR 処理に時間がかかる場合に備えて延長）
    proxy_read_timeout  120s;
    proxy_send_timeout  120s;

    # ヘルスチェックエンドポイントはキャッシュしない
    location /health {
        proxy_pass         http://signreader_api;
        proxy_set_header   Host \$host;
        proxy_set_header   X-Real-IP \$remote_addr;
        proxy_cache_bypass \$http_upgrade;
    }

    location / {
        proxy_pass         http://signreader_api;
        proxy_set_header   Host \$host;
        proxy_set_header   X-Real-IP \$remote_addr;
        proxy_set_header   X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto \$scheme;
        proxy_set_header   Upgrade \$http_upgrade;
        proxy_set_header   Connection "upgrade";
    }
}
EOF
}

# ─────────────────────────────── docker-compose 更新 ──────────────────────────

generate_compose_override() {
    cat <<'EOF'
  nginx:
    image: nginx:1.25-alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - certbot_data:/var/www/certbot:ro
      - /etc/letsencrypt:/etc/letsencrypt:ro
    depends_on:
      - api
    networks:
      - signreader_net

  certbot:
    image: certbot/certbot:latest
    volumes:
      - certbot_data:/var/www/certbot
      - /etc/letsencrypt:/etc/letsencrypt
    networks:
      - signreader_net
    entrypoint: "/bin/sh -c 'trap exit TERM; while :; do certbot renew; sleep 12h & wait $${!}; done;'"
EOF
}

# ─────────────────────────────── setup ────────────────────────────────────────

cmd_setup() {
    check_config
    info "nginx 設定を開始します: ${DOMAIN}"

    # nginx.conf を生成して転送
    info "nginx.conf を生成中..."
    generate_nginx_conf > /tmp/signreader_nginx.conf
    scp_file /tmp/signreader_nginx.conf "${DEPLOY_DIR}/backend/nginx.conf"
    rm -f /tmp/signreader_nginx.conf

    # docker-compose.prod.yml に nginx/certbot サービスを追加
    info "docker-compose.prod.yml を更新中..."
    ssh_cmd bash << REMOTE
set -euo pipefail
cd ${DEPLOY_DIR}/backend

# nginx サービスが既に存在するか確認
if ! grep -q "nginx:" docker-compose.prod.yml; then
    # volumes セクションの前に nginx/certbot サービスを追加
    sed -i '/^volumes:/i\
  nginx:\
    image: nginx:1.25-alpine\
    restart: unless-stopped\
    ports:\
      - "80:80"\
      - "443:443"\
    volumes:\
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro\
      - certbot_data:/var/www/certbot:ro\
      - /etc/letsencrypt:/etc/letsencrypt:ro\
    depends_on:\
      - api\
    networks:\
      - signreader_net\
\
  certbot:\
    image: certbot/certbot:latest\
    volumes:\
      - certbot_data:/var/www/certbot\
      - /etc/letsencrypt:/etc/letsencrypt\
    networks:\
      - signreader_net\
    entrypoint: "/bin/sh -c '"'"'trap exit TERM; while :; do certbot renew; sleep 12h & wait \$\${!}; done;'"'"'"\
' docker-compose.prod.yml

    # certbot_data ボリュームを追加
    if ! grep -q "certbot_data:" docker-compose.prod.yml; then
        sed -i 's/^volumes:/volumes:\n  certbot_data:/' docker-compose.prod.yml
    fi

    echo "nginx サービスを追加しました"
else
    echo "nginx サービスは既に存在します"
fi
REMOTE

    info "nginx 設定完了。次のステップ:"
    info "  1. ./scripts/setup-nginx.sh cert  # SSL 証明書を取得"
    info "  2. ./scripts/setup-nginx.sh deploy # nginx を再起動"
}

# ─────────────────────────────── cert ─────────────────────────────────────────

cmd_cert() {
    check_config
    info "SSL 証明書を取得します: ${DOMAIN}"

    # 一時的に nginx を停止して certbot standalone で取得
    ssh_cmd bash << REMOTE
set -euo pipefail
cd ${DEPLOY_DIR}/backend

# certbot ディレクトリを作成
sudo mkdir -p /etc/letsencrypt
sudo mkdir -p ${DEPLOY_DIR}/backend/certbot-data

# nginx を停止（ポート80を解放）
docker compose -f docker-compose.prod.yml stop nginx 2>/dev/null || true

# certbot で証明書を取得
docker run --rm \
    -p 80:80 \
    -v /etc/letsencrypt:/etc/letsencrypt \
    -v ${DEPLOY_DIR}/backend/certbot-data:/var/www/certbot \
    certbot/certbot certonly \
    --standalone \
    -d ${DOMAIN} \
    --non-interactive \
    --agree-tos \
    --email ${EMAIL} \
    --keep-until-expiring

echo "証明書取得完了"
ls -la /etc/letsencrypt/live/${DOMAIN}/

# nginx を再起動
docker compose -f docker-compose.prod.yml up -d nginx
REMOTE

    info "SSL 証明書取得完了！"
}

# ─────────────────────────────── deploy ───────────────────────────────────────

cmd_deploy() {
    check_config
    info "nginx 設定を適用します..."

    # nginx.conf を転送
    info "nginx.conf を転送中..."
    generate_nginx_conf > /tmp/signreader_nginx.conf
    scp_file /tmp/signreader_nginx.conf "${DEPLOY_DIR}/backend/nginx.conf"
    rm -f /tmp/signreader_nginx.conf

    # nginx を再起動
    ssh_cmd bash << REMOTE
set -euo pipefail
cd ${DEPLOY_DIR}/backend

# 設定ファイルの構文チェック
docker compose -f docker-compose.prod.yml exec -T nginx nginx -t

# nginx をリロード（ダウンタイムなし）
docker compose -f docker-compose.prod.yml exec -T nginx nginx -s reload || \
    docker compose -f docker-compose.prod.yml up -d --force-recreate nginx

echo "nginx 再起動完了"
REMOTE

    # ヘルスチェック
    info "ヘルスチェック中..."
    sleep 2
    ssh_cmd "curl -sf https://${DOMAIN}/health | python3 -m json.tool" || warn "ヘルスチェックに失敗しました"

    info "デプロイ完了！"
    info "  https://${DOMAIN}/health"
}

# ─────────────────────────────── renew ────────────────────────────────────────

cmd_renew() {
    check_config
    info "SSL 証明書を更新します..."

    ssh_cmd bash << REMOTE
set -euo pipefail
cd ${DEPLOY_DIR}/backend

# certbot で証明書更新
docker run --rm \
    -v /etc/letsencrypt:/etc/letsencrypt \
    -v ${DEPLOY_DIR}/backend/certbot-data:/var/www/certbot \
    certbot/certbot renew \
    --non-interactive \
    --quiet \
    --deploy-hook "docker compose -f ${DEPLOY_DIR}/backend/docker-compose.prod.yml exec -T nginx nginx -s reload"

echo "証明書更新完了"
REMOTE
}

# ─────────────────────────────── status ───────────────────────────────────────

cmd_status() {
    check_config
    info "nginx 状態を確認中..."

    ssh_cmd bash << REMOTE
set -euo pipefail
cd ${DEPLOY_DIR}/backend

echo "=== nginx コンテナ状態 ==="
docker compose -f docker-compose.prod.yml ps nginx

echo ""
echo "=== SSL 証明書有効期限 ==="
if [[ -d /etc/letsencrypt/live/${DOMAIN} ]]; then
    openssl x509 -in /etc/letsencrypt/live/${DOMAIN}/cert.pem -noout -dates
else
    echo "証明書が見つかりません"
fi

echo ""
echo "=== HTTP ヘルスチェック ==="
curl -sf http://${DOMAIN}/health 2>/dev/null | python3 -m json.tool || echo "HTTP 未応答"

echo ""
echo "=== HTTPS ヘルスチェック ==="
curl -sfk https://${DOMAIN}/health 2>/dev/null | python3 -m json.tool || echo "HTTPS 未応答"

echo ""
echo "=== nginx 設定テスト ==="
docker compose -f docker-compose.prod.yml exec -T nginx nginx -t 2>&1 || true
REMOTE
}

# ─────────────────────────────── エントリーポイント ───────────────────────────

COMMAND="${1:-setup}"

case "$COMMAND" in
    setup)  cmd_setup ;;
    cert)   cmd_cert ;;
    deploy) cmd_deploy ;;
    renew)  cmd_renew ;;
    status) cmd_status ;;
    *)
        echo "使い方: $0 [setup|cert|deploy|renew|status]"
        echo ""
        echo "  setup   nginx コンテナの設定と docker-compose 更新"
        echo "  cert    Let's Encrypt SSL 証明書を取得"
        echo "  deploy  設定をサーバーに適用（nginx リロード）"
        echo "  renew   SSL 証明書を更新"
        echo "  status  nginx/SSL の状態を確認"
        echo ""
        echo "環境変数:"
        echo "  SERVER_HOST=157.120.32.150  デプロイ先サーバー（必須）"
        echo "  DOMAIN=api.signreader.example.com  ドメイン名（必須）"
        echo "  EMAIL=admin@example.com     Let's Encrypt 登録用メール"
        echo "  SERVER_USER=ubuntu          SSH ユーザー（デフォルト: ubuntu）"
        echo "  DEPLOY_SSH_KEY='...'        SSH 秘密鍵"
        exit 1
        ;;
esac
