# SignReader バックエンド — Phase 2 ガイド（Redis + Celery）

Phase 2 では Celery による非同期 OCR 処理、Redis キャッシュ、キーワードフィルタ、セッション統計を使用します。`app/main_optimized.py` を使用してください。

## 起動手順

### 1. 前提確認

```bash
docker-compose ps   # postgres + redis が healthy であること
```

### 2. Phase 2 API の起動

```bash
uvicorn app.main_optimized:app --reload --host 0.0.0.0 --port 8000
```

起動確認:
```bash
curl http://localhost:8000/health
# → {"status":"ok","version":"0.2.0","async_processing":true}
```

### 3. Celery ワーカーの起動（別ターミナル）

```bash
source venv/bin/activate
celery -A app.tasks.celery_app worker --loglevel=info --concurrency=2
```

### 4. Celery Beat（定期タスク、別ターミナル）

```bash
celery -A app.tasks.celery_app beat --loglevel=info
```

毎日 UTC 02:00 に `cleanup_old_sessions` が実行されます。

### 5. Flower（タスク監視 UI）

```bash
pip install flower
celery -A app.tasks.celery_app flower --port=5555
```

http://localhost:5555 でタスク状態を確認できます。

---

## 非同期 OCR フロー

```
モバイルアプリ
    │
    ▼ POST /ocr/process/async
FastAPI → Celery キューに登録
    ↓
    └─ {"task_id": "...", "status": "queued"} を即座に返す

モバイルアプリ（500ms ごとにポーリング）
    ↓
    GET /tasks/{task_id}
    ↓ status == "success"
    抽出結果を取得・表示
```

### 使用例

```bash
SESSION_ID="<セッション ID>"
BASE64_IMG=$(base64 < sign.jpg)

# タスクをキューに登録
TASK=$(curl -s -X POST http://localhost:8000/ocr/process/async \
  -H "Content-Type: application/json" \
  -d "{\"frame\": \"$BASE64_IMG\", \"session_id\": \"$SESSION_ID\"}")

TASK_ID=$(echo $TASK | python3 -c "import sys,json; print(json.load(sys.stdin)['task_id'])")

# 結果を確認
curl http://localhost:8000/tasks/$TASK_ID
```

---

## キャッシュ管理

```bash
# キャッシュ統計
curl http://localhost:8000/cache/stats

# セッションのキャッシュをクリア
curl -X DELETE http://localhost:8000/cache/$SESSION_ID
```

---

## キーワードフィルタ

```bash
# 包含フィルタ（指定キーワードを含む結果のみ保持）
curl -X POST http://localhost:8000/filters/keywords \
  -H "Content-Type: application/json" \
  -d '{"session_id": "'"$SESSION_ID"'", "keywords": ["停止", "注意"], "mode": "include"}'

# 除外フィルタ（指定キーワードを含む結果を除外）
curl -X POST http://localhost:8000/filters/keywords \
  -H "Content-Type: application/json" \
  -d '{"session_id": "'"$SESSION_ID"'", "keywords": ["広告"], "mode": "exclude"}'

# 現在のフィルタを確認
curl http://localhost:8000/filters/keywords/$SESSION_ID
```

---

## セッション統計とエクスポート

```bash
curl http://localhost:8000/sessions/$SESSION_ID/stats
curl http://localhost:8000/export/$SESSION_ID > export.json
```

---

## Redis キースキーマ

| キーパターン | 型 | TTL | 内容 |
|---|---|---|---|
| `session:<id>` | String (JSON) | 300 秒 | セッションメタデータ |
| `texts:<id>` | Set | 3600 秒 | 重複排除用の既出テキスト |
| `filter:<id>` | String (JSON) | なし | キーワードフィルタ設定 |
| `stats:hits` | String (int) | なし | キャッシュヒットカウンタ |
| `stats:misses` | String (int) | なし | キャッシュミスカウンタ |

---

## Celery タスク一覧

| タスク | 説明 | リトライ |
|---|---|---|
| `process_ocr_frame` | フレーム処理・重複排除・DB 保存 | 3 回 × 2 秒 |
| `save_extractions_batch` | 抽出結果の一括挿入 | なし |
| `cleanup_old_sessions` | 30 日以上前のセッションをアーカイブ | なし（定期） |
| `export_session_data` | エクスポート JSON 生成 | なし |

---

## トラブルシューティング

**タスクがずっと PENDING のまま**
```bash
redis-cli -n 1 ping   # PONG が返るか確認
```

**ワーカーがタスクを受け取っても処理しない**
`-A app.tasks.celery_app`（`app.tasks` ではなく）で起動しているか確認してください。
