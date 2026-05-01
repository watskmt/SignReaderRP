# SignReader モバイル — Phase 3 セットアップガイド

## 前提条件

| ツール | バージョン | 備考 |
|---|---|---|
| Node.js | 18以上 | nvm使用推奨: `nvm use 18` |
| npm | 9以上 | Node 18に同梱 |
| Xcode | 15以上 | macOSのみ（iOSビルド用） |
| Android Studio | Hedgehog以上 | Androidビルド用 |
| CocoaPods | 1.14以上 | iOS用: `sudo gem install cocoapods` |
| JDK | 17 | Android用: `brew install openjdk@17` |

## 1. JavaScriptパッケージのインストール

```bash
cd mobile
npm install
```

## 2. iOS — ネイティブPodのインストール

```bash
cd ios
pod install
cd ..
```

`pod install` が失敗した場合は以下を試してください:

```bash
pod repo update
pod install --repo-update
```

## 3. API URLの設定

`src/config/api.ts` を編集して `API_BASE_URL` を変更してください:

- **ローカル開発（iOSシミュレーター）:** `http://localhost:8000`
- **ローカル開発（iOSの実機）:** `http://<MacのローカルIP>:8000`
- **ローカル開発（Androidエミュレーター）:** `http://10.0.2.2:8000`
- **ステージング/本番環境:** `https://api.your-domain.com`

CI/CDビルドの場合は、ビルド前に `API_BASE_URL` 環境変数を設定してください。

## 4. Metro Bundlerの起動

```bash
npm start
```

開発中はこのターミナルを開いたままにしてください。

## 5. iOSシミュレーターで実行

```bash
npm run ios
# または特定のシミュレーターを指定:
npx react-native run-ios --simulator="iPhone 15 Pro"
```

## 6. Androidエミュレーターで実行

```bash
# Android Studio → Device Manager で AVD を先に起動してください
npm run android
```

## 7. iOSの実機で実行

1. `ios/SignReader.xcworkspace` をXcodeで開く
2. iPhoneをUSBで接続
3. デバイスセレクタで自分のデバイスを選択
4. Signing & CapabilitiesでApple Developerチームを設定
5. 実行ボタンを押す（Cmd+R）

## 8. Androidの実機で実行

1. デバイスの開発者オプションを有効化
2. USBデバッグを有効化
3. USBで接続
4. `adb devices` でデバイスが一覧に表示されることを確認
5. `npm run android` を実行

## 9. テストの実行

```bash
npm test                   # テストを1回実行
npm test -- --watch        # ウォッチモード
npm run test:coverage      # カバレッジレポート付きで実行
```

## 10. 権限の設定

**iOSシミュレーター:**
- シミュレーターではカメラ権限は自動的に付与されます。実機の場合はシステムダイアログが表示されます。

**Androidエミュレーター:**
- アプリは `react-native-permissions` を通じて実行時に権限を要求します。
- 手動で付与する場合: デバイス設定 → アプリ → SignReader → 権限

## デバッグのヒント

### Metro Bundlerに接続できない場合
- デバイスを振る（またはシミュレーターでCmd+D） → "Configure Bundler"
- Macのファイアウォールがポート8100を許可しているか確認
- Android: `adb reverse tcp:8081 tcp:8081` を実行

### シミュレーターのカメラが黒い場合
- iOSシミュレーターには実際のカメラがありません。カメラビューは黒くなります。完全なカメラテストには実機が必要です。

### `pod install` でSSLエラーが発生する場合
```bash
sudo gem install cocoapods --source http://rubygems.org
```

### "Flipper"エラーでビルドが失敗する場合
`ios/Podfile` に以下を追加:
```ruby
# Flipperを無効化
:flipper_configuration => FlipperConfiguration.disabled,
```
その後 `pod install` を再実行してください。

### Android: SDKが見つからない場合
シェルのプロファイルに `ANDROID_HOME` を設定:
```bash
export ANDROID_HOME=$HOME/Library/Android/sdk
export PATH=$PATH:$ANDROID_HOME/emulator
export PATH=$PATH:$ANDROID_HOME/tools
export PATH=$PATH:$ANDROID_HOME/platform-tools
```

## アプリアーキテクチャ概要

```
src/
├── App.tsx                    # ルートナビゲーション（スタック）
├── config/
│   └── api.ts                 # Axiosインスタンス + インターセプター
├── context/
│   └── AppContext.tsx          # グローバル状態（セッション、抽出結果、録画状態）
├── services/
│   ├── api.ts                 # REST APIコール（型付き）
│   ├── camera.ts              # カメラ + GPSサービス
│   └── storage.ts             # AsyncStorage永続化
└── screens/
    ├── CameraScreen.tsx       # 動画撮影 → フレーム送信 → 結果表示
    ├── SessionListScreen.tsx  # セッション一覧/作成
    └── ResultsScreen.tsx      # フィルタ・エクスポート付き抽出結果閲覧
```

## 主要なフロー

### 録画フロー
1. `CameraScreen` がカメラ権限を要求
2. ユーザーが「録画」をタップ → `CameraService.startFrameCapture()` が500msごとに実行
3. 各フレームをbase64エンコードして `POST /ocr/process/async` に送信
4. アプリが完了まで `GET /tasks/{task_id}` をポーリング
5. 抽出されたテキストがコンテキストに追加されてオーバーレイに表示

### GPSフロー
1. ユーザーが「GPS ON」をタップ → `CameraService.requestLocationPermission()`
2. 各フレーム取得時に `CameraService.getCurrentLocation()` も呼び出し
3. 座標がOCRリクエストに含まれる
4. バックエンドが各Extractionレコードに緯度/経度/高度を保存

### オフラインフロー
1. 全セッションと抽出結果は `LocalStorageService` を通じてAsyncStorageに保存
2. `ResultsScreen` は最初にAPIを試み、オフライン時はAsyncStorageにフォールバック
3. セッション一覧はAsyncStorageから直接読み込み（高速、ネットワーク不要）
