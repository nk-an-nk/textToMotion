# 日本語音声対話とVRM

`work`ブランチのMotion Labへ `/conversation` を追加しました。Realtime GAのWebRTC音声と書き起こし、ジェスチャー計画、既存の非同期モデルキュー、VRM表示を同じ画面で扱います。モーション研究画面 `/`、MP4出力、発話例とCSVは引き続き使用できます。

**このクラウドではOpenAI APIキーが実行環境へ未反映で、CUDA GPUもなく、実Realtime＋新規GPU推論のE2Eは未実施です。** 無料の実VRM、既存の実生成結果の再生、公式VRMAローダー、ローカル音声時計、遅延・割り込み制御を別々に検証しています。[検証結果](../reports/dialogue_validation.md)を参照してください。[VRMの動画](../reports/videos/README.md)と [日本語音声を追加する録画手順](vrm_recording.md) も追加しました。

## Windowsで起動

既存の `https://github.com/nk-an-nk/textToMotion.git` の `work` ブランチを更新します。未コミットの変更がある場合は保持したうえで、通常のGit操作で更新してください。

```powershell
git switch work
git pull --ff-only origin work
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup-conversation.ps1 -InstallPrerequisites
powershell -NoProfile -ExecutionPolicy Bypass -File .\start-conversation.ps1
```

このPCのブラウザで `http://127.0.0.1:8765/conversation` を開きます。セットアップはアプリ用Python・Git・Node/npm・FFmpegと専用 `.venv` を準備します。GPUモデル・重み・C++コンパイラーの準備とは分離しているため、モデル利用不可でも会話画面を起動できます。Windows実機のインストールとGPU推論は未検証です。

API未設定ではオフライン検証になります。返答は定型文、音声は4秒の**検証音**です。保存済み発話WAV・モーションJSONも選択できます。これをAI応答・新規推論の成功として記録しません。

Realtimeを使う場合は、OpenAI APIの利用と料金を確認して次を実行します。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start-conversation.ps1 -EnableRealtime -BudgetUsd 3 -SessionSeconds 60
```

APIキーは非表示入力で受け取り、そのPowerShellプロセスと起動したバックエンド内だけで使用します。ファイルに保存しません。既存の `OPENAI_API_KEY` も利用できます。**Codex CLIへのChatGPTログインとは別の、OpenAI APIキーとAPI課金設定が必要です。** 標準APIキーをブラウザへ渡しません。

ブラウザで利用条件を確認したVRM 1.0ファイルを選び、「有料APIに接続」→テキスト送信、または「マイク開始」と進めます。マイクは明示的に開始した後のみ取得します。切断・割り込み・再接続を操作できます。モデル未準備時も音声とデフォルト動作を継続します。

モデルは [既存のWindows手順](windows_lab.md) で準備します。`configs/lab-windows.json` のGPUプロファイルと実際のCUDA演算検査を使用し、対話コードはGPU型番やVRAMを決め打ちしません。セットアップを行った同じ `-DataDir` で対話アプリを起動してください。

Linux開発環境では次を使用します。

```bash
bash scripts/setup.sh
.venv/bin/python scripts/start_conversation.py
# 実APIへの接続を許可する場合のみ
.venv/bin/python scripts/start_conversation.py --enable-realtime --budget-usd 3
```

## Realtime GAと費用設定

`POST /api/realtime/calls` はSDP offerを受け、バックエンドから `POST https://api.openai.com/v1/realtime/calls` へ `sdp` と `session` のmultipartを送ります。SDP answerだけをブラウザへ返します。Betaヘッダー・旧Betaセッション形式は使用しません。

`OPENAI_REALTIME_MODEL` の既定は `gpt-realtime-2.1`、音声は `marin`。現行の公式SDKでモデル名・GA calls形式・イベントを確認しています。ただし、利用者アカウントでのモデル利用権は実接続で確認する必要があります。公式ガイドへの接続がクラウドのネットワーク設定で拒否されたため、[公式SDKのRealtime定義](https://github.com/openai/openai-node/blob/master/src/resources/realtime/realtime.ts)と[calls定義](https://github.com/openai/openai-node/blob/master/src/resources/realtime/calls.ts)を確認根拠として記録しました。

| 設定 | 既定 | 意味 |
|---|---|---|
| `OPENAI_REALTIME_ENABLED` | `0` | `1` の場合に実APIを許可 |
| `OPENAI_API_BUDGET_USD` | `0` | 1サーバープロセスで事前許可する利用枠 |
| `OPENAI_SESSION_ALLOWANCE_USD` | `1` | Realtime接続またはText-first要求ごとに予約する枠 |
| `OPENAI_MAX_CALLS` | `3` | 接続・Text-first要求の上限回数 |
| `OPENAI_SESSION_SECONDS` | `60` | ブラウザが接続を終了する時間、10〜180秒 |
| `OPENAI_TEXT_FIRST_ENABLED` | `0` | 実験用Text-firstを許可 |
| `OPENAI_PLANNER_MODEL` | `gpt-4.1-mini` | Text-firstのResponses APIモデル |

予約枠は**実際の請求額の計測や厳密なドル上限ではありません**。失敗した接続も枠を消費し、サーバーを再起動すると回数はリセットされます。出力上限512 tokens・セッション時間・要求回数を制限していますが、WebRTCの直接音声通信の料金をこのサーバーだけで厳密に停止できません。OpenAI側でもプロジェクトの利用制限・予算を設定してください。APIキー・許可・正の予算がなければ有料APIへ接続しません。

Voice-firstではRealtimeの音声書き起こしから、音声を止めずに動作計画を送ります。Text-firstは `-TextFirst` を起動時に追加すると有効になります。Responses APIで返答・動作案を先に作り、Realtimeの `response.create` の指示に回答候補を渡します。これは専用TTSとしての一字一句の読み上げを保証する機能ではありません。実際の音声書き起こしとの一致を確認するまで生成動作を適用せず、不一致なら無効化します。

## 計画とモデルAPI

`app/gesture.py` の計画は turn/response/gesture ID、分類、元の日本語、英語指示、anchor、優先度、長さ、開始下限・期限・状態を保持します。左右の手を振る、お辞儀、紹介して最後にお辞儀、嬉しい会話の控えめなジェスチャーを扱います。任意の日本語を正確に翻訳できるという意味ではありません。未対応の複雑な指示はデフォルト動作を選び、英語の動作指示欄で補えます。継続時間を勝手に20秒へ縮めず、範囲外なら生成しません。Text-firstの明示的動作は検証済みの規則を優先し、未対応のLLM動作案を自動実行しません。

`anchor_text` はフレーズの関連を示します。単語タイムスタンプがないため、現実装の適用窓は実音声の開始をクライアントで観測した時点からの**粗いフレーズ同期・推定**です。「最後のお辞儀」の正確な単語同期や、動作の意味的一致は未検証です。

| API | 用途 |
|---|---|
| `POST /api/conversation/plan` | 日本語と返答から計画を作成 |
| `POST /api/conversation/prepare` | フラグ・予算付きText-first |
| `POST /api/motion/requests` | 既存キューへ送り即座に `request_id` を返す |
| `GET /api/motion/requests/{id}` | 状態・同じ時計領域の生成時刻・出所 |
| `GET /api/motion/requests/{id}/motion` | 正規化骨格JSON |
| `GET /api/motion/requests/{id}/vrma` | 元VRMA |
| `DELETE /api/motion/requests/{id}` | 待機中の実行を取消、実行中の結果を無効化 |

推論中の公式CLIプロセスは安全に強制終了していません。取消後も処理が完了する場合がありますが、結果は `cancelled` のまま保持し対話には適用しません。元データは研究用に残します。バッチ生成のみを扱い、最初の部分チャンク到着はnullです。バッチを分割してストリーミング生成とは呼びません。

対話用のNVIDIA公式オンラインデモへの送信は既定で拒否します。UIの許可チェックがある場合も送るのは動作指示で、会話履歴全体は送信しません。ローカルGPU経路を優先します。

研究室GPUサービスを別PCで動かす場合、同じFastAPIをモデル準備済みのPCで起動し、対話バックエンドへ次を設定できます。

```text
GPUサービス：MOTION_SERVICE_ACCESS_TOKEN=<専用トークン>
対話サーバー：MOTION_SERVICE_URL=http://<研究室内GPUホスト>:8765
             MOTION_SERVICE_TOKEN=<同じ専用トークン>
```

ブラウザは同じ対話サーバーだけにアクセスし、トークンはバックエンドのHTTPヘッダーに保持します。外部に公開せず、研究室内の接続設定に従ってください。ネットワーク切断はUIと計測ログに残し、音声を止めません。既存の起動スクリプトはloopbackのみです。別PCから接続するGPUサービスのbind設定は管理者の方針に従い明示的に行ってください。

## VRMと同期

`@pixiv/three-vrm` と `@pixiv/three-vrm-animation` は3.5.5に固定しています。VRM 1.0をブラウザ内で読み込み、外部URI参照を拒否します。無料の [AvatarSample](https://hub.vroid.com/characters/2843975675147313744/models/5644550979324015604) の利用条件とモデル内メタデータを確認してください。確認に使用したモデルは © pixiv VRoid Project、`allowRedistribution=false` なので、モデルファイルをこのリポジトリへ追加していません。

VRMAは公式 `VRMAnimationLoaderPlugin` と `createVRMAnimationClip` で適用します。JSONは名前対応・胴体の座標基底・骨の方向・脚長比を使って最小回転を推定し、Quaternionトラックを作ります。位置のみから一意に得られない頭・手首・骨軸のねじれを推測で補いません。足は簡易床補正で、接地IKや足滑りの解消ではありません。変換方法・対応表・寸法比をclipに記録します。

1つのAnimationMixerで生成動作を制御し、デフォルト姿勢との切り替えは関節別の重みを持つSLERPとルート補間を使います。VRMではモーションの最初のルートを現在のアバター位置へ合わせ、寸法補正した相対軌跡を保ちます。発話終了でニュートラルに戻り、移動後の水平ルート位置を保持します。常時のランダムなうなずき・首振りはありません。VRMとスケルトンの表示を切り替えられます。既存研究画面ではVRMA複数ファイルの連続再生・停止・シークができます。

音声の基準はHTMLAudioElementの時計と、同じ音声を観測するWeb Audioの信号です。WebRTCの `output_audio_buffer.started` は観測を準備するイベントで、スピーカーからの発声時刻として記録しません。`response.done` は生成終了のみです。サーバーの音声バッファ終了後もローカルの音声信号を確認して待機へ戻ります。出力デバイスの遅延、単語時刻、物理的なスピーカーの発声時刻は未測定です。

割り込みは `response.cancel`（生成中のみ）とWebRTCの `output_audio_buffer.clear`、ローカルの音声ミュート、モデル要求の取消・無効化をまとめて行います。WebRTCの音声切り捨てはサーバーが管理し、推測した単語時刻で `conversation.item.truncate` を二重送信しません。response metadataのturn IDとitem/content IDで書き起こしを対応付け、古い応答を次のターンへ割り当てません。

## 研究記録と受入テスト

Aはデフォルト動作のみ、Bは生成待機（30秒上限後に会話を継続）、Cは発話と並列で完成次第切り替え、Dは並列生成と期限判定です。通常はDです。B/Text-firstで応答作成前に要求した動作は仮のresponse IDを使い、同じturn IDに限って実際のresponse IDへ明示的に結び付けます。

CSVはclient `performance.now()`、client audio、server monotonicを区別します。各イベントのturn/response/gesture ID、A〜D、出所、推定フラグを保存し、時計の異なる値を単純に差し引きません。実際のLLM内部生成開始・終了、部分チャンク、GPUピークメモリ、意味的品質は測定できなければnullです。応答開始・終了イベントの受信は別項目です。

「研究記録をこのサーバーに保存」を押したときだけ `.motion-lab/conversations/<id>.json` に音声を含まない記録を保存します。CSVはブラウザからも保存できます。動作結果は既存の `.motion-lab/outputs/<実験ID>/`、MP4は既存の動画作成操作で保存します。音声録音・顔映像は自動保存しません。

```bash
.venv/bin/python -m pytest -q
npm run test:unit
npm run test:browser
```

実Realtime＋ローカルGPUのE2Eは、API許可・予算付きの対話アプリを起動してから、利用条件を確認したVRMを指定し、**明示的に有料APIテストを許可した場合だけ**実行します。

```powershell
$env:MOTION_LAB_LIVE_E2E = '1'
$env:MOTION_LAB_TEST_VRM = 'C:\Models\AvatarSample_VRM1.0.vrm'
$env:MOTION_LAB_LIVE_MODEL = 'kimodo'
npx playwright install chromium
npx playwright test --config playwright.live.config.cjs
```

通常のブラウザテストはAPIを無効化した独立環境で実行します。live E2Eだけは既に起動した実サーバーを使い、実音声・新規学習済み結果・同じ発話中のVRM適用を検査します。生成が間に合わなければ成功扱いにしません。

[状態・シーケンス図](dialogue_architecture.md)と `VRMAvatarMotionSink`、`RecordedMotionSink`、未実装で送信を拒否する `KebbiMotionSink` を分離しています。Kebbi実機には動作を送信していません。
