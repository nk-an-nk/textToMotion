# セットアップ

## Codespaces

親リポジトリのdevcontainerはPython 3.12・Node.js 22・Java 17・Gradle 8.7・Android SDKを用意します。
既存のCodespaceでは `git pull --ff-only` 後、`bash kebbi-conversation/scripts/setup.sh` を実行してください。
新規環境ではpostCreateCommandがバックエンドの仮想環境と依存関係も準備します。

Macで手動実行する場合はJDK 17をJAVA_HOMEに、Android SDKをANDROID_HOMEに設定します。
この作業端末ではJDKは `/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home`、SDKは `~/Library/Android/sdk` です。
Android StudioにはcompileSdk 35、Build Tools 34.0.0が必要です。

## バックエンド

```bash
cd kebbi-conversation/backend
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
cp .env.example .env
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log
```

APIキーなしでは `LLM_PROVIDER=mock` のまま利用します。
実際のモデルを利用するときはサーバーの `.env` に `LLM_PROVIDER=openai`、`LLM_API_KEY`、`LLM_MODEL`、`LLM_BASE_URL` を設定します。
ベースURLは `/v1` 等までを指定し、クライアントが `/chat/completions` を付加します。
モデル名は接続先で利用可能なものを明示指定します。キーやモデルがないlive設定は起動時にエラーになります。
JSONモード非対応の互換サービスは `LLM_JSON_MODE=false` にし、アプリ側の応答検証を継続します。
上流への `store:false` を送りますが、サービス側の保持方針を上書きする保証ではありません。

`BACKEND_TOKEN` を指定した場合はアプリの設定に同じ共有トークンを入力してください。LLM APIキーとは別の値です。
`LOG_ENABLED=true` / `LOG_CONTENT=false` が初期値です。本文保存は明示的に有効にした場合だけ行います。
サーバー再起動、期限経過後の次の要求、セッション削除で履歴を破棄します。

## アプリからバックエンドへ接続

- 同じPCのAndroidエミュレータ: `http://10.0.2.2:8000`
- USB接続したKebbiと手元PCのバックエンド: `adb reverse tcp:8000 tcp:8000` 後、アプリURLは `http://127.0.0.1:8000`
- LAN接続: 手元PCのLANアドレスを設定。バックエンドを0.0.0.0で待ち受けます。
- Codespacesのバックエンド: 手元PCでGitHub CLIにログインし、`gh codespace ports forward 8000:18000 -c <codespace名>` を起動したままにします。次に `adb reverse tcp:8000 tcp:18000` を設定し、アプリURLを `http://127.0.0.1:8000` にします。

Codespacesのポートを公開設定へ変更する必要はありません。プライベートな転送先URLはAndroidからそのままアクセスできません。
実機へのUSBインストールと `adb reverse` は手元PCから実行します。クラウドから手元のUSBは直接見えません。
HTTPはdebug版のみで許可しています。release版はHTTPSを利用してください。

## Androidビルド

```bash
cd kebbi-conversation/android-app
./gradlew :app:assembleMockDebug
./gradlew :app:assembleRealDebug
```

realビルドは親リポジトリの `sdk/nuwa` を参照します。別のAARは `-PnuwaSdk=/絶対パス/sdk.aar` で指定します。
`app/libs` に置く場合も同プロパティでファイルを指定してください。
mock版のビルドにはAARは不要です。SDKによる権限や依存関係もmockへ入りません。
Android StudioのBuild VariantもmockDebug/realDebugで切り替えます。

APKのインストール:

```bash
adb install -r app/build/outputs/apk/real/debug/app-real-debug.apk
```

mock版のアプリIDは `jp.ojimalab.kebbi.conversation.mock`、real版は `jp.ojimalab.kebbi.conversation` です。
SDK・OSの互換性を優先してtargetSdkは28、minSdkは26にしています。ストア公開向けのターゲット設定ではありません。
