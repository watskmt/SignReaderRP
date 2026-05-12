# SignReader 開発者ガイド

このドキュメントは、SignReader プロジェクトに参加する開発者のための技術ガイドです。システムの詳細な構造、開発ワークフロー、およびベストプラクティスについて説明します。

## 1. 開発環境のセットアップ

### 前提条件
- **OS**: macOS (推奨) または Linux (Ubuntu/Rocky)
- **Node.js**: v18以上 (LTS推奨)
- **Python**: 3.10.x
- **Docker & Docker Compose**
- **Android Studio**: Android SDK 35, Build Tools 35.0.0, NDK 27.1
- **Java**: OpenJDK 17

### バックエンドのセットアップ
1. **仮想環境の作成**:
   ```bash
   cd backend
   python3.10 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
2. **インフラの起動**:
   ```bash
   docker-compose up -d  # PostgreSQL と Redis を起動
   ```
3. **環境変数の設定**:
   `.env.example` を `.env` にコピーし、必要に応じて編集します。
4. **サーバーの起動**:
   ```bash
   # API サーバー
   uvicorn app.main_optimized:app --reload --host 0.0.0.0 --port 8000
   
   # Celery ワーカー (別ターミナル)
   celery -A app.tasks.celery_app worker --loglevel=info --concurrency=2
   ```

### モバイルのセットアップ
1. **依存関係のインストール**:
   ```bash
   cd mobile
   npm install
   ```
2. **Android ビルド**:
   ```bash
   npx react-native run-android
   ```

---

## 2. システムアーキテクチャ詳細

### データフロー (OCR 処理)
1. **Mobile**: `VisionCamera` が 500ms ごとにフレームを取得。
2. **Mobile**: `api.ts` を通じて `/ocr/process/async` へ送信。
3. **Backend**: FastAPI がリクエストを受け取り、Celery タスクをキューイング。
4. **Backend**: Celery ワーカーが `PaddleOCR` を実行。
5. **Backend**: 結果を Redis に一時保存し、ファジーマッチングで重複を判定。
6. **Backend**: 最終結果を PostgreSQL に保存。
7. **Mobile**: `task_id` を用いてポーリングし、結果を表示。

### 主要コンポーネント
- **Backend**:
  - `app/main_optimized.py`: エントリーポイント。
  - `app/tasks.py`: Celery タスク定義（OCR、定期アーカイブ）。
  - `app/services/ocr_service.py`: PaddleOCR のラッパー。
  - `app/services/filter_service.py`: 重複排除とキーワードフィルタ。
- **Mobile**:
  - `src/screens/CameraScreen.tsx`: カメラ制御とフレーム送信ロジック。
  - `src/services/api.ts`: Axios ベースの通信クライアント。
  - `src/context/AppContext.tsx`: アプリの状態管理。

---

## 3. 開発ガイドライン

### コーディング規約
- **TypeScript (Mobile)**: 
  - strict モードを有効。
  - 型定義を徹底し、`any` の使用を避ける。
  - コンポーネントは関数コンポーネントを使用。
- **Python (Backend)**:
  - PEP 8 準拠。
  - 型ヒントを必須とする。
  - 非同期処理 (`async/await`) を適切に使用。

### テスト
- **バックエンド**: `pytest` を使用。DB 操作を伴うテストはテスト用 DB を使用するように設定されています。
  ```bash
  cd backend && pytest
  ```
- **モバイル**: `Jest` を使用。
  ```bash
  cd mobile && npm test
  ```

### API 変更時の注意点
1. `app/schemas.py` の Pydantic モデルを更新。
2. `app/main_optimized.py` のエンドポイントを修正。
3. `mobile/src/services/api.ts` の型定義とリクエストロジックを更新。

---

## 4. トラブルシューティング

### モバイルアプリが API に接続できない
- **原因**: 開発マシンのローカル IP が `mobile/src/config/api.ts` に設定されていない。
- **解決策**: `localhost` ではなく、PC の実際の IP（例: `192.168.x.x`）を設定してください。

### OCR の反応が遅い
- **原因**: CPU リソースの不足、または Celery ワーカーが起動していない。
- **解決策**: `celery worker` が正常に動作しているか確認してください。CPU 推論のため、最初の実行はモデルのロードに時間がかかります。

### Android ビルドエラー
- **原因**: NDK のバージョン不一致。
- **解決策**: `android/build.gradle` で指定されている `ndkVersion "27.1.12297006"` がインストールされているか確認してください。

---

## 5. デプロイフロー

詳細は `deploy.sh`、`.github/workflows/deploy.yml` および `README.md` を参照してください。
基本手順:
1. `main` ブランチへ `git push` (GitHub Actions が自動デプロイを開始)
2. 手動デプロイが必要な場合は、適切な環境変数を設定して `./deploy.sh deploy` を実行
