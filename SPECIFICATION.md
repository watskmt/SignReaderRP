# SignReader — 技術仕様書

**バージョン:** 1.0
**日付:** 2026-05-01
**作成者:** SignReader エンジニアリングチーム

---

## 1. 概要とユースケース

SignReaderは、ライブカメラ映像から看板を読み取り、抽出したテキストをGPS座標と共に記録するスマートフォンアプリケーションです。基本的な処理フローは「ユーザーが看板にスマートフォンを向ける → アプリがビデオフレームを取得 → バックエンドがOCR処理 → 重複排除した結果を保存・表示」です。

### 主なユースケース

| ユースケース | 説明 |
|---|---|
| フィールド調査 | 研究者がルートを歩きながら、全ての看板を位置情報付きで記録 |
| ルート記録 | 地図データベース用に走行中の道路標識を記録 |
| アクセシビリティ | 視覚障害者向けのリアルタイム看板読み上げ |
| 小売り監査 | 複数店舗の価格・販促看板を大規模に収集 |
| 旅行記録 | 旅行中に出会った全看板の自動ジャーナル |

### スコープ外（v1）

- 手書き文字認識
- PaddleOCRのデフォルト以外の非ラテン文字・非CJK文字対応
- リアルタイム音声出力（スクリーンリーダー連携は将来フェーズ）
- デバイス間のクラウド同期

---

## 2. システムアーキテクチャ

```
┌─────────────────────────────────────────────────────┐
│                   モバイルクライアント                  │
│  React Native + TypeScript                           │
│  ┌──────────┐  ┌────────────┐  ┌────────────────┐  │
│  │ カメラ   │  │ GPS        │  │ AsyncStorage   │  │
│  │ サービス │  │ サービス   │  │ （ローカル）   │  │
│  └────┬─────┘  └─────┬──────┘  └───────┬────────┘  │
│       │               │                  │           │
│       └──────────┬────┘                  │           │
│                  │ HTTP/JSON             │           │
└──────────────────┼───────────────────────┘
                   │ Axios（base64フレーム）
┌──────────────────▼───────────────────────────────────┐
│                   FastAPI バックエンド                 │
│  ┌──────────────────────────────────────────────┐   │
│  │              REST API レイヤー               │   │
│  │  /health  /sessions  /ocr  /extract /filters │   │
│  └──────────────────┬───────────────────────────┘   │
│                     │                                │
│  ┌──────────────────▼───────────────────────────┐   │
│  │              サービスレイヤー                │   │
│  │  OCRService  CacheService  FilterService     │   │
│  └──────┬────────────┬──────────────┬───────────┘   │
│         │            │              │                │
│  ┌──────▼──┐  ┌──────▼──┐  ┌───────▼────────┐      │
│  │PaddleOCR│  │  Redis   │  │  Celery Worker │      │
│  │  (CPU)  │  │  Cache   │  │  (非同期タスク) │      │
│  └─────────┘  └─────────┘  └────────────────┘      │
└──────────────────────┬───────────────────────────────┘
                       │ SQLAlchemy
┌──────────────────────▼───────────────────────────────┐
│               PostgreSQL 15                          │
│   users  |  sessions  |  extractions                 │
└──────────────────────────────────────────────────────┘
```

### コンポーネントの責務

**モバイルクライアント**
- 設定可能な間隔（デフォルト500ms）でフレームを取得
- 有効時にGPS座標を収集
- フレームをbase64でバックエンドへ送信
- カメラビュー上にオーバーレイで結果を表示
- AsyncStorageを通じてセッションと抽出データをローカル保存

**FastAPI バックエンド**
- 受信フレームのバリデーションとデコード
- OCRサービスへのルーティング（Phase 1: 同期、Phase 2: Celery非同期）
- 重複排除とキーワードフィルタの適用
- PostgreSQLへの抽出結果の保存
- セッション管理とエクスポートエンドポイントの提供

**OCRサービス（PaddleOCR）**
- base64 → numpy配列のデコード
- 前処理：最大幅1280pxへのリサイズ、グレースケール強調
- PaddleOCR推論の実行
- 信頼度スコア付きのTextResultリストを返却

**キャッシュサービス（Redis）**
- セッションごとの最近見たテキストをキャッシュ（TTL: 1時間）
- セッションメタデータをキャッシュ（TTL: 5分）
- キャッシュ統計エンドポイントの提供

**フィルタサービス**
- difflib.SequenceMatcherによるファジー重複排除（閾値0.85）
- セッション単位のキーワード包含/除外フィルタ

---

## 3. 機能要件

### 3.1 リアルタイムOCR

- FR-01: システムはbase64エンコードされた画像フレームを受け取り、300ms以内（p95）にテキストを返すこと。
- FR-02: 同期OCR（Phase 1）と非同期Celeryベースのバッチ処理（Phase 2）の両方をサポートすること。
- FR-03: OCRは設定可能な信頼度閾値（デフォルト0.6）以下の結果をフィルタリングすること。
- FR-04: 検出した各テキスト領域のバウンディングボックス座標を返すこと。

### 3.2 GPS記録

- FR-05: 各OCRリクエストに対して緯度・経度・高度をオプションとして受け付けること。
- FR-06: GPS座標は各抽出レコードと共に保存すること。
- FR-07: モバイルクライアントはGPS記録を有効にする前に位置情報の許可を要求すること。

### 3.3 重複排除とフィルタ

- FR-08: ファジーマッチング（類似度85%以上）で類似テキストを検出すること。
- FR-09: 重複した抽出結果は履歴保持のため削除せず `is_duplicate=true` でマークすること。
- FR-10: ユーザーはセッション単位でキーワード包含/除外フィルタを設定できること。
- FR-11: キーワードフィルタはRedisに保存し、抽出結果の保存前に適用すること。

### 3.4 セッション管理

- FR-12: ユーザーは名前付きセッションを作成できること。
- FR-13: セッションはactive（進行中）・completed（完了）・archived（アーカイブ）のステータスを持つこと。
- FR-14: セッションの全抽出結果をJSONでエクスポートできること。
- FR-15: Celery定期タスクで30日以上前のセッションを自動アーカイブすること。

---

## 4. 非機能要件

### 4.1 パフォーマンス

- NFR-01: OCRエンドポイントのp95レイテンシ ≤ 300ms（CPU推論、入力1280×720）
- NFR-02: APIは10件の同時OCRリクエストをキュー飢餓なしで処理できること。
- NFR-03: Redisキャッシュヒットによりレイテンシを50ms以上削減すること。
- NFR-04: 適切なインデックスを持つPostgreSQLクエリは通常負荷で20ms以内に完了すること。

### 4.2 精度

- NFR-05: 鮮明に印刷された看板に対するPaddleOCRのテキスト抽出精度は85%を超えること。
- NFR-06: 重複排除の偽陽性率（ユニークなテキストが誤って重複判定される割合）は5%未満であること。

### 4.3 プライバシー

- NFR-07: GPS情報はオプションかつユーザー制御とし、明示的な許可なく収集しないこと。
- NFR-08: 本番環境での全API通信はHTTPSを使用すること。
- NFR-09: シークレット情報（DBパスワード、APIキー）はバージョン管理にコミットしないこと。
- NFR-10: ユーザーデータは要請に応じて削除可能であること（GDPR第17条）。

### 4.4 信頼性

- NFR-11: Celery OCRタスクは失敗時に2秒バックオフで最大3回自動リトライすること。
- NFR-12: APIは全4xx/5xxエラーに対して構造化されたエラーレスポンスを返すこと。
- NFR-13: モバイルアプリはバックエンドが利用不可の場合にローカルストレージへフォールバックすること。

### 4.5 バッテリーとモバイル

- NFR-14: フレーム取得間隔は設定可能とすること（最小200ms、デフォルト500ms）。
- NFR-15: 本番環境のGPSポーリングは significant-location-change モードを使用してバッテリー消費を最小化すること。

---

## 5. FastAPI エンドポイント仕様

### 5.1 GET /health

**目的:** 死活監視

**レスポンス 200:**
```json
{
  "status": "ok",
  "version": "0.1.0",
  "ocr_engine": "paddleocr"
}
```

### 5.2 POST /sessions

**目的:** 新しい撮影セッションを作成する

**リクエストボディ:**
```json
{
  "title": "渋谷調査 2026-05-01",
  "description": "オプションの説明",
  "user_id": "uuid文字列"
}
```

**レスポンス 201:**
```json
{
  "id": "uuid",
  "title": "渋谷調査 2026-05-01",
  "description": "オプションの説明",
  "status": "active",
  "started_at": "2026-05-01T10:00:00Z",
  "ended_at": null,
  "created_at": "2026-05-01T10:00:00Z",
  "updated_at": "2026-05-01T10:00:00Z"
}
```

### 5.3 POST /ocr/process

**目的:** 単一フレームの同期OCR処理

**リクエストボディ:**
```json
{
  "frame": "<base64エンコードされたPNG/JPEG>",
  "session_id": "uuid",
  "latitude": 35.6762,
  "longitude": 139.6503
}
```

**レスポンス 200:**
```json
{
  "status": "success",
  "texts": [
    {
      "content": "STOP",
      "confidence": 0.98,
      "bounding_box": [[10, 20], [100, 20], [100, 50], [10, 50]]
    }
  ],
  "processing_time_ms": 145,
  "engine": "paddleocr"
}
```

### 5.4 POST /extract/save

**目的:** 抽出結果を1件保存する

**リクエストボディ:**
```json
{
  "session_id": "uuid",
  "content": "STOP",
  "confidence": 0.98,
  "bounding_box": [[10, 20], [100, 20], [100, 50], [10, 50]],
  "latitude": 35.6762,
  "longitude": 139.6503,
  "altitude": 12.5,
  "engine": "paddleocr"
}
```

**レスポンス 201:** `id`、`is_duplicate`、`created_at` を含むExtractionResponse

### 5.5 GET /extract/{session_id}

**目的:** セッションの全抽出結果一覧を取得する

**レスポンス 200:** ExtractionResponseオブジェクトの配列

---

## 6. データスキーマ

### 6.1 users（ユーザー）

| カラム | 型 | 制約 |
|---|---|---|
| id | UUID | PK, デフォルト gen_random_uuid() |
| username | VARCHAR(100) | NOT NULL, UNIQUE |
| email | VARCHAR(255) | NOT NULL, UNIQUE |
| created_at | TIMESTAMPTZ | NOT NULL, デフォルト now() |

### 6.2 sessions（セッション）

| カラム | 型 | 制約 |
|---|---|---|
| id | UUID | PK, デフォルト gen_random_uuid() |
| user_id | UUID | FK → users.id, nullable |
| title | VARCHAR(255) | NOT NULL |
| description | TEXT | nullable |
| status | VARCHAR(20) | NOT NULL, デフォルト 'active' |
| started_at | TIMESTAMPTZ | NOT NULL, デフォルト now() |
| ended_at | TIMESTAMPTZ | nullable |
| created_at | TIMESTAMPTZ | NOT NULL, デフォルト now() |
| updated_at | TIMESTAMPTZ | NOT NULL, デフォルト now() |

### 6.3 extractions（抽出結果）

| カラム | 型 | 制約 |
|---|---|---|
| id | UUID | PK, デフォルト gen_random_uuid() |
| session_id | UUID | FK → sessions.id, NOT NULL |
| content | TEXT | NOT NULL |
| confidence | FLOAT | NOT NULL |
| bounding_box | JSONB | nullable |
| latitude | FLOAT | nullable |
| longitude | FLOAT | nullable |
| altitude | FLOAT | nullable |
| timestamp | TIMESTAMPTZ | NOT NULL, デフォルト now() |
| engine | VARCHAR(50) | NOT NULL, デフォルト 'paddleocr' |
| is_duplicate | BOOLEAN | NOT NULL, デフォルト false |
| created_at | TIMESTAMPTZ | NOT NULL, デフォルト now() |

**インデックス:**
- `extractions(session_id)` — 主要な検索パターン
- `extractions(session_id, is_duplicate)` — 重複除外フィルタ
- `sessions(status)` — アクティブセッションの一覧取得

---

## 7. 技術スタック

| カテゴリ | 選択技術 | 選定理由 |
|---|---|---|
| モバイルフレームワーク | React Native 0.73 | 単一コードベースでiOS + Androidのクロスプラットフォーム対応 |
| モバイル言語 | TypeScript | 型安全性、IDEサポート |
| バックエンドフレームワーク | FastAPI 0.104 | 非同期Python、OpenAPIドキュメント自動生成、Pydantic連携 |
| OCRエンジン | PaddleOCR 2.7 | 高精度、オフラインCPU推論、CJK対応 |
| タスクキュー | Celery 5.3 | 成熟したPythonタスクキュー、リトライ機能、Flower UI |
| キャッシュ/ブローカー | Redis 7 | サブミリ秒のレイテンシ、pub/sub、Celeryブローカー |
| データベース | PostgreSQL 15 | バウンディングボックス用JSONB、UUIDサポート、高信頼性 |
| ORM | SQLAlchemy 2.0 | 非同期サポート、Alembicマイグレーション |
| コンテナ化 | Docker Compose | 再現可能なローカル開発環境 |
| テスト（バックエンド） | pytest + pytest-asyncio | 非同期テストサポート、フィクスチャ、カバレッジ計測 |
| テスト（フロントエンド） | Jest + Testing Library | コンポーネントテスト、モックサポート |

---

## 8. 実装計画

### Phase 1: MVP（4〜6週間）

**目標:** 同期OCRを持つ動作するバックエンド、モバイルの骨格、エンドツーエンドのデータフロー

**第1〜2週: バックエンド基盤**
- プロジェクトの雛形作成、Docker Compose、仮想環境
- PostgreSQLモデル + Alembicマイグレーション
- Pydanticスキーマ、設定、DBセッション管理
- 基本CRUDエンドポイント: /health, /sessions, /extract

**第3〜4週: OCR統合**
- PaddleOCRラッパーとなるOCRService
- 画像前処理パイプライン（リサイズ、グレースケール強調）
- POST /ocr/process 同期エンドポイント
- 信頼度フィルタとTextResultパース

**第5〜6週: モバイル骨格**
- React Nativeプロジェクトセットアップ
- フレーム取得機能付きCameraScreen
- APIクライアント（axios）
- セッション作成と抽出結果の表示
- 基本的なナビゲーション

**成果物:** ユーザーがスマートフォンを看板に向けるとアプリ上に抽出テキストが表示される

### Phase 2: 最適化（2〜3週間）

**目標:** 非同期処理・キャッシュ・重複排除によるプロダクション品質のパフォーマンス

**第7〜8週: 非同期処理 + キャッシュ**
- Celeryワーカーのセットアップ
- POST /ocr/process/async + GET /tasks/{task_id}
- Redis CacheService: セッションキャッシュ、既出テキストキャッシュ
- Celeryタスク: process_ocr_frame, save_extractions_batch

**第9週: フィルタ + エクスポート**
- FilterService: ファジー重複排除、キーワード包含/除外
- POST /filters/keywords, GET /filters/keywords/{session_id}
- GET /export/{session_id}
- GET /sessions/{session_id}/stats
- Celery定期タスク: cleanup_old_sessions

**成果物:** バックエンドが10並行ストリームを処理でき、重複が抑制され、セッションをエクスポートできる

### Phase 3: モバイル完成（4〜6週間）

**目標:** GPS・結果画面・オフライン対応を含むプロダクション品質のモバイルアプリ

**第10〜11週: GPS + 権限**
- 位置情報権限フロー
- GPS座標の取得と表示
- カメラ権限の処理

**第12〜13週: 結果表示とセッション管理**
- SessionListScreen: プルリフレッシュ、セッション作成モーダル
- ResultsScreen: 時刻別グルーピング、信頼度バッジ、キーワードフィルタ入力
- LocalStorageService: AsyncStorageによるオフラインファースト実装

**第14〜15週: 仕上げ**
- ResultsScreenのエクスポートボタン
- エラーハンドリングとローディング状態
- パフォーマンスチューニング（フレームスキップ、コネクションプーリング）
- アプリアイコン、スプラッシュ画面、ストアメタデータ

**成果物:** TestFlight / Google Play Store内部テスト提出準備完了のアプリ

---

## 9. 実装上の注意点

### パフォーマンス

- PaddleOCRモデルは起動時に一度だけロードします（OCRServiceのレイジーシングルトン）。リクエストごとの初期化オーバーヘッド（約3秒のコールドスタート）を避けるためです。
- Redisキャッシュはセッションごとに既出テキストをSetとして保存します。重複チェックはSetの全メンバーに対してO(n)で行われ、1セッションあたり約10,000件まで許容できます。
- SQLAlchemyのコネクションプール: 本番環境では `pool_size=10, max_overflow=20` を設定してください。
- Celeryの並行数は `min(cpu_count, 4)` に設定し、複数のPaddleOCRインスタンスによるRAM枯渇を避けてください。

### セキュリティ

- SECRET_KEYは本番デプロイ前に必ずローテーションしてください（最低32バイトのランダム値）。
- ユーザーが送信した画像データはメモリ内でのみ処理し、フレームをディスクに保存しないこと。
- 本番環境ではデータベース認証情報をデフォルトからローテーションすること。
- DoS対策として /ocr/process にレート制限を検討してください（slowapi または nginxのレート制限）。

### バッテリー最適化（モバイル）

- デフォルトのフレーム取得間隔は500ms。ユーザーは間隔を延ばしてCPU・通信の使用を削減できます。
- GPSは `@react-native-community/geolocation` の `watchPosition` に `distanceFilter: 10`（メートル）を設定してポーリング頻度を削減します。
- アプリがバックグラウンドに移行した際はフレーム取得を必ず停止し、バックグラウンドカメラアクセスを避けること。

### デプロイチェックリスト

- [ ] SECRET_KEY、DBパスワード、Redisパスワードのローテーション
- [ ] HTTPSの有効化（nginx/ロードバランサーでTLS終端）
- [ ] `API_DEBUG=false` に設定
- [ ] Celeryの並行数を設定
- [ ] AlembicマイグレーションのCIステップを設定
- [ ] ログ収集の設定（CloudWatch / Datadog）
- [ ] `CORS` の許可オリジンをモバイルアプリのバンドルIDに限定

---

## 10. エラーハンドリング

全APIエラーは統一された形式のJSONを返します:

```json
{
  "detail": "人間が読めるエラーメッセージ",
  "code": "ERROR_CODE",
  "field": "バリデーションエラーの場合はフィールド名"
}
```

| HTTPステータス | 意味 |
|---|---|
| 400 | 不正なリクエスト（無効なbase64、不正なリクエストボディ） |
| 404 | セッションまたは抽出結果が見つからない |
| 422 | Pydanticバリデーションエラー |
| 500 | 内部サーバーエラー（OCR失敗、DB利用不可） |
| 503 | サービス利用不可（Celeryキューが満杯） |

---

## 11. 未解決事項と今後の課題

- **認証:** Phase 1はオープンエンドポイントを使用。Phase 2ではuser_idバインディングを含むJWTベース認証を追加すること。
- **モデル選択:** PaddleOCRの `lang='japan'` は日本語と英語に対応。言語自動検出ステップを追加することで多言語精度が向上します。
- **Google Visionフォールバック:** `USE_GOOGLE_VISION` 設定フラグは実装済みですが、Phase 1では統合されていません。Phase 2ではPaddleOCRの信頼度が閾値を下回る場合にGoogle Visionにフォールバックするプロバイダー抽象化を追加すること。
- **リアルタイムストリーミング:** WebSocketエンドポイントを使えばモバイルクライアントのポーリングオーバーヘッドを排除できます。
- **地図表示:** ResultsScreenには地図ボタンのプレースホルダーがあります。react-native-mapsを使って抽出結果を地図上にプロットする機能はPhase 3のストレッチゴールです。
