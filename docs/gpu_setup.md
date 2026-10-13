# モデル環境と GPU 再現手順

このクラウドインスタンスは NVIDIA GPU を持ちません。以下の CUDA 手順は GPU 搭載 Linux で実行するために用意したもので、このインスタンスでの CUDA 推論成功を示すものではありません。有料 GPU の作成・起動処理は含みません。

## いま実行できる経路

- **Kimodo**: 既に稼働している NVIDIA 公式オンラインデモに接続。ローカル GPU / Llama トークンは不要。外部へ入力文を送信します。通常のデモ制限と Viser 1.0.16 プロトコルに依存します。実推論・元 NPZ 取得・正規化・共通 UI 再生を確認しました。
- **ARDY**: CPU 版 PyTorch、公開 Core8 重み、公式の空テキスト表現で無条件診断。**会話・音声・動作指示への適合性の検証には使えません**。公式 v1 checkpoint の SHA-256 照合済み。
- **ARDY / Kimodo のローカル言語条件付き推論**: `meta-llama/Meta-Llama-3-8B-Instruct` の承認と Hugging Face 認証が必要です。モデルごとの venv を使い、transformers 5.8.1 と 5.1.0 を同じ環境へ入れないでください。

## CPU 環境の再現（ARDY、実行検証済み）

アプリの `scripts/setup.sh` を実行済みのリポジトリルートで:

```bash
export MOTION_LAB_DATA=/workspace/shared/motion-lab
.venv/bin/python scripts/setup_models.py --models ardy --clone --install --device cpu --demo
# NVIDIA Open Model License を確認した後に実行する:
.venv/bin/python scripts/setup_models.py --models ardy --download --accept-model-license --max-download-gb 1

"$MOTION_LAB_DATA/envs/ardy/bin/python" scripts/diagnose_ardy.py \
  --checkpoints-dir "$MOTION_LAB_DATA/checkpoints/ardy" --duration 3 --seed 0 \
  --output "$MOTION_LAB_DATA/official-attempts/ardy-unconditional.npz"
"$MOTION_LAB_DATA/envs/ardy/bin/python" scripts/export_official.py \
  --family ardy --input "$MOTION_LAB_DATA/official-attempts/ardy-unconditional.npz" \
  --output "$MOTION_LAB_DATA/official-attempts/ardy-unconditional.json"
```

`configs/requirements-ardy-cpu.lock` は実際に動作した依存バージョンです。PyTorch は別途 CPU index から 2.9.0 を導入し、公式 Git コミットのパッケージをビルドします。CMake 3.31.6 / C++17、公式ビルドの並列度4を使用します。既存の異なるコミットへ reset しません。

共通 UI の ARDY を選ぶと「ARDY 無条件CPU診断」ボタンが表示されます。通常の「生成」は言語条件付き経路の準備確認を行い、診断への自動フォールバックはしません。

## Linux + NVIDIA CUDA（未実行）

まず `nvidia-smi` と PyTorch の CUDA 行列演算を実行して利用可能な GPU / VRAM を確認してください。Python 3.12、C++17 コンパイラーを使用します。

```bash
export MOTION_LAB_DATA=/workspace/shared/motion-lab
.venv/bin/python scripts/setup_models.py --models ardy --clone --install --device cuda --demo
"$MOTION_LAB_DATA/envs/ardy/bin/python" -c \
  'import torch; assert torch.cuda.is_available(); x=torch.ones(2,2,device="cuda"); print((x@x).cpu()); print(torch.cuda.get_device_name(0))'

# Kimodo は transformers の版が違うので専用環境へ別途導入する:
.venv/bin/python scripts/setup_models.py --models kimodo --clone --install --device cuda --demo
```

installer の CUDA build は PyTorch 2.9.0/cu126。GPU ドライバーがこれを利用できることを事前に確認してください。TensorRT は導入しません。GPU 手順の依存解決・実推論はこの CPU インスタンスでは未検証です。モデル公式は別バージョンの CUDA 手順も提供しています。

### Llama エンコーダーと保存容量

1. [公式 Llama ページ](https://huggingface.co/meta-llama/Meta-Llama-3-8B-Instruct) で条件を確認し、アカウントのアクセス承認を受けてください。
2. クラウド環境設定の `HF_TOKEN` に読み取りトークンを安全に登録してください。ソース・チャット・ログへ値を貼り付けません。ローカル端末では Hugging Face の公式認証手段を使ってください。
3. 8B backbone の safetensors は約16GBです。API のリポジトリ合計約32GBには **original PTH と safetensors の重複**が含まれます。whole snapshot で両方を取らず、Transformers の `from_pretrained` に必要な形式だけを取得してください。LLM2Vec adapters は別です。
4. 公式公開 diffusion checkpoint は ARDY Core8 約765MB、Kimodo SOMA v1.1 約1.13GB。`setup_models.py --download` はモデルカード・総量・空き容量を確認し、公開 LFS SHA-256 を照合します。巨大な言語エンコーダーを自動取得する install script は保存していません。

`$MOTION_LAB_DATA/runtime.json` を `configs/runtime.example.json` に沿って設定します。ARDY の `checkpoint_dir`、Kimodo の `checkpoint_cached`、双方の `text_encoder_cached` は、必要資産を実際に取得・確認してから設定してください。フラグだけで未取得の資産を準備済みと扱わないでください。Kimodo をローカル実行する場合は `backend` を `local` にします。

公式単体コマンド（リポジトリを変更しない）:

```bash
cd "$MOTION_LAB_DATA/upstreams/ardy"
TEXT_ENCODER_DEVICE=cpu TEXT_ENCODER_MODE=local \
  "$MOTION_LAB_DATA/envs/ardy/bin/python" scripts/generate.py \
  "Raise your right hand and wave for three seconds." --model core8 --duration 3 --seed 0 \
  --no-postprocess --checkpoints_dir "$MOTION_LAB_DATA/checkpoints/ardy" \
  --output "$MOTION_LAB_DATA/official-attempts/ardy-text.npz"
# 公式インタラクティブ再生（バインド設定は公式実装を確認する）:
"$MOTION_LAB_DATA/envs/ardy/bin/python" scripts/visualize.py "$MOTION_LAB_DATA/official-attempts/ardy-text.npz"

cd "$MOTION_LAB_DATA/upstreams/kimodo"
TEXT_ENCODER_DEVICE=cpu "$MOTION_LAB_DATA/envs/kimodo/bin/python" -m kimodo.scripts.generate \
  "Walk forward, stop, and bow." --model kimodo-soma-rp-v1.1 --duration 6 --seed 0 --no-postprocess
```

通常の推論を先に公式単体コマンドで確認し、その後共通 UI のアダプターを有効にします。CPU でエンコーダーを動かす設定は公式が提供していますが、この環境では gated backbone を取得できず、**言語条件付きのローカル成功は未検証**です。

## The Language of Motion v1 / v2

確認した公式コミット: `f238afba0cb6e32df7bc15c974ff2ece109892e3`。

- v1 の公開 LM / VQ 重みは `JuzeZhang/language_of_motion`（revision は reports/huggingface_checks.json）。T2M / A2M LM は各約1GB、VQ は別ファイルです。
- 公式 v1 は Python3.10 / torch2.4.0-cu121。`numpy==1.23.1` は Python3.12 と不整合です。v1/turbot5 は `transformers==4.49.0` を使います。
- 現在の upstream requirements は v2 向け `transformers==5.12.1` を含みます。v1用 constraints と両立しないので、そのまま一括インストールしません。GPU 上で専用 Python3.10 環境を作り、upstream README の v1 指示に従い、依存マニフェストのコピーを公式リポジトリの外へ作って v1版へ変更します。元の requirements / lockfile / コードは変更しません。
- fairseq の古い OmegaConf/Hydra 制約と、README の新版への上書き手順は整合性に注意が必要です。本インスタンスではこの環境の導入・推論は未実行です。環境の準備完了とは扱いません。
- v1 デモは `.cuda()` を直接呼び、CPU に config を変えるだけでは動きません。SMPL-X/FLAME は正規サイトで利用条件に同意して取得してください。値をコードへ保存しません。
- `build_resources.sh` には TLS 検証を無効化するダウンロード行があります。そのスクリプトは実行していません。資産は公式サイトから通常の TLS 検証で取得してください。
- v2 は GLM4-Voice 16384 audio tokens / decoder-only Qwen3 等。v1 の HuBERT500 / T5 encoder-decoder checkpoint は **互換ではありません**。v2 の release `LoM-a2m-4part` は別途資産・config・shape照合が必要です。v1重みを v2へ流用した成功とは扱いません。

確認した公式デモ:

```bash
python demo.py --cfg configs/demo_text2motion.yaml --text examples/text2motion.txt --task text2motion --render
python demo.py --cfg configs/demo_cospeech.yaml --audio examples/2_scott_0_111_111.wav --task cospeech --render
```

共通アダプターは `--cfg_assets` 用のジョブ別 overlay を checkout 外へ作成します。v1 の GPU・fairseq・VQ/LM/T5/HuBERT・許諾済み SMPL-X/FLAME を確認し、runtime.json に `assets_confirmed` と body model の実在パスを設定するまで実行を拒否します。

## 音声連動: StreamTalk / MIBURI

**StreamTalk** は公式に CUDA 必須。Python3.9 / torch2.0 / CUDA11.8 専用環境、WavLM、許諾済み SMPL-X、BEAT2 speaker retrieval database が必要です。公式 README の checkpoints verifier を実行してください。公開重みのカードは MIT ですが、BEAT2 / SMPL-X の利用条件は独立です。

確認した公式コマンド:

```bash
export STREAMTALK_ROOT="$MOTION_LAB_DATA/upstreams/streamtalk"
export PYTHONPATH="${STREAMTALK_ROOT}/Scripts:${PYTHONPATH:-}"
cd "$STREAMTALK_ROOT/Scripts/FM"
python TestFixedExpressions_keyposes.py \
  "$STREAMTALK_ROOT/Data/Test/2_scott_0_1_1.wav" \
  "$STREAMTALK_ROOT/checkpoints/pretrained/streamtalk_speaker2_combined_e0946_cfg3.pt" \
  --example_motion_npz "$STREAMTALK_ROOT/Data/Test/2_scott_0_1_1.npz" \
  --pid 2_scott_0 --output_file "$MOTION_LAB_DATA/official-attempts/streamtalk.npz" \
  --wavlm_model patrickvonplaten/wavlm-libri-clean-100h-large \
  --smplx_model /absolute/path/to/SMPLX_NEUTRAL_2020.npz \
  --retrieval_data_folder /absolute/path/to/BEAT2/smplxflame_30 \
  --retrieval_csv_file /absolute/path/to/BEAT2/train_test_split.csv --cfg_scale 3 --seed 0
```

取得済み資産の実在パスを runtime.json の streamtalk 節に設定してください。共通アダプターは公式 NPZ を残し、別プロセスの `export_smplx.py` で許諾済み body model の FK を行います。どちらもこのインスタンスでは未実行。

**MIBURI** の公式 Python3.12 / torch2.9.0 と Moshi7B、MIBURI codec/LM (~1.7GB)、SMPL-X/Mixamo 規約の確認が必要です。公式 `miburi.gest-server` / `miburi/run_gestinference.py` が推論エントリです。offline script に `.cuda()` と synchronize があり CPU 対応を仮定しません。共通実行アダプターは未実装。公開 Space は調査時 PAUSED、GPU を起動していません。

## 会話テキスト: LLM-Gesture-Pipelines と追加モデル

Text-Only / Text-DiT は Llama3.2-3B の利用権、時刻付き TSV、3074-D embedding、公開 checkpoint、validation seed、DiffuseStyleGesture の正規化 mean/std と BVH pipeline が必要です。公式 inference.py は CUDA を固定使用し、コード・Drive 重みのライセンスは未確認です。未実装のアダプターを動作済みと表示しません。

ViBES は、会話用 body expert の checkpoint リンクが docs にまだなく、公開 `JuzeZhang/ViBES` は README のみでした。一方、**ViBES-T2M の研究限定 checkpoint は公開**されており、これは Qwen3-1.7B + HumanML3D/MotionGPT の別経路です。Face 重みを body の代用品として使わず、T2M checkpoint を会話音声 body expert と混同しません。T2M の導入・推論は未実行。

FreeTalker、AgentHands は互換性レポートに公式エントリと制約を記載しています。AgentHands は動作選択・制御で、任意の full-body learned generator として扱いません。
