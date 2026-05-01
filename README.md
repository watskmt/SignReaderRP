# SignReader

スマートフォンのカメラで看板をリアルタイムにOCR読み取りし、GPS座標と共に記録するアプリケーションです。

## 概要

SignReader はモバイル端末からビデオフレームを取得し、FastAPI バックエンドへ送信して PaddleOCR で OCR 処理を行います。ファジーマッチングで重複を排除し、GPS 座標と共に PostgreSQL へ保存します。モバイルクライアントは React Native 0.75 と TypeScript で構築しています。

## ユースケース

- フィールド調査での街路標識・店舗看板・建物案内の記録
- 地図作成・研究目的での走行ルート沿いの標識データ収集
- 視覚障害者向けアクセシビリティ支援
- 小売り監査：店舗の価格・販促看板の大量収集
- 旅行中に出会った看板の自動記録

## 技術スタック

| レイヤー | 技術 |
|---|---|
| モバイルクライアント | React Native 0.75.4、TypeScript |
| ナビゲーション | React Navigation v6 |
| カメラ | react-native-vision-camera v4 |
| HTTP クライアント | Axios |
| バックエンド API | FastAPI 0.104、Python 3.10 |
| OCR エンジン | PaddleOCR 2.7.3（paddlepaddle 2.6.2 CPU） |
| タスクキュー | Celery 5.3 + Redis 7 |
| キャッシュ | Redis 7 |
| データベース | PostgreSQL 15 + SQLAlchemy 2.0 |
| マイグレーション | Alembic 1.12 |
| テスト（バックエンド） | pytest 7.4、pytest-asyncio、pytest-cov |
| テスト（モバイル） | Jest 29、@testing-library/react-native |

## Android ビルド環境

| 項目 | バージョン |
|---|---|
| Android Gradle Plugin | 8.6.1 |
| Gradle | 8.10.2 |
| Kotlin | 2.0.21 |
| compileSdk / targetSdk | 35 |
| minSdk | 26 |
| NDK | 27.1.12297006 |
| New Architecture | 有効 |

## ディレクトリ構成

```
SignReader/
├── .gitignore
├── README.md
├── SPECIFICATION.md
├── TESTING_GUIDE.md
├── deploy.sh                        # デプロイスクリプト
├── scripts/
│   ├── rocky-setup.sh               # Rocky Linux VPS 初期セットアップ
│   └── nginx-signreader.conf        # nginx サブドメイン設定テンプレート
│
├── backend/
│   ├── .env.example
│   ├── .env.prod.example
│   ├── Dockerfile
│   ├── docker-compose.yml           # ローカル開発用
│   ├── docker-compose.prod.yml      # 本番用（nginx なし）
│   ├── nginx.conf                   # nginx 設定（単独デプロイ用）
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── SETUP.md
│   ├── PHASE2_GUIDE.md
│   ├── QUICKSTART.md
│   │
│   ├── app/
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── main.py                  # Phase 1（同期 OCR）
│   │   ├── main_optimized.py        # Phase 2（Celery + Redis）
│   │   ├── tasks.py
│   │   └── services/
│   │       ├── ocr_service.py
│   │       ├── cache_service.py
│   │       └── filter_service.py
│   │
│   └── tests/
│       ├── conftest.py
│       ├── test_api.py              # 17 件
│       ├── test_ocr_service.py      # 9 件
│       └── test_services.py         # 16 件
│
└── mobile/
    ├── package.json
    ├── tsconfig.json
    ├── babel.config.js
    ├── metro.config.js
    ├── jest.config.js
    ├── jest.setup.js
    ├── PHASE3_GUIDE.md
    ├── android/                     # Android ネイティブプロジェクト
    ├── ios/                         # iOS ネイティブプロジェクト
    └── src/
        ├── App.tsx
        ├── config/api.ts
        ├── context/AppContext.tsx
        ├── services/
        │   ├── api.ts
        │   ├── camera.ts
        │   └── storage.ts
        ├── screens/
        │   ├── CameraScreen.tsx
        │   ├── SessionListScreen.tsx
        │   └── ResultsScreen.tsx
        └── __tests__/services/
            ├── api.test.ts          # 8 件
            └── storage.test.ts      # 13 件
```

## クイックスタート

### バックエンド（Phase 2）

```bash
cd backend

# 仮想環境の作成と有効化（Python 3.10 必須）
python3.10 -m venv venv
source venv/bin/activate

# 依存パッケージのインストール
pip install -r requirements.txt

# PostgreSQL + Redis の起動
docker-compose up -d

# 環境変数の設定
cp .env.example .env
# .env の DATABASE_URL パスワードを docker-compose.yml に合わせて設定

# Phase 2 API サーバーの起動（非同期 OCR 対応）
uvicorn app.main_optimized:app --reload --host 0.0.0.0 --port 8000

# Celery ワーカーの起動（別ターミナル）
celery -A app.tasks.celery_app worker --loglevel=info --concurrency=2
```

Swagger UI: http://localhost:8000/docs

### モバイルアプリ

```bash
cd mobile

npm install

# Android エミュレーター
npm run android

# iOS シミュレーター
cd ios && pod install && cd ..
npm run ios
```

> **実機からの接続:** `src/config/api.ts` の `API_BASE_URL` を Mac のローカル IP（例: `http://192.168.x.x:8000`）に変更してください。

### テストの実行

```bash
# バックエンド（42 件）
cd backend && source venv/bin/activate
pytest -v

# モバイル（21 件）
cd mobile && npm test
```

## デプロイ

```bash
# Rocky Linux VPS の初期セットアップ
export SERVER_HOST=<VPS_IP>
export DOMAIN=api.example.com
sudo bash scripts/rocky-setup.sh

# アプリのデプロイ
cp backend/.env.prod.example backend/.env.prod
# .env.prod を編集してパスワード・SECRET_KEY を設定
./deploy.sh deploy

# 状態確認
./deploy.sh status
```
