# Kebbi Conversation

Kebbi標準ASR → FastAPI → OpenAI互換LLM → 標準TTS＋既存モーション、を接続する研究用Androidアプリです。
Javaの `mock` / `real` flavorを分離し、AAR・APIキー・実機がなくてもモックで開発できます。
新しいText-to-Motion生成、車輪移動API、関節の直接制御は含みません。

## 最初に動かす

リポジトリ直下でバックエンドの依存関係を準備します。CodespacesではJava 17・Gradle・Android SDKが既に利用できます。

```bash
bash kebbi-conversation/scripts/setup.sh
cd kebbi-conversation/backend
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log
```

初期設定はモックLLMです。別のターミナルで確認します。

```bash
curl http://127.0.0.1:8000/health
curl -H 'Content-Type: application/json' http://127.0.0.1:8000/api/respond \
  -d '{"session_id":"demo","text":"Hello, Kebbi!","language":"en"}'
cd kebbi-conversation/android-app
./gradlew :app:assembleMockDebug
```

APK: `android-app/app/build/outputs/apk/mock/debug/app-mock-debug.apk`。
Android Studioで `android-app` を開き、Build Variantを `mockDebug` にして起動することもできます。
アプリの「設定」でバックエンドURLを指定し、テキストを入力して「テキストで会話」を押します。
`greet → mock_wave` などはモック専用IDで、実機IDではありません。

## 構成

- `android-app/core`: Android非依存の会話状態管理・同期制御・契約検証・HTTPクライアント・モック
- `android-app/app`: 研究用画面・設定・モーション管理・JSONログ
- `app/src/real`: NUWA SDK接続のみを隔離
- `backend/app`: FastAPI、モック/外部LLM、メモリ内の会話履歴
- `config/gesture_mapping.json`: 実機向けの初期マッピング。すべて空配列
- `docs`: [構成](docs/architecture.md)、[セットアップ](docs/setup.md)、[SDK](docs/kebbi-sdk.md)、[テスト](docs/testing.md)

## 実機ビルド

リポジトリ直下で `bash scripts/download-nuwa-sdk.sh` を実行すれば、メーカー指定の2.1.0.08が配置されます。

```bash
cd kebbi-conversation/android-app
./gradlew :app:assembleRealDebug
# 別のSDKを使う場合:
./gradlew :app:assembleRealDebug -PnuwaSdk=/absolute/path/NuwaSDK.aar
```

SDKがない場合は実機版だけが明示的なエラーとなり、モック版はビルドできます。
手元のPCへAPKをダウンロードし、USBデバッグを有効にしたKebbiへ `adb install -r app-real-debug.apk` でインストールします。
最初は「モーション管理」で実機一覧の取得と単独再生を確認し、IDとカテゴリを割り当てて保存してください。

## テスト

```bash
# リポジトリ直下
bash kebbi-conversation/scripts/verify.sh
# AARも含めてビルド検証
KEBBI_VERIFY_REAL=true bash kebbi-conversation/scripts/verify.sh
```

Pythonの単体/APIテスト、Javaの状態管理テスト、実際のHTTPによるFastAPIモックLLM→MockRobotAdapter→IDLEの結合テスト、モックAPKのビルドを実行します。
Kebbi実機のテストは自動テストと区別しています。[手順と制約](docs/testing.md)を参照してください。

## ログと制約

会話本文の永続保存は初期状態で無効です。Androidは本文なしのJSONイベントをメモリとLogcatに記録します。
端末内ファイルへの保存・本文の記録はそれぞれ設定で有効にした場合だけ実行します。
サーバーの履歴は最大128セッション・各6往復・15分の非活動期限付きで、プロセスのメモリ内にのみ保持します。
外部LLMへ送信する際の保存・保持ポリシーは接続先サービスに依存します。

ボタン開始のASRに対応します。常時認識・ウェイクワード・自動再認識は未実装です。
発話とモーションは近接して開始要求を出しますが、実機での同時開始や単語単位の同期を保証しません。
実機の型番・OS・音声エンジン・モーション一覧は未確定です。実機動作確認済みという意味ではありません。
