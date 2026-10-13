# 使用OSS・重み・データのライセンス

確認元は固定 GitHub ref と公開 HF model card。コード公開を重み・dataset・人体modelの利用許諾と同一視しません。root licenseがないsourceは許諾不明とし、アプリへコードをコピー／再配布していません。モデル本体・dataset・SMPL-X/FLAMEは primary Git repositoryへ追加しません。

| モデル | コード | 重み | data / body / backbone |
|---|---|---|---|
| [The Language of Motion v1](https://github.com/Juzezhang/language_of_motion/tree/f238afba0cb6e32df7bc15c974ff2ece109892e3) | MIT | Apache-2.0（公開 HF v1 カード確認）。SMPL-X/FLAME は別規約。 | AMASS/BEAT2 と SMPL-X/FLAME の個別規約 |
| [ARDY](https://github.com/nv-tlabs/ardy/tree/693f74d13b3d04a0a22ce127ee79c929dd89756b) | Apache-2.0 | NVIDIA Open Model License（公式 README）。Llama encoder は独立ライセンス。 | Bones Rigplay 1 独自規約。データの再配布はしない。 |
| [Kimodo](https://github.com/nv-tlabs/kimodo/tree/58e781898b3d7e328a676a75d3e338c45dce3ad9) | Apache-2.0 | SOMA/G1: NVIDIA Open Model; SMPLX: NVIDIA R&D Model License | Bones Rigplay 1 / BONES-SEED 独自規約、SMPL-X 別規約 |
| [MIBURI](https://github.com/m-hamza-mughal/miburi/tree/2d43849265d3d17e7508ca8e01f362f1b7eda697) | CC-BY-NC-4.0; bundled AudioCraft license separately | MIBURI CC-BY-NC-4.0; Moshi/Mimi CC-BY-4.0 | BEATX/BEAT2; SMPL-X noncommercial; Adobe Mixamo separate |
| [StreamTalk](https://github.com/Xiangyue-Zhang/StreamTalk/tree/550faa3d2fcf56d2055552fef6a19a107c998d44) | MIT | MIT（公開 HF モデルカード確認）。BEAT2/SMPL-X 資産は別規約。 | BEAT2 + SMPL-X 個別規約、配布 inference data のカード別途 |
| [LLM-Gesture-Pipelines](https://github.com/AI-Unicamp/LLM-Gesture-Pipelines/tree/b551372ffee1ebb78fc79993c09b44ea18e5df0a) | root LICENSE 未確認（存在なし）。再配布許諾を推定しない。 | Google Drive 配布条件未確認; Llama3.2 separate gated license | GENEA 2023 / Talking With Hands 個別規約 |
| [ViBES (body)](https://github.com/Juzezhang/ViBES/tree/aa2347fa64e01a99f3a41db9f72417066f7d3011) | MIT | Face: CC-BY-4.0 / Audio: Apache-2.0 / T2M: research-only。会話 body expert の公開は未確認。 | SMPL-X/FLAME/BEAT2/BONES 等の個別規約 |
| [FreeTalker](https://github.com/YoungSeng/FreeTalker/tree/33bff1fe955305ed8f753ec1cea709312a57a30f) | root LICENSE なし。HumanML3D 等のサブツリーには別ライセンス。 | Google/Baidu 配布の条件未確認。 | BEAT / AMASS / HumanML3D / SMPL-X 個別規約 |
| [AgentHands / XR Blocks](https://github.com/google/xrblocks/tree/b97fa6fd4d9770566a3abe0c63bb9f8bdf3dcf93) | Apache-2.0（assets は個別条件） | N/A; 外部 LLM provider の条件は別 | N/A / hand assets の規約は別 |

## 追加OSS

| OSS | License / 確認範囲 |
|---|---|
| FastAPI | MIT |
| Uvicorn | BSD-3-Clause |
| NumPy / SciPy | BSD-3-Clause |
| Matplotlib | PSF-based license |
| Three.js 0.176.0 | MIT |
| Playwright 1.52.0 | Apache-2.0 |
| PyTorch 2.9.0 | BSD-3-Clause、本件はCPU wheel |
| Viser / NVIDIA kimodo-viser fork | upstream MIT と fork の各SPDX noticesを保持。commit 7c82ad8f8640bad9dff8ded5c5eee908eeb08f11 |
| ARDY MotionCorrection | Apache-2.0、Eigen等の個別条件を保持 |
| MIBURI bundled AudioCraft | LICENSE.audiocraft は MIT、MIBURI本体CC-BY-NCとは別 |
| LLM2Vec / Meta Llama | LLM2Vec adapters MIT。backbone Llama3のgated license/利用承認は別。今回はbackboneを取得していない |

ARDY Core8 に同梱された NVIDIA Open Model Agreement は、commercial use、derivative、outputsへのNVIDIA非所有を記載します。ただし再配布時のAgreement/NOTICE等の条件は別に適用されます。学習済み重みのGit再配布は行っていません。Kimodoオンラインでは公開NVIDIAサービスの通常制限に従い、GPUを新規作成していません。
