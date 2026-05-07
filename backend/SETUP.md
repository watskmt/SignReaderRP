# SignReader バックエンド — セットアップガイド

## 前提条件

- Python 3.10（`python3.10 --version` で確認）
- Docker Desktop（PostgreSQL + Redis 用）

## 1. 仮想環境の作成と有効化

```bash
cd backend
python3.10 -m venv venv
source venv/bin/activate
```

## 2. 依存パッケージのインストール

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

> **初回インストール:** `paddleocr` のモデルデータ（約 200MB）は初回実行時に自動ダウンロードされます。

## 3. PostgreSQL + Redis の起動

```bash
docker-compose up -d
docker-compose ps   # 両コンテナが healthy になるまで待つ
```

## 4. 環境変数の設定

```bash
cp .env.example .env
```

`.env` の `DATABASE_URL` のパスワードを `docker-compose.yml` の `POSTGRES_PASSWORD` に合わせます:

```
DATABASE_URL=postgresql://signreader:signreader_pass@localhost:5432/signreader_db
```

## 5. APIサーバーの起動

### Phase 2（非同期 OCR、推奨・本番使用）

ターミナル 1:
```bash
uvicorn app.main_optimized:app --reload --host 0.0.0.0 --port 8000
```

ターミナル 2（Celery ワーカー）:
```bash
celery -A app.tasks.celery_app worker --loglevel=info --concurrency=2
```

### Phase 1（同期 OCR、開発・確認用のみ）

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 6. 動作確認

```bash
curl http://localhost:8000/health
# → {"status":"ok","version":"0.2.0","ocr_engine":"paddleocr","async_processing":true}
```

Swagger UI: http://localhost:8000/docs

```bash
# セッション作成
curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{"title": "テスト調査"}'

# 非同期 OCR
SESSION_ID="<上記で取得した id>"
BASE64_IMG=$(base64 < /path/to/image.png)
curl -X POST http://localhost:8000/ocr/process/async \
  -H "Content-Type: application/json" \
  -d "{\"frame\": \"$BASE64_IMG\", \"session_id\": \"$SESSION_ID\"}"
```

## 7. テストの実行

```bash
# テーブルは自動作成（PostgreSQL 不要）
pytest -v

# カバレッジ付き
pytest --cov=app tests/ --cov-report=term-missing
```

## 8. サービスの停止

```bash
docker-compose down          # コンテナを停止（データを保持）
docker-compose down -v       # コンテナを停止してボリュームも削除
```

## トラブルシューティング

**`password authentication failed for user "signreader"`**
`.env` の `DATABASE_URL` のパスワードが `docker-compose.yml` の `POSTGRES_PASSWORD` と一致しているか確認してください。

**`ModuleNotFoundError: No module named 'paddleocr'`**
仮想環境が有効化されているか確認: `which python` → `venv/bin/python` を指しているはず。

**`Connection refused` (Redis)**
`docker-compose ps` で Redis コンテナが起動しているか確認してください。
