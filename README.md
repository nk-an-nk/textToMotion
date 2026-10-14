# Motion Lab / textToMotion

公開モデルの3D人体動作を生成し、ブラウザで再生・比較・保存する Python 研究アプリです。

- **Kimodo**: NVIDIA 公式オンラインデモで動作指示 → 実推論成功。異なる2入力、元 NPZ、SOMA77 関節、共通3D表示を確認。
- **ARDY**: 公開重みを SHA-256 照合し CPU で実推論成功。ただし **無条件診断のみ**。テキストや音声への対応成功ではありません。
- **text-to-vrma（ARDY）**: 公式ARDYエンジンとVRMA出力を比較経路に追加。同じARDY重み・CPUテキスト処理を共有。研究室GPUでの実生成は未検証です。
- **会話／音声条件付きジェスチャー**: 未成立。CUDA GPU・許諾済み SMPL-X 等が不足しています。未実装モデルを動作済みと表示しません。

[モデル互換性](reports/model_compatibility.md)、[実行結果と未達条件](reports/execution_results.md)、[環境調査](docs/environment.md)、[ライセンス](reports/licenses.md) を参照してください。

## 生成済み MP4

検証動画をリポジトリに収録しています。GitHub のファイル画面で再生できない場合は **Download raw file** で取得してください。

- [Kimodo：右手を上げて振る指示から生成](reports/videos/kimodo-wave.mp4) — 3秒、30fps。
- [ARDY：CPU 無条件診断](reports/videos/ardy-unconditional.mp4) — 3秒、20fps。テキスト・音声による指示はありません。

どちらも実モデルが出力した関節位置をスケルトン表示した動画で、音声はありません。[動画の出典と検証値](reports/videos/README.md) を参照してください。

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
