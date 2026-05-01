# SignReader — 技術仕様書

**バージョン:** 1.1
**更新日:** 2026-05-01
**作成者:** SignReader エンジニアリングチーム

---

## 1. 概要とユースケース

SignReader は、ライブカメラ映像から看板を読み取り、抽出したテキストを GPS 座標と共に記録するスマートフォンアプリケーションです。

### 主なユースケース

| ユースケース | 説明 |
|---|---|
| フィールド調査 | 研究者がルートを歩きながら全看板を位置情報付きで記録 |
| ルート記録 | 地図データベース用に走行中の道路標識を記録 |
| アクセシビリティ | 視覚障害者向けのリアルタイム看板読み上げ |
| 小売り監査 | 複数店舗の価格・販促看板を大規模に収集 |
| 旅行記録 | 旅行中に出会った全看板の自動ジャーナル |

### スコープ外（v1）

- 手書き文字認識
- リアルタイム音声出力
- デバイス間のクラウド同期

---

## 2. システムアーキテクチャ

```
┌──────────────────────────────────────────────────┐
│              モバイルクライアント                   │
│  React Native 0.75.4 + TypeScript                │
│  ┌────────────────┐  ┌──────────┐  ┌──────────┐ │
│  │ VisionCamera v4 │  │   GPS    │  │AsyncStore│ │
│  └───────┬────────┘  └─────┬────┘  └────┬─────┘ │
│          └────────────┬────┘             │       │
└───────────────────────┼──────────────────┘
                        │ HTTP/JSON (Axios)
┌───────────────────────▼──────────────────────────┐
│              FastAPI バックエンド                  │
│  ┌─────────────────────────────────────────────┐ │
│  │  REST API（Phase 2: main_optimized.py）      │ │
│  │  /health /sessions /ocr /extract /filters   │ │
│  └──────────────────┬──────────────────────────┘ │
│  ┌──────────┐ ┌─────┴──────┐ ┌────────────────┐  │
│  │PaddleOCR │ │   Redis    │ │ Celery Worker  │  │
│  │  2.7.3   │ │  キャッシュ │ │  非同期タスク  │  │
│  └──────────┘ └────────────┘ └────────────────┘  │
└──────────────────────┬───────────────────────────┘
                       │ SQLAlchemy 2.0
┌──────────────────────▼───────────────────────────┐
│              PostgreSQL 15                       │
│   users  |  sessions  |  extractions             │
└──────────────────────────────────────────────────┘
```

---

## 3. 機能要件

### 3.1 リアルタイム OCR

- FR-01: base64 エンコードフレームを受け取り 300ms 以内（p95）にテキストを返すこと
- FR-02: 同期 OCR（Phase 1）と非同期 Celery ベース OCR（Phase 2）をサポート
- FR-03: 信頼度閾値（デフォルト 0.6）以下の結果をフィルタリング
- FR-04: 検出テキスト領域のバウンディングボックス座標を返す

### 3.2 GPS 記録

- FR-05: 各 OCR リクエストに緯度・経度・高度をオプションとして受け付ける
- FR-06: GPS 座標は各抽出レコードと共に保存
- FR-07: GPS 記録有効化前に位置情報の許可を要求

### 3.3 重複排除とフィルタ

- FR-08: ファジーマッチング（類似度 85% 以上）で類似テキストを検出
- FR-09: 重複抽出結果は `is_duplicate=true` でマーク（削除しない）
- FR-10: セッション単位でキーワード包含/除外フィルタを設定可能
- FR-11: キーワードフィルタは Redis に保存し抽出保存前に適用

### 3.4 セッション管理

- FR-12: 名前付きセッションの作成
- FR-13: セッションステータス: active / completed / archived
- FR-14: セッション全抽出結果の JSON エクスポート
- FR-15: Celery 定期タスクで 30 日以上前のセッションを自動アーカイブ

---

## 4. 非機能要件

| カテゴリ | 要件 |
|---|---|
| OCR レイテンシ | p95 ≤ 300ms（CPU 推論） |
| スループット | 10 並行 OCR リクエスト |
| OCR 精度 | 鮮明な印刷看板で 85% 以上 |
| 重複誤検知率 | < 5% |
| GPS | オプション・ユーザー制御（GDPR 準拠） |
| 通信 | 本番環境は HTTPS 必須 |
| モバイル最小 SDK | Android 26（Vision Camera 要件） |
| フレーム取得間隔 | 設定可能（最小 200ms、デフォルト 500ms） |

---

## 5. API エンドポイント仕様

### Phase 1（main.py）— 同期

| メソッド | パス | 説明 |
|---|---|---|
| GET | `/health` | 死活監視 |
| POST | `/sessions` | セッション作成 |
| GET | `/sessions/{id}` | セッション取得 |
| POST | `/ocr/process` | 同期 OCR 処理 |
| POST | `/extract/save` | 抽出結果保存 |
| GET | `/extract/{session_id}` | 抽出結果一覧 |

### Phase 2（main_optimized.py）— 非同期・推奨

上記 Phase 1 エンドポイントに加えて:

| メソッド | パス | 説明 |
|---|---|---|
| POST | `/ocr/process/async` | 非同期 OCR（Celery） |
| GET | `/tasks/{task_id}` | タスク状態確認 |
| GET | `/cache/stats` | キャッシュ統計 |
| DELETE | `/cache/{session_id}` | キャッシュクリア |
| POST | `/filters/keywords` | キーワードフィルタ設定 |
| GET | `/filters/keywords/{session_id}` | フィルタ取得 |
| GET | `/export/{session_id}` | JSON エクスポート |
| GET | `/sessions/{session_id}/stats` | セッション統計 |

### POST /ocr/process/async — リクエスト/レスポンス例

**リクエスト:**
```json
{
  "frame": "<base64エンコードされた PNG/JPEG>",
  "session_id": "uuid",
  "latitude": 35.6762,
  "longitude": 139.6503
}
```

**レスポンス 202:**
```json
{
  "task_id": "celery-task-uuid",
  "status": "queued",
  "message": "OCR task queued for processing"
}
```

---

## 6. データスキーマ

### users

| カラム | 型 | 制約 |
|---|---|---|
| id | UUID | PK |
| username | VARCHAR(100) | NOT NULL, UNIQUE |
| email | VARCHAR(255) | NOT NULL, UNIQUE |
| created_at | TIMESTAMPTZ | NOT NULL |

### sessions

| カラム | 型 | 制約 |
|---|---|---|
| id | UUID | PK |
| user_id | UUID | FK → users.id, nullable |
| title | VARCHAR(255) | NOT NULL |
| description | TEXT | nullable |
| status | VARCHAR(20) | default 'active' |
| started_at | TIMESTAMPTZ | NOT NULL |
| ended_at | TIMESTAMPTZ | nullable |
| created_at / updated_at | TIMESTAMPTZ | NOT NULL |

### extractions

| カラム | 型 | 制約 |
|---|---|---|
| id | UUID | PK |
| session_id | UUID | FK → sessions.id |
| content | TEXT | NOT NULL |
| confidence | FLOAT | NOT NULL |
| bounding_box | JSONB | nullable |
| latitude / longitude / altitude | FLOAT | nullable |
| timestamp | TIMESTAMPTZ | NOT NULL |
| engine | VARCHAR(50) | default 'paddleocr' |
| is_duplicate | BOOLEAN | default false |
| created_at | TIMESTAMPTZ | NOT NULL |

**インデックス:**
- `extractions(session_id)`
- `extractions(session_id, is_duplicate)`
- `sessions(status)`

---

## 7. 技術スタック

| カテゴリ | 選択技術 | バージョン |
|---|---|---|
| モバイルフレームワーク | React Native | 0.75.4 |
| モバイル言語 | TypeScript | 5.5.4 |
| カメラ | react-native-vision-camera | ^4.5.3 |
| バックエンドフレームワーク | FastAPI | 0.104.0 |
| OCR エンジン | PaddleOCR | 2.7.3 |
| OCR バックエンド | paddlepaddle（CPU） | 2.6.2 |
| タスクキュー | Celery | 5.3.4 |
| キャッシュ/ブローカー | Redis | 7 |
| データベース | PostgreSQL | 15 |
| ORM | SQLAlchemy | 2.0.23 |
| Android Gradle Plugin | AGP | 8.6.1 |
| Gradle | Gradle | 8.10.2 |
| Kotlin | Kotlin | 2.0.21 |
| コンテナ | Docker Compose | - |

---

## 8. Android ビルド設定

```groovy
// android/build.gradle
ext {
    buildToolsVersion = "35.0.0"
    minSdkVersion     = 26      // Vision Camera 要件
    compileSdkVersion = 35
    targetSdkVersion  = 35
    ndkVersion        = "27.1.12297006"
    kotlinVersion     = "2.0.21"
}
```

```properties
# android/gradle.properties
newArchEnabled=true    # New Architecture 有効
hermesEnabled=true
org.gradle.java.home=/opt/homebrew/opt/openjdk@17
```

---

## 9. 実装フェーズ

### Phase 1: MVP（完了）

- FastAPI 基本 API（同期 OCR）
- PostgreSQL + SQLAlchemy モデル
- PaddleOCR 統合
- React Native 骨格（CameraScreen, SessionList, Results）

### Phase 2: 最適化（完了）

- Celery 非同期 OCR 処理
- Redis キャッシュ・重複排除
- キーワードフィルタ
- セッション統計・エクスポート

### Phase 3: モバイル完成（完了）

- react-native-vision-camera v4 統合
- GPS 連携
- AsyncStorage オフライン対応
- Android / iOS ネイティブプロジェクト

---

## 10. デプロイ構成

### 本番環境（既存サービスとサブドメイン共存）

```
ネイティブ nginx（80/443）
├── example.com          → 既存サービス（変更なし）
└── api.example.com      → 127.0.0.1:8000 へプロキシ

Docker（SignReader 専用）
├── FastAPI       :8000（localhost のみ）
├── Celery Worker
├── Celery Beat
├── PostgreSQL
└── Redis
```

### デプロイコマンド

```bash
export SERVER_HOST=<VPS_IP>
./deploy.sh setup    # 初回のみ
./deploy.sh deploy   # 更新デプロイ
./deploy.sh status   # 状態確認
./deploy.sh rollback # ロールバック
```

---

## 11. 未解決事項と今後の課題

- **認証:** Phase 1/2 はオープンエンドポイント。JWT 認証は Phase 3 以降で追加予定
- **Google Vision フォールバック:** `USE_GOOGLE_VISION` フラグは実装済みだが未統合。PaddleOCR 信頼度が低い場合にフォールバックするプロバイダー抽象化を追加予定
- **地図表示:** ResultsScreen の地図ボタンは未実装（react-native-maps で抽出結果をプロット）
- **WebSocket:** ポーリング方式をリアルタイムストリーミングに置き換え
