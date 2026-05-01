# SignReader モバイル — セットアップガイド

## 前提条件

| ツール | バージョン | 備考 |
|---|---|---|
| Node.js | 18 以上 | `nvm use 18` |
| React Native CLI | - | `npm install -g @react-native-community/cli` |
| Xcode | 15 以上 | macOS のみ（iOS ビルド用） |
| Android Studio | Hedgehog 以上 | Android ビルド用 |
| JDK | 17 | `brew install openjdk@17` |
| CocoaPods | 1.14 以上 | `sudo gem install cocoapods` |

## 1. パッケージのインストール

```bash
cd mobile
npm install
```

## 2. 環境変数の設定（`~/.zshrc` に追加）

```bash
# Android SDK
export ANDROID_HOME=$HOME/Library/Android/sdk
export PATH=$PATH:$ANDROID_HOME/emulator
export PATH=$PATH:$ANDROID_HOME/platform-tools
export PATH=$PATH:$ANDROID_HOME/tools

# Java 17
export PATH="/opt/homebrew/opt/openjdk@17/bin:$PATH"
```

```bash
source ~/.zshrc
```

## 3. API URL の設定

`src/config/api.ts` の `API_BASE_URL` を環境に合わせて変更:

| 環境 | URL |
|---|---|
| Android エミュレーター | `http://10.0.2.2:8000` |
| iOS シミュレーター | `http://localhost:8000` |
| 実機（同一 WiFi） | `http://192.168.x.x:8000`（Mac のローカル IP） |

バックエンドは `--host 0.0.0.0` で起動する必要があります。

## 4. Android エミュレーターで実行

```bash
# エミュレーターを先に起動
$ANDROID_HOME/emulator/emulator -avd Pixel_10 &

# ビルド・インストール（起動完了後）
npm run android
```

> 初回ビルドは Gradle ダウンロードのため 5〜10 分かかります。

## 5. iOS シミュレーターで実行

```bash
cd ios && pod install && cd ..
npm run ios
```

## 6. 実機（iOS）で実行

1. `ios/SignReader.xcworkspace` を Xcode で開く
2. iPhone を USB で接続
3. Signing & Capabilities で Apple Developer Team を設定
4. Run（Cmd+R）

## 7. 実機（Android）で実行

```bash
adb devices            # デバイスが表示されることを確認
npm run android
```

## 8. テストの実行

```bash
npm test               # 全 21 件
npm run test:coverage  # カバレッジ付き
```

---

## アプリアーキテクチャ

```
src/
├── App.tsx                    # ルートナビゲーション（Stack）
├── config/api.ts              # Axios インスタンス・API URL
├── context/AppContext.tsx      # グローバル状態（session, recording, GPS）
├── services/
│   ├── api.ts                 # バックエンド API クライアント（型付き）
│   ├── camera.ts              # カメラ権限・GPS・フレーム取得
│   └── storage.ts             # AsyncStorage 永続化
└── screens/
    ├── CameraScreen.tsx       # メイン画面（撮影・OCR・結果表示）
    ├── SessionListScreen.tsx  # セッション一覧・作成
    └── ResultsScreen.tsx      # 抽出結果閲覧・フィルタ・エクスポート
```

## カメラ・権限

アプリは `react-native-vision-camera v4` を使用しています。

**Android 権限（AndroidManifest.xml に設定済み）:**
```xml
<uses-permission android:name="android.permission.CAMERA" />
<uses-permission android:name="android.permission.RECORD_AUDIO" />
<uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />
```

初回起動時にシステムダイアログが表示されます。「許可」を選択してください。

権限を一度拒否した場合は adb で付与できます:
```bash
adb shell pm grant com.signreader android.permission.CAMERA
adb shell pm grant com.signreader android.permission.ACCESS_FINE_LOCATION
```

> エミュレーターはカメラが使えません（黒い画面）。カメラ機能のテストには実機が必要です。

## 録画フロー

1. Record ボタンをタップ
2. `CameraService.startFrameCapture()` が 500ms ごとに起動
3. フレームを base64 に変換して `POST /ocr/process/async` に送信
4. `GET /tasks/{task_id}` を 800ms 間隔でポーリング
5. 完了したテキストをオーバーレイに表示

## デバッグのヒント

**Metro が接続できない場合:**
```bash
npx react-native start --reset-cache
```

**Android ビルドが失敗する場合:**
```bash
cd android && ./gradlew clean && cd ..
npm run android
```

**Gradle でメモリ不足になる場合:**
`android/gradle.properties` の `org.gradle.jvmargs` を調整:
```
org.gradle.jvmargs=-Xmx4096m -XX:MaxMetaspaceSize=512m
```
