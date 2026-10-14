# VRMアバターの動画と日本語音声

保存済みのKimodo・ARDYの実生成モーションを、既存の `MotionViewer` と `VRMAvatarMotionSink` でVRMへ適用して録画できます。MP4と出所・計測情報のJSONを保存します。別途生成した短いRealtime音声のWAVを指定すると、音声トラックと口の開閉も録画します。

これは**保存済みモーションと音声の再生録画**です。RealtimeとのライブWebRTC会話、新規Text-to-Motion推論、発話からARDYへの条件付けの成功としては数えません。ARDYの既存例はテキスト・音声なしの無条件CPU診断です。

## 正面・高画質で書き出す（推奨）

`scripts/export_vrm_video.cjs` は1920×1080・30fpsで、各フレームを既存のVRMレンダラーに描画させ、無損失PNGからH.264 CRF 16へ直接変換します。実時間の画面録画で取りこぼしたフレームを繰り返す方式から変更しました。CPUでも時間をかけて全フレームを描画するため、出力の30fpsをGPUの実時間性能として扱いません。

アバターの初期カメラと視点リセットは正面になり、照明も白飛びを抑える強さへ調整しました。出力解像度、全フレーム数、正面のカメラ方向、音声と動画のハッシュ、描画の所要時間をJSONへ保存します。

指定された日本語・英語の発話文は `configs/demo_english_lesson.txt` に保存しています。Realtime音声の上限を60秒へ広げ、長い文章を途中で切らない出力トークン枠にしました。日本語と英語をそれぞれ自然な発音で読み、翻訳や文の省略をしない指示を使用します。

```powershell
.\.venv\Scripts\python.exe scripts\generate_demo_speech.py --text-file configs\demo_english_lesson.txt --output .motion-lab\recordings\english-lesson.wav --budget-usd 1
node scripts\export_vrm_video.cjs --avatar C:\Models\AvatarSample_VRM1.0.vrm --motion .motion-lab\outputs\<実験ID>\motion.json --wav .motion-lab\recordings\english-lesson.wav --speech-metadata .motion-lab\recordings\english-lesson.json --output .motion-lab\recordings\english-lesson-1080p.mp4 --title "英語学習のあいさつ"
```

先にMotion Labを起動し、ChromiumとFFmpegを準備します。`<実験ID>` は手元の実際のモーション保存先に置き換えます。元のWAVを0.5秒の待機後に再生する時刻へ合わせて直接AACへ変換するため、低ビットレートの画面録画音声を経由しません。口の開閉は同じWAVのPCM信号から計算します。

`--width`、`--height`、`--fps` で解像度と出力フレームレートを選べます。`--preview-only yes` は正面と画質を確認するPNGを出力します。既存のMP4・JSON・プレビューは上書きしません。

指定文の実音声は12.50秒、生成処理は7.54秒で、書き起こしが入力文と完全一致することを確認しました。[完成した動画とAPI記録](../reports/videos/README.md) を参照してください。モーションが先に終わる場合は、残りの発話中にデフォルトの発話姿勢・呼吸・まばたき・口の開閉を使います。

## クラウドのネットワークシークレット

名前 `realtime`、環境変数名 `realtime`、接続先 `api.openai.com` を使用できます。バックエンドと録音スクリプトは、ローカル用の `OPENAI_API_KEY`、クラウド用の `MOTION_LAB_OPENAI_API_KEY`、`realtime` の順で存在する認証を使用します。名前だけを宣言しても値は渡されません。環境設定で既存の値を割り当て、保存・Publish後に実行環境への反映を確認してください。

キーの値をチャット、Git、録画メタデータ、ログへ保存しません。ネットワークシークレットのプレースホルダーを実キーとして抽出せず、指定されたOpenAIの接続先へのAuthorizationヘッダーで使用します。録音スクリプトは1回の短い音声応答だけを要求します。`--budget-usd 1` は1セッションの許可枠であり、OpenAIの実請求額を厳密に1ドル以下に制御する機能ではありません。

## 日本語の短い音声を生成する

セットアップ済みのリポジトリで実行します。API利用には料金が発生します。

```powershell
.\.venv\Scripts\python.exe scripts\generate_demo_speech.py --text "こんにちは。よろしくお願いします。" --output .motion-lab\recordings\hello.wav --budget-usd 1
```

Linuxでは `.venv/bin/python` を使用します。Realtime GA WebSocketの実音声をPCM16・24kHz・モノラルWAVへ保存し、実際の書き起こし、モデル・声・使用量、音声のハッシュを `hello.json` に記録します。失敗や未設定を検証音で代替しません。既存の出力は上書きしません。

## 実時間の画面録画を行う

まずMotion Labを起動し、PlaywrightのChromiumとFFmpegを用意します。APIキーは録画時のブラウザへ渡しません。使用条件を確認したVRM 1.0と、実際に手元へ保存したモーションJSONのパスを指定してください。

```powershell
npx playwright install chromium
node scripts\record_vrm_demo.cjs --avatar C:\Models\AvatarSample_VRM1.0.vrm --motion .motion-lab\outputs\<実験ID>\motion.json --wav .motion-lab\recordings\hello.wav --speech-metadata .motion-lab\recordings\hello.json --output .motion-lab\recordings\kimodo-vrm-voice.mp4 --title "Kimodo / 保存済みモーション"
```

`<実験ID>` は実際の保存先へ置き換えます。クラウドで以前生成した例は `outputs/9c59514de11744aeb0a97038e73c7e5d/motion.json`（Kimodo）、`outputs/cfc9aaf72a0944cf8449a978df8d5e29/motion.json`（ARDY無条件診断）です。これらのモーションJSONはGitに含めず、動画の出所は [動画一覧](../reports/videos/README.md) に記録しています。

WAVを省略すると無音の録画になります。別途保存した通常のWAVも使用できますが、`--speech-metadata` がない場合はRealtimeで生成した音声とは表示しません。指定された音声ハッシュとメタデータが一致しなければ録画を拒否します。

動画は960×640のH.264、音声付きの場合はAACです。VRMの実際の描画をMediaRecorderで音声と一緒に保存し、FFmpegでMP4へ変換します。表情は音声のRMSから口の開閉を近似します。音素別のリップシンクや正確な単語同期ではありません。30fpsのMP4にはソフトウェア描画のフレーム反復を含むため、研究室GPUの描画性能の測定としては使用しません。

JSONには元モーション・音声・動画のSHA-256、実描画フレーム数、音声時計のサンプル、検出音量、口の開閉、ブラウザエラー、動画と音声の形式を記録します。元VRMを動画へ埋め込まず、Gitへも追加しません。AvatarSampleの描画動画には pixiv VRoid Project の出典を表示します。

## このクラウドで確認した範囲

2026-10-14（日本時間）：事前に実VRMと実Kimodoモーション、ローカルの人工検証音を使って録画処理を検証しました。その後、利用者のPublishで `realtime` のシークレットが実行環境へ反映され、Realtime GA WebSocket / `gpt-realtime-2.1` / `marin` から「こんにちは。よろしくお願いします。」を実生成しました。音声は3.00秒、生成処理は5.20秒、input 58 / output 79 tokensです。同じ音声を使ってKimodoとARDYの保存済みモーションを録画しました。

[音声付きMP4と生成記録](../reports/videos/README.md) をGitへ保存しています。両方の動画についてH.264＋AAC、MP4の全デコード、実音声の信号、口の開閉、元モーションの再生を確認しています。WebRTCでのライブ会話と新規GPUモーション生成を組み合わせたE2Eは、今回の保存済みデータの再生録画とは別で未実施です。
