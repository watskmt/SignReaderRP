# SignReader

スマートフォンのカメラで看板をリアルタイムにOCR読み取りし、GPS座標と共に記録するアプリケーションです。歩きながら・運転しながらカメラを向けるだけで、検出したテキストを自動的に抽出・重複排除・位置情報タグ付けします。

## 概要

SignReaderはモバイル端末からビデオフレームを取得し、FastAPIバックエンドへ送信してPaddleOCRでOCR処理を行います。ファジーマッチングで重複を排除し、GPS座標と共にPostgreSQLへ保存します。モバイルクライアントはReact NativeとTypeScriptで構築しています。

## ユースケース

- フィールド調査での街路標識・店舗看板・建物案内の記録
- 地図作成・研究目的での走行ルート沿いの標識データ収集
- 視覚障害者向けアクセシビリティ支援：看板の音声読み上げ
- 小売り監査：店舗の価格・販促看板の大量収集
- 観光：旅行中に出会った看板の自動記録

## 技術スタック

| レイヤー | 技術 |
|---|---|
| モバイルクライアント | React Native 0.73、TypeScript |
| ナビゲーション | React Navigation v6 |
| HTTPクライアント | Axios |
| バックエンドAPI | FastAPI 0.104、Python 3.11 |
| OCRエンジン | PaddleOCR 2.7（paddlepaddle CPU） |
| タスクキュー | Celery 5.3 + Redis 7 |
| キャッシュ | Redis 7 |
| データベース | PostgreSQL 15 + SQLAlchemy 2.0 |
| マイグレーション | Alembic 1.12 |
| テスト（バックエンド） | pytest、pytest-asyncio、pytest-cov |
| テスト（フロントエンド） | Jest、@testing-library/react-native |

## ディレクトリ構成

```
SignReader/
├── .gitignore
├── README.md
├── SPECIFICATION.md
├── TESTING_GUIDE.md
│
├── backend/
│   ├── .env
│   ├── .env.example
│   ├── docker-compose.yml
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── SETUP.md
│   ├── PHASE2_GUIDE.md
│   ├── QUICKSTART.md
│   │
│   ├── app/
│   │   ├── __init__.py
│   │   ├── config.py          # Pydantic設定
│   │   ├── database.py        # SQLAlchemyエンジン + セッション
│   │   ├── models.py          # User, Session, Extraction ORMモデル
│   │   ├── schemas.py         # Pydantic v2 リクエスト/レスポンススキーマ
│   │   ├── main.py            # Phase 1 FastAPIアプリ
│   │   ├── main_optimized.py  # Phase 2 FastAPIアプリ（Celery + Redis）
│   │   ├── tasks.py           # Celeryタスク
│   │   │
│   │   └── services/
│   │       ├── __init__.py
│   │       ├── ocr_service.py     # PaddleOCRラッパー
│   │       ├── cache_service.py   # Redisキャッシュ層
│   │       └── filter_service.py  # 重複排除 + キーワードフィルタ
│   │
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py
│       ├── test_api.py
│       ├── test_ocr_service.py
│       └── test_services.py
│
└── mobile/
    ├── package.json
    ├── tsconfig.json
    ├── app.json
    ├── index.js
    ├── babel.config.js
    ├── jest.config.js
    ├── jest.setup.js
    ├── PHASE3_GUIDE.md
    │
    └── src/
        ├── App.tsx
        ├── config/
        │   └── api.ts
        ├── context/
        │   └── AppContext.tsx
        ├── services/
        │   ├── api.ts
        │   ├── camera.ts
        │   └── storage.ts
        ├── screens/
        │   ├── CameraScreen.tsx
        │   ├── SessionListScreen.tsx
        │   └── ResultsScreen.tsx
        └── __tests__/
            └── services/
                ├── api.test.ts
                └── storage.test.ts
```

## クイックスタート

### バックエンド（Phase 1）

```bash
cd backend

# 仮想環境の作成と有効化
python3.10 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 依存パッケージのインストール
pip install -r requirements.txt

# PostgreSQL + Redis の起動
docker-compose up -d

# 環境ファイルのコピー
cp .env.example .env

# APIサーバーの起動（テーブルは起動時に自動作成）
uvicorn app.main:app --reload --port 8000
```

ブラウザで [http://localhost:8000/docs](http://localhost:8000/docs) を開くとSwagger UIが表示されます。

### モバイルアプリ（Phase 3）

```bash
cd mobile

# JS依存パッケージのインストール
npm install

# iOSのみ
cd ios && pod install && cd ..

# Metro bundlerの起動
npm start

# iOSシミュレーターで実行
npm run ios

# Androidエミュレーターで実行
npm run android
```

### テストの実行

```bash
# バックエンド
cd backend
source venv/bin/activate
pytest --cov=app tests/

# モバイル
cd mobile
npm test
npm run test:coverage
```
