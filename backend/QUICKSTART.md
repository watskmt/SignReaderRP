# SignReader バックエンド — 2分クイックスタート

5つのコマンドで起動できます:

```bash
# 1. 依存パッケージのインストール
cd backend && python3.10 -m venv venv && source venv/bin/activate && pip install -r requirements.txt

# 2. PostgreSQL + Redis の起動
docker-compose up -d

# 3. 環境設定ファイルのコピー
cp .env.example .env

# 4. APIサーバーの起動（テーブルは起動時に自動作成）
uvicorn app.main:app --reload --port 8000

# 5. 動作確認
curl http://localhost:8000/health
```

コマンド5の期待される出力:

```json
{"status": "ok", "version": "0.1.0", "ocr_engine": "paddleocr"}
```

ブラウザで [http://localhost:8000/docs](http://localhost:8000/docs) を開くとインタラクティブなAPIドキュメントが表示されます。
