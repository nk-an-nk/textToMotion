# Motion Lab / textToMotion

公開モデルの3D人体動作を生成し、ブラウザで再生・比較・保存する Python 研究アプリです。

**[MoLingo・ReMoMask-2・MoMaskの追加実験](reports/masked-models-20261016/README.md)**：LLMで発話を英訳してから、共通5区間と生徒→先生の音声会話を2環境で検証しました。[全12本のデモ一覧](reports/masked-models-20261016/index.html)・[生成時間とRealtimeとの差のCSV](reports/masked-models-20261016/summary.csv)・[再現手順](docs/masked_models.md)。研究室側の代替はRTX 4090 / PyTorch VRAM上限12GB / CPU8で、RTX 5070実機の測定ではありません。

**[報告用PowerPoint更新版（49枚・全60本の動画を埋め込み）](reports/presentation-20261016-updated/textToMotion_experiment_report_20261016_updated.pptx)**：従来30枚に、MoLingo・ReMoMask-2・MoMaskの英訳入力・2GPU比較を追加しました。[閲覧用PDF](reports/presentation-20261016-updated/textToMotion_experiment_report_20261016_updated.pdf)・[全動画一覧](reports/presentation-20261016-updated/index.html)・[資料の使い方](reports/presentation-20261016-updated/README.md)。[旧30枚版](reports/presentation-20261016/README.md)も保持しています。

**[B300でKimodoの上半身会話デモを追加](reports/kimodo-b300-20261015/README.md)**しました。[通常100ステップ](reports/kimodo-b300-20261015/video-fp32-100/demo.mp4)と[高速20ステップ](reports/kimodo-b300-20261015/video-tf32-20/demo.mp4)を、実音声入力からの時間表示付きで比較できます。常駐生成の中央値は約1.89秒／0.43秒、Realtime初音声から骨格受信までの実測差は約4.37秒／3.25秒でした。

**[音声入力から7モデルを比較](docs/audio_input_comparison.md)**しました。生徒の「先生、こんにちは！」をRealtimeへ音声で送り、教師の返答から新規生成する時間を計測しています。Kimodo、ARDY、MotionLCM、MoMask、MMM、ReactMotion、MaAIの正面1080p動画・CSVは[検証結果](reports/model-comparison/runpod-20261014/README.md)にまとめています。

**日本語音声対話・VRM画面を追加しました。** Realtime GAのWebRTC接続、音声書き起こし、非同期ジェスチャー生成、VRM/VRMA再生、期限・割り込み制御、計測CSVを実装しています。Realtime API音声と新規Kimodo・ARDY動作によるオフライン分割動画を収録しています。ライブWebRTC会話と新規ジェスチャー推論を組み合わせたE2Eは未検証です。[導入手順](docs/conversation_vrm.md)・[検証結果](reports/dialogue_validation.md)・[状態／シーケンス図](docs/dialogue_architecture.md)を参照してください。

Windowsで対話アプリのみを準備して、オフライン検証を起動する場合:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup-conversation.ps1 -InstallPrerequisites
powershell -NoProfile -ExecutionPolicy Bypass -File .\start-conversation.ps1
```

研究室PCのブラウザで `http://127.0.0.1:8765/conversation` を開き、利用条件を確認した無料VRM 1.0を選択してください。実Realtimeを使うときは起動に `-EnableRealtime -BudgetUsd 3` を追加し、OpenAI APIキーを非表示入力します。Codexへのログインとは別のAPI認証・課金です。GPUモデルの導入は既存のWindowsセットアップを使用します。

- **Kimodo**: NVIDIA公式オンラインデモと、RunPod B300上の常駐CUDA推論を確認。音声入力からの上半身会話動画、元NPZ、SOMA77関節、生成時間を保存しています。
- **ARDY**: 公開コミュニティサービスのHorizon40で、動作指示から5区間を新規生成し、音声付きVRM動画を出力。[動画・入力からの生成時間](reports/segmented/english-lesson-ardy/README.md)。ローカルCore8はLLM2Vec CPU＋CUDAで今回の同一5文・教師返答を生成成功。旧CPU無条件診断も別途保持しています。
- **text-to-vrma（ARDY）**: 公式ARDYエンジンとVRMA出力を比較経路に追加。同じARDY重み・CPUテキスト処理を共有。研究室GPUでの実生成は未検証です。
- **音声条件付きモデル**: MaAIの聞き手うなずき予測をCUDAで実行しました。話者の全身Co-Speechモデルは未成立で、許諾済み SMPL-X 等が不足しています。今回の対話画面は発話内容を英語の動作指示へ変換する経路で、音声条件付き学習モデルの推論成功ではありません。

[モデル互換性](reports/model_compatibility.md)、[実行結果と未達条件](reports/execution_results.md)、[環境調査](docs/environment.md)、[ライセンス](reports/licenses.md) を参照してください。

## 生成済み MP4

検証動画をリポジトリに収録しています。GitHub のファイル画面で再生できない場合は **Download raw file** で取得してください。

- [英語学習：5区間それぞれで音声・Kimodoジェスチャーを新規生成して同期・連結](reports/segmented/english-lesson/combined.mp4) — 正面1080p / 30fps / 音声付き。[個別5本と時間](reports/segmented/english-lesson/README.md)・[独立した実装の使い方](docs/segmented_dialogue.md)。従来版も保持しています。
- [英語学習：同じ5区間をARDYで新規生成して同期・連結](reports/segmented/english-lesson-ardy/combined.mp4) — 同じ音声・発話文・動作指示・seedで比較。[個別5本と入力→生成時間](reports/segmented/english-lesson-ardy/README.md)・[ARDY実行手順](docs/ardy_segmented.md)。
- [Kimodo：右手を上げて振る指示から生成](reports/videos/kimodo-wave.mp4) — 3秒、30fps。
- [ARDY：CPU 無条件診断](reports/videos/ardy-unconditional.mp4) — 3秒、20fps。テキスト・音声による指示はありません。

上記の3秒のKimodo・ARDY動画は、実モデルが出力した関節位置をスケルトン表示した動画で、音声はありません。[動画の出典と検証値](reports/videos/README.md) を参照してください。

## セットアップと起動

**研究室のWindows PC（RTX 5070 / VRAM 12GB / RAM 32GB）**では [Windows用の実行手順](docs/windows_lab.md) を使ってください。PowerShellから仮想環境・CUDA 12.8版PyTorch・モデル導入・実生成とMP4検査をまとめて実行します。WSL2は不要です。Windows実機での検証は未実施です。

Python 3.11+、Node.js/npm が必要です。動画には FFmpeg、ブラウザテストには Chromium が必要です。Python 依存と Three.js はローカルに導入し、CDN に依存しません。

```bash
cd /workspace/textToMotion
bash scripts/setup.sh
export MOTION_LAB_DATA=/workspace/shared/motion-lab
source .venv/bin/activate
python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

ローカル端末のブラウザで `127.0.0.1` のポート `8765` を開きます。クラウドのオンボーディング画面は localhost プレビューを提供しません。必要ならご自身の開発クライアントのポート転送機構を使ってください。バインドは原則 loopback のままにします。

別端末で機能確認:

```bash
curl --fail http://127.0.0.1:8765/api/health
.venv/bin/python scripts/smoke_test.py
```

デフォルト smoke は人工サンプルの入出力検査です。実モデル推論の確認は `--model kimodo` を明示します。アプリの起動成功とモデルの準備状況は区別します。

新しいローカル環境では checkout の絶対パスを読み替えてください。このクラウドタスクは隔離済みなので、通常は既存 checkout を使い、Git worktree を作りません。

## 最初の実生成

準備済み環境では **Kimodo / 動作指示** を選び、英語の指示を入力して生成します。

```text
Raise your right hand and wave for three seconds.
Bow, then raise both arms.
Walk forward, stop, and bow.
```

この経路は **NVIDIA 公式オンラインデモ**へ入力文を送信します。ローカル GPU や有料クラウドの起動は行いません。サービスの稼働・通常の5分セッション制限・Viser 1.0.16 プロトコルに依存し、1回10秒以内に制限します。

新規環境で公式オンライン経路を準備するには:

```bash
export MOTION_LAB_DATA=/workspace/shared/motion-lab
.venv/bin/python scripts/setup_models.py --models kimodo --clone
.venv/bin/python scripts/kimodo_online.py "Raise your right hand and wave." \
  --duration 3 --seed 0 --output "$MOTION_LAB_DATA/kimodo-check.npz"
```

公式成功通知と実 NPZ の取得後、`$MOTION_LAB_DATA/runtime.json` の kimodo 節を設定し、サーバーを再起動します。準備済みクラウドには保存しています。

```json
{"kimodo": {"backend": "official_demo", "online_validated": true}}
```

```bash
.venv/bin/python scripts/smoke_test.py --model kimodo
```

公式初期モーションを読み込んだ後、自分の指示へ更新し、既存 constraints を消し、Generate → Download を実行します。読み込みだけを推論成功とは扱いません。失敗時はエラーを記録し、人工サンプルへ置き換えません。

日本語では「モデルへ渡す英訳」を入力してください。自動翻訳は未導入です。元文と指定した英訳を両方保存します。

## 3D再生・比較・保存

- 一覧のチェックボックスで複数結果を選択。骨格階層を保持して同じ画面に並べます。
- ドラッグで回転、ホイールで zoom、右ドラッグで移動。
- 再生／停止／一時停止、timeline seek、0.5–2倍速度。
- 骨格／簡易アバター切り替え。アバターは骨間の円柱で、SMPL-X/SOMA 人体メッシュではありません。
- WAV を同期用または音声入力としてアップロード。audio.currentTime を master clock に再生・seek・速度を同期します。
- 元 NPZ、変換 JSON、実験記録を取得。「動画を作成」で MP4 を生成し、音声があれば mux します。
- 「骨格まで」「MP4まで（合計）」の秒数を表示。「時間をCSVで取得」で入力と測定値を保存できます。
- 同一入力で複数モデルを順番に実行し、失敗を個別に記録します。会話／音声モデルの実推論は現在未成立です。

「ビューアー検証用サンプル」は人工アニメーションです。モデル選択に含めず、画面・実験一覧に **推論ではない**と表示します。音声との同期検査を co-speech 生成成功とは数えません。

研究室PCでは、短い発話5通りと中程度の発話5通りを [一括実行して3経路を比較](docs/windows_lab.md#発話文10通りの生成時間比較) できます。元日本語と指定英訳を保存し、ARDYには発話文の英訳をそのまま渡します。

[モーション形式・座標・評価](docs/motion_format.md) に JSON / NPZ / BVH、原データ保持、root、未知形式の拒否、評価値の意味を記載しています。SMPL-X poses を関節位置と仮定しません。

## ローカル ML モデルと GPU

[GPU 再現手順](docs/gpu_setup.md) に専用 venv、実行した依存 lock、公式コマンド、LoM v1/v2 非互換性、CUDA・データ・ライセンス条件を記載しました。

**ARDY CPU 無条件診断は準備済み**です。ARDY を選ぶと専用ボタンが表示されます。通常の動作生成は gated Llama encoder が必要で、診断へ自動フォールバックしません。

認証はクラウド環境設定の `HF_TOKEN` に安全に登録します。Llama モデルのアクセス承認は別途必要です。SMPL-X/FLAME は正規の登録・規約同意を行い、ソースに認証値を保存しません。

## テスト

```bash
.venv/bin/python scripts/doctor.py --torch-python "$MOTION_LAB_DATA/envs/ardy/bin/python"
.venv/bin/python -m pytest -q
CHROMIUM_PATH=/usr/bin/chromium npm run test:browser
```

Python は座標変換／BVH FK／shape・循環・NaN／WAV 異常入力／比較の失敗分離／原データ保持／MP4・音声 stream を検査します。Chromium は実際の WebGL カメラ操作、再生・seek・速度、音声同期、取得、取り込み・比較を操作します。test double の成功を学習済みモデルの成功と扱いません。

依存は `requirements-app.lock` / `package-lock.json` に固定。各モデルの ML 依存と巨大な重みはアプリ setup に含めません。モデル用 venv は `MOTION_LAB_DATA/envs/<model>` に分離します。

## 構成

```text
app/        FastAPI、実験保存、変換、動画、ブラウザUI
adapters/   独立モデルアダプター、準備状況
scripts/    調査、固定ソース導入、公式推論／変換／smoke
configs/    コミット台帳、runtime例、ARDY CPU依存lock
tests/      PythonとChromiumブラウザテスト
docs/       環境、GPU、形式
reports/    互換性、実行結果、ライセンス、検証証拠、videos/ の MP4
outputs/    元モーション、正規化JSON、動画、実験記録（Git管理外）
```

日常の生成結果は `outputs/` に保存し、Git に自動追加しません。検証用 MP4 の2本は `reports/videos/` に収録しています。重みは Git 管理外です。既存 `.devcontainer/devcontainer.json` は公式 Universal `6.1.9-noble` を指定する Codespaces 設定です。本クラウドタスクでは、そのコンテナーを起動せず提供された Linux 環境で検証しています。
