# SignReader テストガイド

## テスト結果サマリー

| スイート | テスト数 | 状態 |
|---|---|---|
| backend/tests/test_api.py | 17 件 | 全件パス |
| backend/tests/test_ocr_service.py | 9 件 | 全件パス |
| backend/tests/test_services.py | 16 件 | 全件パス |
| mobile/src/__tests__/services/api.test.ts | 8 件 | 全件パス |
| mobile/src/__tests__/services/storage.test.ts | 13 件 | 全件パス |
| **合計** | **63 件** | **全件パス** |

---

## バックエンドテスト（pytest）

### 前提条件

```bash
cd backend
python3.10 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

テストは **インメモリ SQLite** を使用するため PostgreSQL / Redis の起動は不要です。

### 実行コマンド

```bash
# 全テスト
pytest

# カバレッジ付き
pytest --cov=app tests/ --cov-report=term-missing

# HTML カバレッジレポート
pytest --cov=app tests/ --cov-report=html
open htmlcov/index.html

# 特定ファイル
pytest tests/test_api.py -v
pytest tests/test_ocr_service.py -v
pytest tests/test_services.py -v
```

### pytest 設定（pytest.ini）

```ini
[pytest]
testpaths = tests
asyncio_mode = auto
addopts = -v --tb=short
```

### テスト分離の仕組み

| 依存 | テスト時の対処 |
|---|---|
| PostgreSQL | SQLite インメモリ DB（conftest.py で override） |
| Redis | MagicMock（CacheService の Redis クライアントをモック） |
| PaddleOCR | MagicMock（モデルダウンロードを回避） |
| Celery | `process_ocr_frame.delay` をモック |

> **重要:** `app.main.get_ocr_service` や `app.main_optimized.get_cache_service` のモックは `patch()` ではなく `app.dependency_overrides` を使用します（FastAPI の `Depends` は `patch` では差し替えできないため）。

### テストケース一覧

#### test_api.py（17 件）

| # | テスト名 | 内容 |
|---|---|---|
| 1 | test_health_endpoint | GET /health → 200 |
| 2 | test_health_response_structure | status/version/ocr_engine キー確認 |
| 3 | test_create_session_success | POST /sessions → 201 |
| 4 | test_create_session_missing_title | title なし → 422 |
| 5 | test_get_session_found | GET /sessions/{id} → 200 |
| 6 | test_get_session_not_found | 不明 ID → 404 |
| 7 | test_ocr_process_valid_frame | OCR エンドポイント正常系 |
| 8 | test_ocr_process_missing_session_id | session_id なし → 422 |
| 9 | test_ocr_process_missing_frame | frame なし → 422 |
| 10 | test_ocr_process_async_returns_task_id | /ocr/process/async → task_id |
| 11 | test_ocr_process_async_task_structure | task レスポンス構造確認 |
| 12 | test_save_extraction_success | POST /extract/save → 201 |
| 13 | test_save_extraction_confidence_out_of_range | confidence > 1.0 → 422 |
| 14 | test_get_extractions_returns_list | GET /extract/{id} → 配列 |
| 15 | test_get_extractions_empty | 新規セッション → [] |
| 16 | test_cache_stats_structure | GET /cache/stats → 正常 |
| 17 | test_delete_cache_success | DELETE /cache/{id} → 200 |

#### test_ocr_service.py（9 件）

| # | テスト名 | 内容 |
|---|---|---|
| 1 | test_ocr_service_initializes | インスタンス化できる |
| 2 | test_decode_frame_valid_base64 | base64 → numpy 配列 |
| 3 | test_decode_frame_invalid_base64 | 無効文字列 → ValueError |
| 4 | test_preprocess_image_resizes_large | 1280px 超 → 縮小 |
| 5 | test_preprocess_image_leaves_small | 1280px 以下 → 変更なし |
| 6 | test_extract_text_filters_low_confidence | 低信頼度 → 除外 |
| 7 | test_parse_paddle_result | PaddleOCR 出力のパース |
| 8 | test_process_frame_returns_ocr_response | タイミング付きレスポンス |
| 9 | test_process_frame_empty_image | 白紙 → texts: [] |

#### test_services.py（16 件）

| # | テスト名 | 内容 |
|---|---|---|
| 1–5 | TestCacheService | Redis CRUD・統計・存在確認 |
| 6–16 | TestFilterService | 重複検出・キーワードフィルタ・統合テスト |

---

## モバイルテスト（Jest）

### 前提条件

```bash
cd mobile
npm install
```

### 実行コマンド

```bash
# 全テスト
npm test

# カバレッジ付き
npm run test:coverage

# ウォッチモード
npm test -- --watch

# 特定ファイル
npm test -- src/__tests__/services/api.test.ts
```

### Jest 設定

```js
// jest.config.js
module.exports = {
  preset: 'react-native',
  setupFilesAfterEnv: ['./jest.setup.js'],
  transformIgnorePatterns: [
    'node_modules/(?!(react-native|@react-native|@react-navigation|...|)/)',
  ],
};
```

**jest.setup.js のモック:**

| モジュール | 内容 |
|---|---|
| `@react-native-async-storage/async-storage` | `getItem` / `setItem` / `removeItem` の純粋モック |
| `axios` | 全メソッドを `jest.fn()` に置き換え |
| `react-native-vision-camera` | `Camera` / `useCameraDevice` / `useCameraPermission` をモック |
| `@react-native-community/geolocation` | 固定座標（東京）を返すモック |

> **beforeEach で `jest.resetAllMocks()` を使用:** `clearAllMocks()` は `mockResolvedValueOnce` キューをクリアしないためテスト間でモック値が汚染されます。`resetAllMocks()` + デフォルト値の再設定パターンを採用しています。

### テストケース一覧

#### api.test.ts（8 件）

| # | テスト名 |
|---|---|
| 1 | healthCheck → ok レスポンス |
| 2 | createSession 成功 |
| 3 | createSession ネットワークエラー |
| 4 | processOCRAsync → task_id |
| 5 | getTaskStatus → status |
| 6 | saveExtraction 成功 |
| 7 | getExtractions → 配列 |
| 8 | setFilterKeywords 成功 |

#### storage.test.ts（13 件）

| # | テスト名 |
|---|---|
| 1–4 | セッション CRUD |
| 5–6 | deleteSession（抽出結果も削除） |
| 7–10 | 抽出結果 CRUD |
| 11 | clearSessionExtractions |
| 12–13 | currentSessionId の読み書き |

---

## CI/CD 統合

### GitHub Actions 設定例

```yaml
name: CI

on: [push, pull_request]

jobs:
  backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.10" }
      - run: pip install -r requirements.txt
        working-directory: backend
      - run: pytest --cov=app tests/ --cov-fail-under=85
        working-directory: backend

  mobile:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "18" }
      - run: npm ci
        working-directory: mobile
      - run: npm test
        working-directory: mobile
```

### pre-commit フック

```bash
#!/bin/bash
set -e
cd backend && source venv/bin/activate && pytest tests/ -q --tb=short
cd ../mobile && npm test -- --watchAll=false --passWithNoTests
```
