# SignReader バックエンド — 2 分クイックスタート

```bash
# 1. 仮想環境を作成・有効化
cd backend && python3.10 -m venv venv && source venv/bin/activate

# 2. パッケージをインストール
pip install -r requirements.txt

# 3. PostgreSQL + Redis を起動
docker-compose up -d

# 4. 環境変数を設定（パスワードを docker-compose.yml に合わせる）
cp .env.example .env
# .env: DATABASE_URL=postgresql://signreader:signreader_pass@localhost:5432/signreader_db

# 5. Phase 2 API を起動（テーブルは自動作成）
uvicorn app.main_optimized:app --reload --host 0.0.0.0 --port 8000

# 6. 別ターミナルで Celery ワーカーを起動
source venv/bin/activate
celery -A app.tasks.celery_app worker --loglevel=info --concurrency=2
```

起動確認:
```bash
curl http://localhost:8000/health
# → {"status":"ok","version":"0.2.0","ocr_engine":"paddleocr","async_processing":true}
```

Swagger UI: http://localhost:8000/docs
