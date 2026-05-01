# SignReader バックエンド — Phase 1 セットアップガイド

## 前提条件

- Python 3.10 または 3.11
- Docker Desktop（PostgreSQL + Redis 用）
- Git

## 1. 仮想環境の作成と有効化

```bash
cd backend
python3.10 -m venv venv

# macOS / Linux
source venv/bin/activate

# Windows（PowerShell）
venv\Scripts\Activate.ps1
```

## 2. 依存パッケージのインストール

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

> **注意:** `paddleocr` の初回インストール時に約200MBのモデルデータがダウンロードされます。開発中にOCRをスキップしたい場合は、PaddleOCRがインポートできない場合に空の結果を返すようにサービスが設計されています。

## 3. PostgreSQL と Redis の起動

```bash
docker-compose up -d
```

両方のコンテナが正常に起動していることを確認:

```bash
docker-compose ps
```

`signreader_postgres` と `signreader_redis` のステータスが `Up (healthy)` と表示されれば正常です。

## 4. 環境変数の設定

```bash
cp .env.example .env
```

`.env.example` のデフォルト値は `docker-compose.yml` の認証情報と一致しているため、ローカル開発では変更不要です。

## 5. データベースのマイグレーション

Alembicを設定している場合:

```bash
alembic upgrade head
```

FastAPIの起動イベントが `create_tables()` を呼び出してテーブルを自動作成するため、Alembicのセットアップを省略することもできます:

```bash
# テーブルはAPIの初回起動時に自動作成されます
```

## 6. APIサーバーの起動

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 7. APIの動作確認

ブラウザで [http://localhost:8000/docs](http://localhost:8000/docs) を開くとインタラクティブなSwagger UIが表示されます。

curl でも確認できます:

```bash
# ヘルスチェック
curl http://localhost:8000/health

# セッションの作成
curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{"title": "最初の調査"}'

# 画像のOCR処理（実際のbase64に置き換えてください）
SESSION_ID="<上記で取得したid>"
BASE64_IMG=$(base64 < /path/to/image.png)
curl -X POST http://localhost:8000/ocr/process \
  -H "Content-Type: application/json" \
  -d "{\"frame\": \"$BASE64_IMG\", \"session_id\": \"$SESSION_ID\"}"

# セッションの抽出結果を取得
curl http://localhost:8000/extract/$SESSION_ID
```

## 8. テストの実行

```bash
pytest tests/ -v
```

カバレッジ付きで実行:

```bash
pytest --cov=app tests/ --cov-report=term-missing
```

## 9. サービスの停止

```bash
docker-compose down          # コンテナを停止（データを保持）
docker-compose down -v       # コンテナを停止してボリュームも削除
```

## トラブルシューティング

**`psycopg2.OperationalError: could not connect to server`**
Dockerが起動していて、postgresコンテナが正常かどうか確認してください: `docker-compose ps`

**`ModuleNotFoundError: No module named 'paddleocr'`**
仮想環境内で `pip install paddlepaddle==2.5.2 paddleocr==2.7.0.3` を実行してください。

**ポート5432がすでに使用中**
別のPostgreSQLインスタンスが起動しています。停止するか、`docker-compose.yml` のポートマッピングを変更してください。
