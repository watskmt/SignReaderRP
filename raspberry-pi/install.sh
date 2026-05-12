#!/usr/bin/env bash
# SignReader Pi Zero W セットアップスクリプト
# 使い方: bash install.sh

set -euo pipefail

INSTALL_DIR="/opt/signreader-pi"
SERVICE_NAME="signreader-capture"

echo "[1/5] システムパッケージを更新中..."
sudo apt-get update -qq
sudo apt-get install -y python3-pip python3-venv libopencv-dev v4l-utils

echo "[2/5] インストールディレクトリを作成中..."
sudo mkdir -p "$INSTALL_DIR"
sudo cp capture.py "$INSTALL_DIR/"

echo "[3/5] Python 仮想環境を構築中..."
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip --quiet
"$INSTALL_DIR/venv/bin/pip" install -r requirements.txt --quiet

echo "[4/5] 環境設定ファイルを作成中..."
if [ ! -f "$INSTALL_DIR/.env" ]; then
  cat > "$INSTALL_DIR/.env" << 'ENV'
SIGNREADER_API_URL=https://api.signreader.amtech-service.com
CAPTURE_INTERVAL=2.0
CAMERA_INDEX=0
JPEG_QUALITY=70
CAPTURE_WIDTH=640
CAPTURE_HEIGHT=480
ENV
  echo "  → $INSTALL_DIR/.env を編集して API URL などを設定してください"
fi

echo "[5/5] systemd サービスをインストール中..."
sudo cp signreader-capture.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"

echo ""
echo "インストール完了！"
echo "  状態確認: sudo systemctl status $SERVICE_NAME"
echo "  ログ確認: sudo journalctl -u $SERVICE_NAME -f"
echo "  設定変更: sudo nano $INSTALL_DIR/.env && sudo systemctl restart $SERVICE_NAME"
echo ""
echo "接続中のカメラデバイスを確認:"
v4l2-ctl --list-devices 2>/dev/null || echo "  v4l2-ctl が使えません"
