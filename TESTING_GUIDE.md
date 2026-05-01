# SignReader テストガイド

## 概要

SignReaderはPythonバックエンドにpytest、React Nativeモバイルアプリにネストを使用しています。このガイドでは、テストの実行方法、結果の解釈、カバレッジ目標の設定、CI/CDとの統合方法を説明します。

---

## バックエンドテスト（pytest）

### 前提条件

```bash
cd backend
python3.10 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

テストスイートは `conftest.py` のオーバーライドにより**インメモリSQLite**データベースを使用するため、ユニット・統合テストの実行にPostgreSQLやRedisは不要です。Celeryタスクのテストはモック（提供済み）を使用します。

### 全テストの実行

```bash
cd backend
pytest
```

### カバレッジ付きで実行

```bash
pytest --cov=app tests/ --cov-report=term-missing
```

HTMLレポートを生成する場合:

```bash
pytest --cov=app tests/ --cov-report=html
open htmlcov/index.html
```

### 特定のテストファイルを実行

```bash
pytest tests/test_api.py -v
pytest tests/test_ocr_service.py -v
pytest tests/test_services.py -v
```

### 特定のテストを実行

```bash
pytest tests/test_api.py::test_health_endpoint -v
pytest tests/test_services.py::TestFilterService::test_is_duplicate_similar -v
```

### pytest設定

`pytest.ini` の内容:

```ini
[pytest]
testpaths = tests
asyncio_mode = auto
addopts = -v --tb=short
```

- `asyncio_mode = auto` — `async def test_*` 関数は自動的にイベントループで実行されます。
- `--tb=short` — 失敗時のトレースバックを簡潔に表示します。

### テストファイル構成

| ファイル | テスト対象 |
|---|---|
| `tests/conftest.py` | 共有フィクスチャ: TestClient、DB、サンプルデータ、モック |
| `tests/test_api.py` | FastAPI TestClientを通じたHTTPエンドポイント（17件） |
| `tests/test_ocr_service.py` | OCRServiceユニットテスト（9件） |
| `tests/test_services.py` | CacheService + FilterServiceユニットテスト（15件） |

### フィクスチャ一覧

| フィクスチャ | スコープ | 説明 |
|---|---|---|
| `client` | function | SQLite DBを使用したFastAPI TestClient |
| `sample_user` | function | テストDBのUserレコード |
| `sample_session` | function | テストDBのSessionレコード |
| `sample_image_b64` | session | 100×100の白いPNGをbase64エンコードした文字列 |
| `mock_ocr_service` | function | 固定のOCRResponseを返すMagicMock |
| `mock_redis` | function | CacheServiceのRedisクライアント用MagicMock |

### カバレッジ目標

| モジュール | 目標 |
|---|---|
| `app/main.py` | ≥ 90% |
| `app/main_optimized.py` | ≥ 85% |
| `app/services/ocr_service.py` | ≥ 85% |
| `app/services/cache_service.py` | ≥ 90% |
| `app/services/filter_service.py` | ≥ 90% |
| `app/models.py` | ≥ 95% |
| `app/schemas.py` | ≥ 95% |
| **全体** | **≥ 88%** |

### バックエンドテストケース一覧

#### test_api.py（17件）

1. `test_health_endpoint` — GET /health が正しいスキーマで200を返す
2. `test_health_response_structure` — status、version、ocr_engineキーを確認
3. `test_create_session_success` — POST /sessions に正しいボディで201が返る
4. `test_create_session_missing_title` — POST /sessions でtitleなしの場合422が返る
5. `test_get_session_found` — GET /sessions/{id} で既存セッションが200で返る
6. `test_get_session_not_found` — GET /sessions/{id} で不明なIDの場合404が返る
7. `test_ocr_process_valid_frame` — POST /ocr/process に有効なbase64でOCRResponseが返る
8. `test_ocr_process_missing_session_id` — POST /ocr/process でsession_idなしの場合422が返る
9. `test_ocr_process_missing_frame` — POST /ocr/process でframeなしの場合422が返る
10. `test_ocr_process_async_returns_task_id` — POST /ocr/process/async がtask_idを返す
11. `test_ocr_process_async_task_structure` — タスクレスポンスにid、status、messageが含まれる
12. `test_save_extraction_success` — POST /extract/save がidと共に201を返す
13. `test_save_extraction_confidence_out_of_range` — confidence > 1.0 の場合422が返る
14. `test_get_extractions_returns_list` — GET /extract/{session_id} が配列を返す
15. `test_get_extractions_empty` — GET /extract/{session_id} が新規セッションで[]を返す
16. `test_cache_stats_structure` — GET /cache/stats が hit_rate、total_keys、memory_usage_mbを返す
17. `test_delete_cache_success` — DELETE /cache/{session_id} が成功レスポンスを返す

#### test_ocr_service.py（9件）

1. `test_ocr_service_initializes` — OCRServiceをインスタンス化できる
2. `test_decode_frame_valid_base64` — 有効なPNG base64 → numpy配列
3. `test_decode_frame_invalid_base64` — 無効な文字列はValueErrorを発生させる
4. `test_preprocess_image_resizes_large` — 幅1280px超の画像は縮小される
5. `test_preprocess_image_leaves_small` — 幅1280px以下の画像はそのまま
6. `test_extract_text_filters_low_confidence` — min_confidence未満の結果は除外される
7. `test_parse_paddle_result` — PaddleOCRの出力形式が正しくパースされる
8. `test_process_frame_returns_ocr_response` — パイプライン全体がタイミング付きのOCRResponseを返す
9. `test_process_frame_empty_image` — 白紙画像は空のtextリストを返す

#### test_services.py（15件）

1. `test_cache_set_and_get_session` — set_session / get_session の往復確認
2. `test_cache_delete_session` — delete_sessionがキーを削除する
3. `test_cache_exists_true` — 設定済みキーでexistsがTrueを返す
4. `test_cache_exists_false` — 存在しないキーでexistsがFalseを返す
5. `test_cache_get_stats_shape` — get_statsがCacheStatsを返す
6. `test_filter_is_duplicate_similar` — SequenceMatcher ≥ 0.85 → True
7. `test_filter_is_duplicate_different` — 類似していないテキスト → False
8. `test_filter_add_to_seen` — add_to_seenがcache.add_textを呼び出す
9. `test_filter_set_and_get_keywords` — set_keywords / get_keywords の往復確認
10. `test_filter_matches_include_passes` — 包含モードでキーワードが存在する場合 → True
11. `test_filter_matches_include_blocks` — 包含モードでキーワードが存在しない場合 → False
12. `test_filter_matches_exclude_blocks` — 除外モードでキーワードが存在する場合 → False
13. `test_filter_results_removes_duplicates` — 重複テキストが出力から除去される
14. `test_filter_results_applies_keyword_filter` — マッチしないテキストが除去される
15. `test_filter_results_empty_list` — 空のリスト入力は空のリストを返す

---

## モバイルテスト（Jest）

### 前提条件

```bash
cd mobile
npm install
```

### 全テストの実行

```bash
npm test
```

### カバレッジ付きで実行

```bash
npm run test:coverage
```

### ウォッチモードで実行

```bash
npm test -- --watch
```

### 特定のファイルを実行

```bash
npm test -- src/__tests__/services/api.test.ts
npm test -- src/__tests__/services/storage.test.ts
```

### Jest設定

`jest.config.js` は `react-native` プリセットを使用し、`babel-jest` でTypeScriptを変換します。`jest.setup.js` は以下のモックを提供します:

- `@react-native-async-storage/async-storage`
- `axios`
- `react-native-camera`
- `@react-native-community/geolocation`

### カバレッジ目標

| モジュール | 目標 |
|---|---|
| `src/services/api.ts` | ≥ 90% |
| `src/services/storage.ts` | ≥ 90% |
| `src/services/camera.ts` | ≥ 80% |
| `src/context/AppContext.tsx` | ≥ 85% |
| `src/screens/*.tsx` | ≥ 75% |
| **全体** | **≥ 85%** |

### モバイルテストケース一覧

#### api.test.ts（8件）

1. `healthCheck returns ok status` — axios GET /health がモックレスポンスを返す
2. `createSession success` — POST /sessions がセッションオブジェクトを返す
3. `createSession network error throws` — axiosエラーが伝播される
4. `processOCRAsync returns task_id` — POST /ocr/process/async がタスクを返す
5. `getTaskStatus returns status` — GET /tasks/{id} がタスクステータスを返す
6. `saveExtraction success` — POST /extract/save が抽出結果を返す
7. `getExtractions returns array` — GET /extract/{id} がリストを返す
8. `setFilterKeywords succeeds` — POST /filters/keywords がエラーなく完了する

#### storage.test.ts（13件）

1. `saveSession stores correctly` — AsyncStorage.setItemがシリアライズされたセッションで呼ばれる
2. `getSession retrieves correctly` — AsyncStorage.getItemがデシリアライズされたセッションを返す
3. `getSession returns null when not found` — 存在しないキーはnullを返す
4. `getAllSessions returns all` — 複数のセッションが取得・パースされる
5. `deleteSession removes session and extractions` — セッションと抽出結果のキーが削除される
6. `saveExtraction stores correctly` — 抽出結果がセッションのリストに追加される
7. `getExtractions retrieves by session_id` — 正しい抽出結果リストが返される
8. `getExtractions returns empty array when none` — 存在しないキーは[]を返す
9. `clearSessionExtractions clears correctly` — 抽出結果キーが削除される
10. `setCurrentSessionId / getCurrentSessionId round-trip` — setしたものがgetで返る
11. `getAllSessions returns empty array when storage empty` — AsyncStorageの値がnullの場合→[]
12. `saveExtraction appends to existing` — 2件目の抽出結果がリストに追加される
13. `deleteSession with no extractions completes without error` — 抽出結果がない場合も正常完了

---

## CI/CD 統合

### GitHub Actions 設定例

```yaml
name: CI

on:
  push:
    branches: [main, master]
  pull_request:
    branches: [main, master]

jobs:
  backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Pythonのセットアップ
        uses: actions/setup-python@v5
        with:
          python-version: "3.10"
      - name: 依存パッケージのインストール
        working-directory: backend
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
      - name: カバレッジ付きテスト実行
        working-directory: backend
        run: pytest --cov=app tests/ --cov-report=xml --cov-fail-under=88
      - name: カバレッジのアップロード
        uses: codecov/codecov-action@v4
        with:
          files: backend/coverage.xml

  mobile:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Nodeのセットアップ
        uses: actions/setup-node@v4
        with:
          node-version: "18"
          cache: "npm"
          cache-dependency-path: mobile/package-lock.json
      - name: 依存パッケージのインストール
        working-directory: mobile
        run: npm ci
      - name: カバレッジ付きテスト実行
        working-directory: mobile
        run: npm run test:coverage -- --coverageReporters=lcov
      - name: カバレッジのアップロード
        uses: codecov/codecov-action@v4
        with:
          files: mobile/coverage/lcov.info
```

### pre-commitフック

`.git/hooks/pre-commit` に追加:

```bash
#!/bin/bash
set -e

echo "バックエンドテストを実行中..."
cd backend
source venv/bin/activate
pytest tests/ -q --tb=short
cd ..

echo "モバイルテストを実行中..."
cd mobile
npm test -- --passWithNoTests --watchAll=false
cd ..
```

### カバレッジバッジ

Codecovのセットアップ後にREADMEへ追加:

```markdown
![バックエンドカバレッジ](https://codecov.io/gh/your-org/SignReader/branch/main/graph/badge.svg?flag=backend)
![モバイルカバレッジ](https://codecov.io/gh/your-org/SignReader/branch/main/graph/badge.svg?flag=mobile)
```
