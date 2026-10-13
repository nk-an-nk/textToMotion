# 実行結果と到達点

記録日（日本時間）: 2026-10-13T22:02:25.757618+09:00

**Stage 1・2・4 の範囲を実装・検証。Stage 3（会話ジェスチャー＋動作指示の双方で実推論成功）は未達**。CはKimodo公式オンラインで成立。A/Bは未成立。ARDYの無条件推論はA/B/Cの成功に数えません。

| モデル | 分類 | 実際に確認した範囲と制約 |
|---|---|---|
| The Language of Motion v1 | **利用不可** | このCPUインスタンスの公式v1経路。CUDA・許諾済みSMPL-X/FLAME・旧依存環境が不足。公開v1重みは存在し配信先へ到達。 |
| ARDY | **実際に推論成功** | CPU無条件診断のみ。言語・音声条件付き成功ではない。専用env/公式CLI/ネイティブ拡張/公開重みSHA確認済み。 |
| Kimodo | **実際に推論成功** | NVIDIA公式オンラインSOMA-RP-v1、動作指示C。ローカルv1.1とgated encoderは未実行。 |
| MIBURI | **利用不可** | 今回のCPU環境でCUDA直呼び経路不可。Moshi/SMPL-X等は未取得。公式SpaceはPAUSED、起動していない。実行アダプター未実装。 |
| StreamTalk | **利用不可** | 今回のCPU環境で公式CUDA必須経路不可。SMPL-X/BEAT2 retrieval/WavLM資産未取得。GPUアダプターは実推論未検証。 |
| LLM-Gesture-Pipelines | **利用不可** | 公式inference.pyがCUDA固定。Llama3.2/Drive重み/seed/正規化/BVH資産未取得、実行アダプター未実装。 |
| ViBES (body) | **利用不可** | 会話body expertは公開取得先を確認できず利用不可。別公開のViBES-T2Mは**未実行**。Face/Audioをbodyに代用しない。 |
| FreeTalker | **未実行** | 公式sourceを調査。Drive/Baidu重み・旧依存環境・feature資産・root license未確認。アダプター未実装。 |
| AgentHands / XR Blocks | **利用不可** | 任意full-body learned generatorとしては対象外。AgentHandsは動作選択・制御addon。addon自体は未実行。 |

「利用不可」は今回の環境・対象経路についての分類です。GPU搭載環境の一般的な実行不可能性を意味しません。コード公開だけでモデル推論成功とは扱いません。

## 実生成の証拠

| 実験 | 入力条件 / device | 時間の実測 | 出力 |
|---|---|---|
| ARDY Core8 standalone seed0 | テキスト・音声なし、CPU、10 diffusion steps、3秒 | load 1.06秒、推論9.88秒、first result 10.94秒 | 60 frames / 20fps / Core27、元NPZとJSON |
| ARDY 共通API `cfc9aaf72a0944cf8449a978df8d5e29` | 無条件CPU診断、seed0 | 推論 19.72秒（このAPI実行） | [元NPZ](../outputs/cfc9aaf72a0944cf8449a978df8d5e29/original.npz)、[JSON](../outputs/cfc9aaf72a0944cf8449a978df8d5e29/motion.json)、[MP4](../outputs/cfc9aaf72a0944cf8449a978df8d5e29/video.mp4) |
| Kimodo 公式standalone wave | Raise your right hand and wave for three seconds. / official remote GPU | 生成通知まで2.59秒、取得まで8.62秒 | 90 frames / 30fps / SOMA77、実NPZ取得 |
| Kimodo 公式standalone bow | Bow, then raise both arms. / 同seed0・同3秒 | 生成通知まで2.62秒、取得まで8.56秒 | 90 frames、入力変更により関節位置が変化 |
| Kimodo 共通API `9c59514de11744aeb0a97038e73c7e5d` | wave / NVIDIA official Space | 生成通知まで 2.37秒 | [元NPZ](../outputs/9c59514de11744aeb0a97038e73c7e5d/original.npz)、[JSON](../outputs/9c59514de11744aeb0a97038e73c7e5d/motion.json)、[MP4](../outputs/9c59514de11744aeb0a97038e73c7e5d/video.mp4) |

ARDY standalone seed0/1の最大関節座標差は0.864m、Kimodo同seed・異なる入力の差は0.828m。これは出力差の検査で、意味的一致や自然さのスコアではありません。実行時間はCPU/外部GPU・条件・処理範囲が違うため、優劣のbenchmarkに使いません。

Kimodoの時間には外部テキストエンコーディングと通知通信が含まれます。公開Space runtimeが報告するGPUはl40sx1。実行コンテナー内部のGit SHA・checkpoint SHA・peak VRAMは観測不能なのでnull。公式SpaceのGit revisionとGUIモデル名は保存。ローカルGPU実測と区別します。

JSONメタデータ: [ardy_cpu_result.json](ardy_cpu_result.json)、[kimodo_api_result.json](kimodo_api_result.json)、[入力変更比較](kimodo_input_comparison.json)。元データと動画はGit管理外ですが現在のworkspaceに保存されています。

## UI・テスト

- 3Dスケルトン／簡易アバター、カメラ回転・zoom、再生・停止・pause、seek、速度、原ファイル／JSON／MP4取得を実装。
- 実生成したKimodoとARDYを同じ画面に並べ、再生を操作。[実生成ビューアー画像](actual-motion-viewer.png)とlogs/actual-viewer.logに記録。
- WAVのアップロード・型／duration検証、audio.currentTime同期、seek/rate/pause、MP4 audio muxを検査。同期はモデルによるaudio conditioningの成功ではない。
- 同じ入力で複数モデルへジョブ投入。異常・未準備モデルを個別に拒否、推論失敗後も次のモデルを実行。現在のA/Bは準備不足で拒否。
- JSON/BVH/明示関節付きNPZの変換、元データ保持、軸・単位・root・階層検証。未知SMPL-Xパラメーターを位置配列として扱わない。
- **pytest: 36 passed / 0 failed / 0 skipped**。test doubleと人工fixtureによるサービス契約検査は、学習済みモデルの実推論結果とは別。
- **Chromium / Playwright: 4 passed / 0 failed / 0 skipped**。0-test runは成功証拠として採用しない。最終XMLとtest_summary.jsonに件数を保存。
- アプリの保存済みsetupを再実行し、pip checkとnpm ciを確認。ARDYの固定source/CPU lockを再実行、公式CLI起動とrefresh後の実denoisingを確認。
- primary app sourceはこの依頼で実装。9公式repoのtracked diffは空。

## 失敗・診断・解決策

| 操作 | 観測した問題 | 対応と現在の状態 |
|---|---|---|
| 初回HF metadata / artifact取得 | proxy tunnel HTTP403。HubとCDN/Spaceは別host。 | 必要hostをdraftへ追加。後の再試行でAPIとus.aws.cdn.hf.coへのHTTP200、ARDY全量SHA照合に成功。初回ARDY CLIの60秒timeoutはログ保存。 |
| ローカルLlamaエンコーダー | meta-llama/Meta-Llama-3-8B-Instruct configへHTTP401、gated=manual。token/file binding不在。 | HF_TOKENを個人用要件としてdraftに宣言。Llamaアカウント承認とsecure設定入力が残る。tokenをchat/sourceへ保存していない。 |
| 公式Kimodoブラウザprobe | proxy CAをChromiumが認識せずERR_CERT_AUTHORITY_INVALID。 | 証明書検証を無効化しない。CAを検証するPython SSL経由の公式Viser protocolで推論・Downloadを実行。共通ローカルThree.jsビューアーはChromiumで検証済み。 |
| 公式Viser protocol初回 | client version unknown→1002 Version mismatch。 | installed official forkとserverが示すviser-v1.0.16に合わせた。protocol変更時はエラーとして扱う。 |
| splittext timeline編集 | 最後のprompt削除後に再生成され、空prompt待機timeout。 | 既存promptをupdate/resize。指定textとframe数のserver ackを検査する。 |
| 公式demo Generateの初期状態 | serverがOnly one motion allowed for constrained generationを通知。 | 公式01_single_text_promptを先にLoad Example、1 sampleを指定、constraintsをclear、自分のpromptへ変更してからGenerate。以後2入力と共通APIで成功。上流コードを書き換えていない。 |
| LoM v1 | GPU不在、SMPL-X/FLAME未取得。現在requirementsのtransformersはv2用。 | v1/v2非互換、Python3.10・fairseq旧制約を報告。v1 demoをCPUで動くと仮定しない。TLS無効化を含むbuild_resources.shは実行しない。 |
| 会話／音声モデル | CUDA・公開資産／gatedモデル・利用許諾が不足。 | 各adapter/互換性/GPU手順に記録。人工動作へ置換しない。 |

## Stage 3のために必要な外部資源

CUDA搭載Linux環境、対象モデルの公開重みと付随data、正規取得・規約同意済みSMPL-X/FLAMEが必要です。LLM-GestureやローカルARDY/Kimodoには該当Llamaアクセス承認とHF_TOKENも必要。GPU再現手順は docs/gpu_setup.md。今回、有料GPUの作成・起動・課金処理は行っていません。

共通アプリとC/CPU診断は動作しますが、A/Bを含む全モデルの環境完了は宣言しません。環境config draftの保存は公開・新タスク復元・新タスクでの検証とは別です。

Google Drive の公式配布folder（LLM-Gesture / FreeTalker）のHEADは現在のproxyでHTTP403でした（drive_checks.json）。これらを追加導入する場合は drive.google.com と必要に応じた実download hostの接続設定、GPU・data・licenseの確認が必要です。現在のKimodo/ARDY経路には不要なので、未使用のDrive許可を追加していません。

追加検証: 再接続時の初期GUI応答timeoutを観測。公式の同時利用queueと初期化待ちを考慮し、待機上限150秒、server noticeとconnection errorの伝達を追加しました。接続数／セッション制限を迂回せず、後の再試行で90frameの実生成と、欠けていたruntime.jsonの初期化に成功（setup_config_initialization.json）。既存依存を保持した設定初期化検査であり、新task snapshot復元の検証ではありません。PAUSEDのSpaceには接続せず、GPUを起動・再開しないことを単体テストで検証しました。
