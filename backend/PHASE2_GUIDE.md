# SignReader バックエンド — Phase 2 ガイド（Redis + Celery）

Phase 2では、Celeryによる非同期OCR処理、Redisを使った重複排除キャッシュ、キーワードフィルタ、セッション統計を追加します。`app/main.py` の代わりに `app/main_optimized.py` を使用してください。

## 前提条件

Phase 1のセットアップを完了していること。Docker Composeが起動していることを確認:

```bash
docker-compose ps   # postgres と redis の両方が healthy 状態であること
```

## 1. 最適化版APIの起動

```bash
uvicorn app.main_optimized:app --reload --host 0.0.0.0 --port 8000
```

ブラウザで [http://localhost:8000/docs](http://localhost:8000/docs) を開くとPhase 2の全エンドポイントが確認できます。

## 2. Celeryワーカーの起動

2つ目のターミナルを開き（venvを有効化した状態で）:

```bash
cd backend
source venv/bin/activate

celery -A app.tasks.celery_app worker --loglevel=info --concurrency=2
```

`--concurrency=2` は通常のノートPCでのRAM枯渇を防ぐためにPaddleOCRインスタンスを2つに制限します。

## 3. Celery Beat（定期タスク）の起動

定期クリーンアップタスク用に3つ目のターミナルを開きます:

```bash
celery -A app.tasks.celery_app beat --loglevel=info
```

毎日UTC 02:00に `cleanup_old_sessions` が実行されます。

## 4. Flowerによる監視

FlowerはCeleryタスクを監視するためのWebUIです:

```bash
pip install flower
celery -A app.tasks.celery_app flower --port=5555
```

[http://localhost:5555](http://localhost:5555) でタスクキュー、ワーカー、実行履歴を確認できます。

## 5. 非同期OCR処理フロー

```
モバイルアプリ
    │
    ▼ POST /ocr/process/async  { frame, session_id, lat, lon }
FastAPI
    │
    ▼ { task_id, status: "queued" } を返す
モバイルアプリ（500msごとにポーリング）
    │
    ▼ GET /tasks/{task_id}
FastAPI → AsyncResult(task_id) → { status, result }
    │
    ▼ status == "success" になったら
モバイルアプリが抽出結果をローカルに保存
```

### 使用例

```bash
SESSION_ID="<セッションID>"
BASE64_IMG=$(base64 < /path/to/sign.jpg)

# タスクをキューに追加
TASK=$(curl -s -X POST http://localhost:8000/ocr/process/async \
  -H "Content-Type: application/json" \
  -d "{\"frame\": \"$BASE64_IMG\", \"session_id\": \"$SESSION_ID\"}")

TASK_ID=$(echo $TASK | python3 -c "import sys,json; print(json.load(sys.stdin)['task_id'])")

# 結果をポーリング
curl http://localhost:8000/tasks/$TASK_ID
```

## 6. キャッシュ管理

```bash
# キャッシュ統計の確認
curl http://localhost:8000/cache/stats

# 特定セッションのキャッシュをクリア
curl -X DELETE http://localhost:8000/cache/$SESSION_ID
```

## 7. キーワードフィルタ

```bash
# 包含フィルタの設定（"停止"または"注意"を含むテキストのみ保持）
curl -X POST http://localhost:8000/filters/keywords \
  -H "Content-Type: application/json" \
  -d "{
    \"session_id\": \"$SESSION_ID\",
    \"keywords\": [\"停止\", \"注意\"],
    \"mode\": \"include\"
  }"

# セッションの現在のフィルタを取得
curl http://localhost:8000/filters/keywords/$SESSION_ID

# 除外フィルタの設定（"広告"を含むテキストを除外）
curl -X POST http://localhost:8000/filters/keywords \
  -H "Content-Type: application/json" \
  -d "{
    \"session_id\": \"$SESSION_ID\",
    \"keywords\": [\"広告\", \"セール\"],
    \"mode\": \"exclude\"
  }"
```

## 8. セッション統計とエクスポート

```bash
# セッション統計の確認
curl http://localhost:8000/sessions/$SESSION_ID/stats

# セッションをJSONとしてエクスポート
curl http://localhost:8000/export/$SESSION_ID > session_export.json
```

## 9. Redisキースキーマ

| キーパターン | 型 | TTL | 内容 |
|---|---|---|---|
| `session:<id>` | String（JSON） | 300秒 | セッションメタデータ |
| `texts:<id>` | Set | 3600秒 | 重複排除用の既出テキスト文字列 |
| `filter:<id>` | String（JSON） | なし | キーワードフィルタ設定 |
| `stats:hits` | String（整数） | なし | キャッシュヒットカウンタ |
| `stats:misses` | String（整数） | なし | キャッシュミスカウンタ |

## 10. Celeryタスク一覧

| タスク | 説明 | リトライ |
|---|---|---|
| `app.tasks.process_ocr_frame` | 単一フレームを処理し、重複排除してDBに保存 | 3回 × 2秒バックオフ |
| `app.tasks.save_extractions_batch` | 抽出結果リストの一括挿入 | なし |
| `app.tasks.cleanup_old_sessions` | 30日以上前のセッションをアーカイブ | なし（定期タスク） |
| `app.tasks.export_session_data` | エクスポートJSONを生成してリザルトバックエンドに保存 | なし |

## トラブルシューティング

**ワーカーがタスクを受け取っても何も処理しない**
ワーカーを `-A app.tasks.celery_app`（`app.tasks` ではなく）で起動していることを確認してください。

**タスクがずっとPENDING状態のまま**
Celeryブローカーの接続先（`redis://localhost:6379/1`）が到達可能か確認してください: `redis-cli -n 1 ping`

**FlowerでREPLACED状態が表示される**
タスクがリトライされています。ワーカーのログで元の例外を確認してください。
