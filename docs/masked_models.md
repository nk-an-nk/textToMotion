# MoLingo・ReMoMask-2・MoMaskの英訳入力による比較

結果・全12本の動画は [reports/masked-models-20261016](../reports/masked-models-20261016/README.md) を参照してください。従来の日本語直接入力の結果も残しています。

## 入力と計測範囲

元の発話は音声と字幕に使い、LLMの忠実な英訳だけを動作モデルに渡します。動作指示文への書き換えはしません。共通5区間の原文・英訳・翻訳時間・LLM応答情報は [比較設定](../configs/masked_comparison_20261016.json) に保存しています。英語だけの区間も同じ文のままです。

会話では生徒の実音声をRealtimeへ送り、実際に受信した教師の全文を毎回新規に英訳します。モデルは生徒音声の送信前に常駐させます。`measure_masked_model_dialogue.py` が、発話終了から骨格受信までを同じクライアント時計で測定します。APIキーは制御側クラウドの `realtime` / `OPENAI_API_KEY` 環境変数から読み、GPU Podへ送りません。

`llm_translate_motion.translate(text)` はRealtimeのテキスト出力を使います。今回の環境では同じシークレットがRealtime WSSで利用できた一方、Responses RESTでは認証されなかったため、この経路を採用しています。翻訳ごとに独立接続するので、翻訳秒数に接続時間も含まれます。キーをコマンド引数やチャットに貼らないでください。

動作本体はFP32、TF32無効です。CLIPには公式実装のFP16を併用し、MoLingoのT5はFP32です。

## GPU内の実行

Ubuntu 24.04 / Python3.12、PyTorch2.8.0+cu129を利用しました。ソース・重みの固定情報は [asset manifest](../configs/masked_assets_20261016.json)、実導入版は各環境の `versions.txt` です。MoLingoにはHumanML3Dの263次元版と、元のデータセットのMean.npy/Std.npyが必要です。MoMaskのVQ訓練用に変更されたstdで代用しません。263次元版ではSMPLモデルを使いません。

保持中のPodをRunPod Consoleで再開した場合、GPU在庫と料金を確認し、JupyterのTerminalで次を実行します。

```bash
bash /workspace/retained/resume.sh
```

永続ボリューム内の公式アーカイブを検証・再展開し、`/tmp/masked_runtime` に仮想環境、固定ソース、重みを再構成します。仮想環境とソースの実体も `runtime-environment.tar.gz` に保存しています。最新の実験コードは `bootstrap/project` と `latest-experiment-code.tar.gz` を優先してください。初回のlab側アーカイブ中のprojectは英訳対応前ですが、`resume.sh` は更新済みbootstrapからコードをコピーします。

GPU内で3モデルのうち1つを実行する例です。既存の結果ディレクトリを指定すると停止するので、新しい名前を使います。

```bash
RUNTIME=/tmp/masked_runtime
"$RUNTIME/venv/bin/python" "$RUNTIME/project/scripts/benchmark_masked_models.py" \
  --model momask --repo "$RUNTIME/upstreams/momask" \
  --weights "$RUNTIME/checkpoints/momask/t2m" \
  --config "$RUNTIME/project/configs/masked_comparison_20261016.json" \
  --output /workspace/retained/results/retest/momask \
  --profile lab_proxy --cpu-threads 8 --repeats 3 --serve
```

他モデルは `--model` / `--repo` を変更し、`--weights` にそれぞれ `$RUNTIME/weights/molingo`、`$RUNTIME/weights/remomask2` を指定します。B300では `--profile b300` を使います。1プロセスずつ実行し、`RESIDENT_READY` 後に会話を測定します。ポート8766はGPU内loopbackだけで待ち受けます。3モデルとも全身22関節を生成し、上半身の表示は推論後に行います。

## 制御側クラウドで会話を測定

実験を作成したときのprivate stateとJupyter認証ファイルは `.motion-lab/masked-models-20261016/PROFILE/` に保持しています。認証ファイルをGitへ追加しないでください。

```bash
.venv/bin/python scripts/measure_masked_model_dialogue.py \
  --state .motion-lab/masked-models-20261016/lab_proxy/state.json \
  --auth .motion-lab/masked-models-20261016/lab_proxy/auth.json \
  --student-wav reports/kimodo-b300-20261015/dialogue-fp32-100/student.wav \
  --output outputs/retest-dialogue-momask --model momask --profile lab_proxy
```

状態ファイルの `stop_confirmed` は実験時の記録です。再開時はRunPod側の実状態も確認し、再開したPodをwatcherが直ちに期限切れと判断しないように、別の検証用状態・予算・期限を設定してください。以前の期限を無断で延長する処理は行いません。

## 動画化

モデル推論が終わったらGPUは停止できます。動画化は制御側のMotion LabとPlaywright、FFmpegで行います。VRM本体は別途ライセンスに従って用意し、Gitへ追加しません。

共通5区間の新規骨格に保存済みの実音声を合わせる例:

```bash
.venv/bin/python scripts/assemble_comparison.py \
  --config configs/masked_comparison_20261016.json \
  --motion-root reports/masked-models-20261016/lab_proxy/native/momask \
  --speech-root reports/model-comparison/runpod-20261014/common/momask/segments \
  --output outputs/momask-common --model momask --allow-llm-translation
node scripts/export_segmented_dialogue.cjs \
  --manifest outputs/momask-common/manifest.json --avatar /path/to/avatar.vrm \
  --output outputs/momask-common/combined.mp4 --upper-body
```

会話は `prepare_audio_dialogue_video.py --root MEASUREMENT_DIR --output VIDEO_DIR`、次に `export_upper_body_dialogue.cjs --plan VIDEO_DIR/plan.json --avatar AVATAR --output VIDEO_DIR/dialogue.mp4` を使います。Motion Labを `127.0.0.1:8765` で起動しておいてください。保存済みの6組のplanがある場合は `render_masked_models.py --profile lab_proxy --avatar AVATAR --jobs 2` で一括出力できます。`--resume` は同名動画のSHA256を検証して完了分をスキップします。

## 新しいPodを作成するとき

今回の実行は [runpod_retained_experiment.py](../scripts/runpod_retained_experiment.py) で作成しました。`credit-budget-private.json` の `retained_storage_reserve_usd` に停止後保持する領域の予算を確保し、APIの現在残高内でのみGPUを作成します。自動入金は行いません。作成には実課金が伴うため、今回の再現だけなら新規作成をせず保持した環境を確認してください。

GPUへ渡す小さなbootstrapは次で再作成できます。重みやAPIキーは含めません。MoMaskアーカイブは前回の検証で作ったSHA256一致の束を使用します。

```bash
.venv/bin/python scripts/prepare_masked_bootstrap.py \
  --normalization /path/to/original/HumanML3D \
  --momask-archive .motion-lab/runpod-weight-cache/momask-weights.tar.gz \
  --output outputs/new-bootstrap.tar.gz
```

JupyterのFiles APIまたはTerminalを通じ、bootstrapを `/workspace/retained/bootstrap/` に展開し、MoMaskアーカイブを `/workspace/retained/assets/momask-weights.tar.gz` へ置きます。その後 `python /workspace/retained/bootstrap/remote_setup.py` を実行します。公開公式URLから取得する他の重みはサイズ・SHA256を検証します。ソースの研究・非商用条件、HumanML3D等の別途条件に従ってください。

## 停止と24時間保持

今回用意したPodだけを停止するコマンド:

```bash
.venv/bin/python scripts/runpod_retained_experiment.py \
  --root .motion-lab/masked-models-20261016 stop --profile lab_proxy
.venv/bin/python scripts/runpod_retained_experiment.py \
  --root .motion-lab/masked-models-20261016 stop --profile b300
```

`stop` はGPUを解放し、永続領域を残します。`terminate` / `DELETE` は保持データを削除するため、保持期間中は使いません。24時間後のcleanupを継続するには、制御側で次のwatcherを動かします。保持用stateとJupyter認証の控えは、チェックアウト外の `/workspace/shared/motion-lab/retained-experiments/masked-models-20261016/` にもアクセス権を限定して保存しています。現在のwatcherはこの共有側stateを使用しています。

```bash
.venv/bin/python scripts/runpod_retained_experiment.py \
  --root /workspace/shared/motion-lab/retained-experiments/masked-models-20261016 watch
```

watcherは期限または保持用残高の閾値でGPUを停止し、停止から24時間後に自身の作成したPodだけを削除します。このクラウド環境が停止すると実行も止まるため、RunPod Consoleでも保持期限を確認してください。保持期限を超えたPodの再開や削除は、先にwatcherとの整合を確認してから行います。
