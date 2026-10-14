# 公式モデル互換性調査

最新の追加検証：公開コミュニティサービスのARDY Horizon40で、文章条件付きの5区間を新規生成し、Kimodo版と同じ音声を使ったVRM動画を出力しました。[ARDYの入力・計測・動画](segmented/english-lesson-ardy/README.md) を参照してください。以下の初期調査表にある「ARDY無条件CPU診断」とは別の実行記録です。ローカルCore8のテキスト条件付き推論は引き続き未検証です。

確認日（日本時間）: 2026-10-13T21:58:00.488572+09:00

公式 GitHub の README、license、依存定義、推論エントリ、実 HEAD を確認。実行証拠は execution_results.md、重みの HTTP 検査は huggingface_checks.json。主たる checkout は nk-an-nk/textToMotion、9モデルの source は ML dependency cache として別置き。

## 論文・入力・出力

| モデル / 優先度 | 論文・年・発表先 | 入力 | 出力・骨格 |
|---|---|---|---|
| The Language of Motion v1 / 1 | The Language of Motion: Unifying Verbal and Non-verbal Language of 3D Human Motion (2025, CVPR) | C:動作指示, B:音声 | SMPL-X poses/trans/expressions NPZ; 55 pose joints, 30 fps |
| ARDY / 2 | ARDY: Autoregressive Diffusion with Hybrid Representation for Interactive Human Motion Generation (2026, SIGGRAPH / ACM TOG) | C:動作指示 | Core 27 / G1 34 joints; world posed_joints NPZ; Core 20 fps / G1 25 fps |
| Kimodo / 2 | Kimodo: Scaling Controllable Human Motion Generation (2026, arXiv:2603.15546 / technical report) | C:動作指示 | SOMA 77 / G1 34 / SMPLX 22 joints; NPZ, G1 qpos CSV, SMPLX AMASS NPZ |
| MIBURI / 3 | MIBURI: Towards Expressive Interactive Gesture Synthesis (2026, CVPR) | B:音声 | SMPL-X at 25 fps, codec tokens, live Viser and reply-audio video |
| StreamTalk / 3 | StreamTalk: Streaming Co-Speech Gesture Generation with Key-Pose Anchoring (2026, ECCV) | B:音声 | SMPL-X 55-joint pose parameters NPZ; poses/trans/expressions/betas |
| LLM-Gesture-Pipelines / 4 | From Embeddings to Language Models: A Comparative Analysis of Feature Extractors for Text-Only and Multimodal Gesture Generation (2025, GENEA workshop at ACM Multimedia) | A:会話テキスト, B:音声 | Text-Only/Text-DiT -> BVH; 62-joint conversion pipeline (pipeline_rotmat_62.sav) |
| ViBES (body) / 5 | ViBES: A Conversational Agent with Behaviorally-Intelligent 3D Virtual Body (2026, CVPR) | A:会話テキスト, C:動作指示 | Face FLAME / body SMPL-X; speech tokens and synchronized MP4 |
| FreeTalker / 5 | FreeTalker: Controllable Speech and Text-Driven Gesture Generation Based on Diffusion Models for Enhanced Speaker Naturalness (2024, ICASSP（公式 conference archive）) | C:動作指示, B:音声 | result_rec*.npy joints; MP4; optional SMPLX conversion |
| AgentHands / XR Blocks / 5 | AgentHands (2026, CHI（addon README の引用）) | A:会話テキスト | Three.js posable hands/orb; inline gesture timeline; full body output なし |

A/B/C は原則公式モデルの条件形式。自然な会話意味への適合性や日本語対応を検証した意味ではありません。Kimodo は C、ARDY の今回の実測は A/B/C のいずれにも数えない無条件診断。AgentHands の A は markup による手動作選択であり full-body generation ではありません。

## 重み・ライセンス・取得状態

| モデル | 公開重み | 全量取得／実行 | コード license | 重み license | データ・人体資産 license |
|---|---|---|---|---|---|
| The Language of Motion v1 | JuzeZhang/language_of_motion | 公開 v1 checkpoint 先頭16byte取得可。全量未取得・未推論 | MIT | Apache-2.0（公開 HF v1 カード確認）。SMPL-X/FLAME は別規約。 | AMASS/BEAT2 と SMPL-X/FLAME の個別規約 |
| ARDY | nvidia/ARDY-Core-RP-20FPS-Horizon8 | Core8 約765MB を全量取得・公開 LFS SHA256 照合・CPU診断成功 | Apache-2.0 | NVIDIA Open Model License（公式 README）。Llama encoder は独立ライセンス。 | Bones Rigplay 1 独自規約。データの再配布はしない。 |
| Kimodo | nvidia/Kimodo-SOMA-RP-v1.1 | ローカル配信先の16byte取得可。実推論は公式 Space の SOMA-RP-v1。ローカルv1.1未取得 | Apache-2.0 | SOMA/G1: NVIDIA Open Model; SMPLX: NVIDIA R&D Model License | Bones Rigplay 1 / BONES-SEED 独自規約、SMPL-X 別規約 |
| MIBURI | m-hamza-mughal/miburi-release-checkpoints | 公開 checkpoint 先頭16byte取得可。全量未取得・未推論 | CC-BY-NC-4.0; bundled AudioCraft license separately | MIBURI CC-BY-NC-4.0; Moshi/Mimi CC-BY-4.0 | BEATX/BEAT2; SMPL-X noncommercial; Adobe Mixamo separate |
| StreamTalk | X-Zhang/StreamTalk | 公開 checkpoint 先頭16byte取得可。全量未取得・未推論 | MIT | MIT（公開 HF モデルカード確認）。BEAT2/SMPL-X 資産は別規約。 | BEAT2 + SMPL-X 個別規約、配布 inference data のカード別途 |
| LLM-Gesture-Pipelines | Google Drive: 1w4pqZerPJlT-Kdsft8D8bbuERhRZoGdi | Google Drive 配布を参照。重み未取得・未推論 | root LICENSE 未確認（存在なし）。再配布許諾を推定しない。 | Google Drive 配布条件未確認; Llama3.2 separate gated license | GENEA 2023 / Talking With Hands 個別規約 |
| ViBES (body) | JuzeZhang/ViBES は README のみ。Face/Audio の他に ViBES-T2M 研究限定の motion expert が公開。会話 body expert は未確認。 | Face/Audio 配信の先頭16byte取得可。会話body linkは未確認。ViBES-T2M公開／未推論 | MIT | Face: CC-BY-4.0 / Audio: Apache-2.0 / T2M: research-only。会話 body expert の公開は未確認。 | SMPL-X/FLAME/BEAT2/BONES 等の個別規約 |
| FreeTalker | Google Drive: 1M2m_3S5I5SgnPU1bWNeX0r2wKWDV9maW | Google/Baidu配布を参照。重み未取得・未推論 | root LICENSE なし。HumanML3D 等のサブツリーには別ライセンス。 | Google/Baidu 配布の条件未確認。 | BEAT / AMASS / HumanML3D / SMPL-X 個別規約 |
| AgentHands / XR Blocks | 生成モデルの重みなし。LLM gesture markup を既存手動作へ選択・制御する addon。 | 生成モデルの重みはない。addon未実行 | Apache-2.0（assets は個別条件） | N/A; 外部 LLM provider の条件は別 | N/A / hand assets の規約は別 |

配信先への HTTP200 は、全量取得や重みロードの完了ではありません。Codeの公開／checkpointの公開／model-card license／dataset licenseは独立に扱います。

## 実行環境・デモ・障害

| モデル | GPU・VRAM | macOS / MPS | 依存・platform | 公式デモ／可視化 | 今回の障害／範囲 |
|---|---|---|---|---|---|
| The Language of Motion v1 | 公式 v1 demo.py は CUDA 直接呼び出し。最低 VRAM は未記載。 | 未検証。CPU/MPS へ config を変えるだけでは動かない。 | Python 3.10; torch 2.4.0/cu121; fairseq; numpy 1.23.1; v1 transformers <=4.49 / v2 5.12.1 | demo.py + Blender 2.93.18 rendering | 公開 v1 重みの配信は確認。CUDA GPU と許諾済み SMPL-X/FLAME が不足、旧 v1 依存環境は未構築。 |
| ARDY | 公式 CLI に CPU 分岐あり。LLM2Vec の GPU bf16 は約14GB（README）。CPU 推論速度は未測定。 | ビルドに ARM64 分岐あり。MPS 推論は未検証。 | Python >=3.10; torch >=2.4; transformers 5.8.1; C++17/CMake; numpy<2 | scripts/run_demo.py; scripts/visualize.py (Viser) | 公開 Core8 重み取得・SHA256確認、CPU無条件診断成功。言語条件付きは gated Llama が HTTP401、未成功。 |
| Kimodo | 全 GPU 約17GB VRAM。TEXT_ENCODER_DEVICE=cpu で <3GB（公式）。CLI CPU 分岐あり、未実行。 | 公式は Linux 開発。macOS/MPS 未検証。 | Python >=3.8（現行ソースは新しい Python 推奨）; transformers 5.1.0; torch 別途; motion correction | kimodo_demo (Gradio + Viser) / kimodo_gen | 公式オンライン v1 推論成功（異なる2入力）。ローカル v1.1 と Llama encoder は未実行。 |
| MIBURI | Moshi 7B + gesture LM; official run_gestinference has .cuda()/synchronize.最低 VRAM 未記載。 | 公式 CUDA 13/12 手順。MPS 未検証。 | Python 3.12; torch 2.9.0; hf-hub<0.29; streaming Moshi | python -m miburi.gest-server / offline run_gestinference.py | GPU 不在・Moshi 大容量・SMPL-X/Mixamo 条件確認が必要。実行アダプター未実装。 |
| StreamTalk | README が CUDA GPU 必須と明記。論文 76fps は V100 16GB の実測、最低 VRAM ではない。 | CUDA 直呼び。MPS 未対応・未検証。 | Python 3.9; torch 2.0/CUDA11.8; WavLM; retrieval BEAT2 | Scripts/FM/TestFixedExpressions_keyposes.py; published YouTube demo | NVIDIA GPU・SMPL-X・BEAT2 retrieval assets が必要。HF 接続も拒否。 |
| LLM-Gesture-Pipelines | 公式 inference.py は torch.cuda.set_device。推奨16GB VRAM（README）。 | CUDA 固定、MPS 未検証。 | Python3.8; torch2.1/cu121; DiffuseStyleGesture submodule; gated Llama3.2-3B; timestamped TSV + 3074-D embeddings | scripts/inference.py produces BVH; qualitative videos | CUDA 固定・重み/seed/normalization pipeline・Llamaアクセス未確認。実行アダプター未実装。 |
| ViBES (body) | GLM4-Voice9B（約18GB base）または0.5B、CUDA/PyTorch3D。最低VRAM未記載。 | GPU ビルド手順、MPS 未検証。 | GLM4-Voice; torch cu128; PyTorch3D with GPU; body compositional VQ | inference/inference_face.py; body code exists | 会話 body expert は公開リンクを確認できず利用不可。公開 ViBES-T2M は別 HumanML3D/Qwen 経路で未実行。 |
| FreeTalker | 公式 RTX4090 CUDA12.2 で検証。最低VRAM不明。 | Python3.8 Linux pinned env。MPS 未検証。 | PriorMDM env; WavLM features; CLIP features; smplx[all] | python -m sample.double_take; merge_mp4_audio | 旧環境・Google/Baidu 重み・前処理データ・root license 不明。実行アダプター未実装。 |
| AgentHands / XR Blocks | browser WebGL/WebXR。学習済み full-body generator ではない。 | browser環境依存、今回未起動。 | TypeScript/npm; optional LLM/TTS provider; WebXR scene | demos/agent_hands; src/addons/agenthands | 手動作の選択・制御。任意3D人体動作の生成モデルとしては利用不可。addon 統合は未実装。 |

GPUの最低VRAMが公式に未記載のモデルでは、推奨環境／論文測定値から最低値を捏造しません。macOS / MPS は実機検証していません。

## 公式ソースと最後のコミット

| モデル | 公式GitHub（確認済み固定ref） | コミット時刻 |
|---|---|---|
| The Language of Motion v1 | [Juzezhang/language_of_motion](https://github.com/Juzezhang/language_of_motion/tree/f238afba0cb6e32df7bc15c974ff2ece109892e3) `f238afba0cb6e32df7bc15c974ff2ece109892e3` | 2026-07-16T12:26:56-07:00 |
| ARDY | [nv-tlabs/ardy](https://github.com/nv-tlabs/ardy/tree/693f74d13b3d04a0a22ce127ee79c929dd89756b) `693f74d13b3d04a0a22ce127ee79c929dd89756b` | 2026-07-09T19:52:46+02:00 |
| Kimodo | [nv-tlabs/kimodo](https://github.com/nv-tlabs/kimodo/tree/58e781898b3d7e328a676a75d3e338c45dce3ad9) `58e781898b3d7e328a676a75d3e338c45dce3ad9` | 2026-09-22T12:30:02+02:00 |
| MIBURI | [m-hamza-mughal/miburi](https://github.com/m-hamza-mughal/miburi/tree/2d43849265d3d17e7508ca8e01f362f1b7eda697) `2d43849265d3d17e7508ca8e01f362f1b7eda697` | 2026-09-30T13:00:01+02:00 |
| StreamTalk | [Xiangyue-Zhang/StreamTalk](https://github.com/Xiangyue-Zhang/StreamTalk/tree/550faa3d2fcf56d2055552fef6a19a107c998d44) `550faa3d2fcf56d2055552fef6a19a107c998d44` | 2026-08-28T13:09:45+08:00 |
| LLM-Gesture-Pipelines | [AI-Unicamp/LLM-Gesture-Pipelines](https://github.com/AI-Unicamp/LLM-Gesture-Pipelines/tree/b551372ffee1ebb78fc79993c09b44ea18e5df0a) `b551372ffee1ebb78fc79993c09b44ea18e5df0a` | 2025-10-14T15:08:15-03:00 |
| ViBES (body) | [Juzezhang/ViBES](https://github.com/Juzezhang/ViBES/tree/aa2347fa64e01a99f3a41db9f72417066f7d3011) `aa2347fa64e01a99f3a41db9f72417066f7d3011` | 2026-08-03T11:36:49-07:00 |
| FreeTalker | [YoungSeng/FreeTalker](https://github.com/YoungSeng/FreeTalker/tree/33bff1fe955305ed8f753ec1cea709312a57a30f) `33bff1fe955305ed8f753ec1cea709312a57a30f` | 2026-04-09T15:17:50+08:00 |
| AgentHands / XR Blocks | [google/xrblocks](https://github.com/google/xrblocks/tree/b97fa6fd4d9770566a3abe0c63bb9f8bdf3dcf93) `b97fa6fd4d9770566a3abe0c63bb9f8bdf3dcf93` | 2026-10-12T22:33:50-07:00 |

全9 source の tracked diff は空。上流ソースやテストは書き換えていません。pip build の生成物は別で、主アプリの自作コード／依存宣言と区別します。

## LoM v1/v2 と ViBES release の注意

- LoM v1 は HuBERT500 / T5 encoder-decoder。v2 は GLM4-Voice16384 / decoder-only pretrained LLM。token vocabulary、LM architecture、text/audio sequence、root velocity表現が変わり、v1 checkpoint と v2 config は非互換。v1 transformers<=4.49 と upstream v2 requirements 5.12.1 も分離が必要。
- 公開 LoM-a2m-4part release は reports/lom_v2_release.json に記録。存在だけで推論成功とは扱わず、対応する構成・VQ・body assets・shape照合は未実行。
- ViBES READMEはbody codeを available と記載する一方、docs/3-inference.mdはbody checkpointをplaceholderとしている。JuzeZhang/ViBES は README のみ。Face/Audioの公開と会話body expertの公開を区別した。
- ViBES-T2M は公式authorが別途公開した research-only の Qwen3-1.7B + HumanML3D/MotionGPT 経路。READMEとcheckpoint自体が示す0.27B expert、GLM expert形式など複数構成が同居しているため相互互換を仮定しない。会話body expertの代用品とは扱わず、今回未実行。
- AgentHands は既存手動作の選択・制御、grounded pointing、TTS word-boundary同期。任意full-body motion generatorではない。

## 追加: text-to-vrma（2026-10-14）

[Kirakun0328/text-to-vrma](https://github.com/Kirakun0328/text-to-vrma/tree/53c50504d1dc5137d4414b27ae8afaff89a62943) を10番目の比較経路として追加しました。利用者指定によりARDYエンジンを選択し、共有のCore8・CPUテキスト処理・CUDA動作生成を使います。独立した動作モデルではありません。Node.js 20.6以上、公式npm lock、準備済みARDY専用環境が必要です。LLM planner・Jev・追加APIは無効にします。

固定ソース・runtime依存・公式Node関数のimport、VRMAのFK変換とMP4書き出しを確認しました。形式確認には明示した人工fixtureを使い、テキスト推論成功とは数えません。研究室Windows/RTX 5070での実生成は未検証です。VRMA・specを保持し、hips軌跡と階層を共通骨格へ変換します。表情・視線は元VRMAに残り、骨格MP4には含めません。

コードはMIT。ARDY/Llamaと同梱VRoid素材は別規約です。[統合記録](text_to_vrma_integration.json)、[Windows手順](../docs/windows_lab.md)、[ライセンス](licenses.md) を参照してください。
