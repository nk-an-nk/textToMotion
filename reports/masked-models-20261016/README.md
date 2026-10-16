# MoLingo / ReMoMask-2 / MoMask 実測比較（2026-10-16）

日本語・混在文をLLM（OpenAI Realtime、テキスト出力）で英訳し、その英語を動作モデルへ渡しました。音声・字幕は元の日本語と英語を保持しています。

## 測定結果

| 環境 | モデル | 骨格生成中央値 | 会話の英訳 | 会話の骨格生成 | 発話終了→骨格受信 | Realtimeとの差 | VRAM最大 |
|---|---|---:|---:|---:|---:|---:|---:|
| RTX 4090 / VRAM上限12GB | MoLingo-263 | 2.217s | 1.587s | 2.632s | 6.175s | +5.597s | 3.10GiB |
| RTX 4090 / VRAM上限12GB | ReMoMask-2 | 0.277s | 0.936s | 0.316s | 3.302s | +2.592s | 1.75GiB |
| RTX 4090 / VRAM上限12GB | MoMask | 0.168s | 1.167s | 0.210s | 3.337s | +2.710s | 0.89GiB |
| B300 | MoLingo-263 | 3.038s | 1.499s | 3.046s | 7.756s | +6.863s | 3.10GiB |
| B300 | ReMoMask-2 | 0.494s | 1.437s | 0.520s | 5.011s | +4.112s | 1.78GiB |
| B300 | MoMask | 0.300s | 1.112s | 0.284s | 4.217s | +3.404s | 0.89GiB |

骨格生成中央値は共通5区間×3 seed＝15回の常駐推論。テキスト符号化、学習済み生成、デコード、CPUへの転送、骨格JSONの直列化を含み、モデル読込・英訳・通信・保存・MP4描画を除きます。5区間それぞれのウォームアップを先に実施しました。seedは0/1/2、動画にはseed0を採用し、見栄えによる選び直しをしていません。

会話は各モデル・環境1回の測定です。1.9秒の録音済み合成生徒音声「先生、こんにちは！」をPCM16/24kHz/monoで実時間送信し、受信した教師の全文をLLMで英訳してから新規骨格を生成しました。「発話終了→骨格受信」は同じクライアントのmonotonic時計で計測し、Realtime応答、英訳、通信を含みます。「Realtimeとの差」は骨格受信と最初の音声チャンク受信の差で、スピーカー実再生との比較ではありません。

教師の返答は「こんにちは！今日も元気そうだね！英会話の練習を始めましょう」に固定しています。自由回答の性能評価ではありません。受信した文の英訳は毎回新規に実行し、各 `dialogue/MODEL/translation.json` に原文・英訳・翻訳秒数・API usageを残しました。英訳の表現と発話時間には呼び出しごとの揺れがあるため、厳密に同一の英語入力での速度比較は共通5区間を参照してください。

## デモ動画（12本）

[ブラウザーで全動画と計測表を見る](index.html)。正面1920×1080、30fps、H.264 CRF16、AAC192k。共通5区間は区間ごとに発話・動作を同じフレームで開始して連結しています。区間単独の30本のMP4も各 `common-video/MODEL/segments/01..05/video.mp4` にあります。

会話動画は実測した待ち時間を省略せず再現するオフライン動画です。教師音声を骨格受信まで保留して、発話と動作を同時に開始します。ライブ録画ではありません。描画はこのクラウド環境のCPU / SwiftShaderで実施しており、GPU推論時間と動画化時間を分けて保存しています。

| 環境 | モデル | 共通5区間 | 生徒→先生会話 |
|---|---|---|---|
| RTX 4090 / VRAM上限12GB | MoLingo-263 | [MP4](lab_proxy/common-video/molingo/combined.mp4) | [MP4](lab_proxy/dialogue-video/molingo/dialogue.mp4) |
| RTX 4090 / VRAM上限12GB | ReMoMask-2 | [MP4](lab_proxy/common-video/remomask2/combined.mp4) | [MP4](lab_proxy/dialogue-video/remomask2/dialogue.mp4) |
| RTX 4090 / VRAM上限12GB | MoMask | [MP4](lab_proxy/common-video/momask/combined.mp4) | [MP4](lab_proxy/dialogue-video/momask/dialogue.mp4) |
| B300 | MoLingo-263 | [MP4](b300/common-video/molingo/combined.mp4) | [MP4](b300/dialogue-video/molingo/dialogue.mp4) |
| B300 | ReMoMask-2 | [MP4](b300/common-video/remomask2/combined.mp4) | [MP4](b300/dialogue-video/remomask2/dialogue.mp4) |
| B300 | MoMask | [MP4](b300/common-video/momask/combined.mp4) | [MP4](b300/dialogue-video/momask/dialogue.mp4) |

## 入力と英訳

共通5区間は同じ英訳・同じ実音声を全モデル・全GPUで共有しました。元の音声は2026-10-14の実生成クリップで、今回の推論開始前から保存済みです。英訳時間は下表に別記しており、共通区間の常駐推論中央値へ加算していません。`segment-times.csv` には英訳時間＋骨格生成中央値の処理時間合計も載せていますが、これは別測定の加算値であり、日本語入力からの通し実測ではありません。通し実測は会話の値を参照してください。

| 区間 | 元の発話 | LLMによる英語入力 | 英訳秒 |
|---|---|---|---:|
| 01 | こんにちは！ | Hello! | 1.061 |
| 02 | 今日も一緒に楽しく英語を勉強しましょう！ | Let’s have fun studying English together again today! | 1.075 |
| 03 | まずは英語で挨拶してみよう。 | First, let's try greeting in English. | 1.294 |
| 04 | Hello! How are you today? | Hello! How are you today? | 0.998 |
| 05 | 元気なときは、I'm happy! って言ってみてね。 | When you're feeling energetic, try saying, "I'm happy!" | 1.430 |

## 条件と解釈

| 環境 | 実CPU | 割当vCPU / 推論スレッド | 割当RAM | GPU / driver / VRAM / 電力上限 | GPU時給 |
|---|---|---|---:|---|---:|
| RTX 4090 / VRAM上限12GB | AMD EPYC 75F3 32-Core Processor | 16 / 8 | 62GB | NVIDIA GeForce RTX 4090, 580.159.04, 24564 MiB, 450.00 W | $0.89/h |
| B300 | Intel(R) Xeon(R) 6740E | 24 / 8 | 251GB | NVIDIA B300 SXM6 AC, 580.173.02, 275040 MiB, 1100.00 W | $8.99/h |

ソフトウェアは両方Ubuntu24.04の同一イメージ、Python3.12.3、PyTorch2.8.0+cu129 / CUDA12.9です。GPU欄のVRAMはnvidia-smiのMiB値で、公称288GB等とは単位が異なります。

- 研究室実機（Ryzen 7 5700X、RTX 5070 12GB、RAM32GB、Windows）には接続していません。代替はRTX 4090、PyTorch VRAM allocator上限12,227MiB、CPU8スレッド・affinity8です。GPUの演算性能、CPU型番、OSは一致せず、RAM32GBの強制上限も設けていません。RTX 5070の速度としては報告できません。
- B300は前回と同じNVIDIA B300 SXM6 AC 1枚。両環境で動作本体FP32、TF32無効、CPU8スレッド、同一ソースと重みです。MoMask / ReMoMask-2のCLIPには公式実装どおりFP16を併用し、MoLingoのT5はFP32です。動画中のFP32表記は動作本体を指します。実際のCPU型番、OS、driver、割当RAMは各環境の `machine.json` と `hardware.json`、導入パッケージは `versions.txt` に保存しています。
- MoLingoは公式HumanML3D **263次元版**（EMA、32 RF step、acceleration3、CFG5.5）。272次元版との比較ではありません。ReMoMask-2は公式epoch309、10 step、CFG4、retrieval k1/pool10。MoMaskはmasked18 step/CFG4＋residual CFG5。ソースcommitとダウンロードSHA256は [asset manifest](../../configs/masked_assets_20261016.json)。
- 3モデルとも全身22関節を実生成し、表示時に上半身を使用します。腰・脚の固定と胴体のyaw補正は表示用変換です。上半身だけ推論した速度ではありません。元の骨格JSONとHumanML3D特徴量NPYを `native/MODEL/` に保持しています。22関節に手指・表情の生成は含まれず、口パクは音声RMSに基づく表示です。
- 英訳後のMoLingo/T5では未知語0件を確認しました。CLIPを使う残り2モデルも入力を切り詰めず検証しています。英訳は動作指示文への書き換えを行っていません。
- これらは主に動作記述から全身運動を作るモデルです。発話内容の英訳だけでは会話ジェスチャーを保証できません。MoMaskの会話出力には大きく体を倒す動作があり、共通5区間でもMoMask/ReMoMask-2に大きな傾きが出ました。各seed0の胴体傾斜角をCSVに記録しています。傾斜角は品質点数ではなく、姿勢確認用の値です。FIDや意味適合度の定量評価は実施していません。
- 会話はJupyter WSS中継で骨格を受信しています。本番アプリの最適化済み直結通信とは異なるため、native推論秒数と通し実測を分けて評価してください。
- `summary.csv` の1リクエスト当たりGPU料金は **常駐した生成処理の秒数×GPU時給÷3600** の参考値です。起動・ダウンロード・待機・モデル読込・通信・保持領域・OpenAI利用料を含む実請求額ではありません。APIのusageは記録していますが、実請求額は未取得です。

## 生成処理のGPU料金目安

| 環境 | モデル | 常駐生成1回のGPU料金目安（共通区間中央値） | 会話の骨格生成1回 |
|---|---|---:|---:|
| RTX 4090 / VRAM上限12GB | MoLingo-263 | $0.000548 | $0.000651 |
| RTX 4090 / VRAM上限12GB | ReMoMask-2 | $0.000069 | $0.000078 |
| RTX 4090 / VRAM上限12GB | MoMask | $0.000041 | $0.000052 |
| B300 | MoLingo-263 | $0.007586 | $0.007607 |
| B300 | ReMoMask-2 | $0.001233 | $0.001298 |
| B300 | MoMask | $0.000749 | $0.000708 |

この表はGPUがすでに常駐し、生成中の時間だけを按分した参考値です。セットアップや待機も課金されるため、単発実験をこの金額で実行できるという意味ではありません。

## 会話1リクエストの参考小計

GPUは生徒音声開始から骨格受信までを按分し、今回のRealtime音声とLLM英訳の実usageからAPI料金を概算。1USD=200円。ASR・起動・待機・保存・描画は別。API単価は既存資料で2026-10-15確認のgpt-realtime-2.1（100万tokenあたり入力text4/audio32、出力text24/audio64 USD）を使用し、実請求とは未照合です。reasoningはtext内訳として二重加算しません。

| 環境 | モデル | GPU按分 | Realtime音声 | LLM英訳 | 参考小計 |
|---|---|---:|---:|---:|---:|
| lab_proxy | molingo | 0.399円 | 1.783円 | 0.502円 | 2.684円 |
| lab_proxy | remomask2 | 0.257円 | 1.886円 | 0.233円 | 2.376円 |
| lab_proxy | momask | 0.259円 | 1.830円 | 0.290円 | 2.379円 |
| b300 | molingo | 4.823円 | 1.762円 | 0.386円 | 6.972円 |
| b300 | remomask2 | 3.452円 | 1.818円 | 0.295円 | 5.565円 |
| b300 | momask | 3.055円 | 1.730円 | 0.305円 | 5.090円 |

[計算原本と単価](request-cost-estimates.json)。


## ファイルと再現

- [集計CSV](summary.csv)、[区間別CSV](segment-times.csv)、[全90回の生データCSV](all-trials.csv)、[集計JSON](summary.json)、[整合チェック](validation.json)。
- [追加実験の全42動画ZIP](../masked-models-videos-20261016.zip)。12本の本編と30本の区間単独動画を収録しています。
- [今回のGPUレンタル概算](rental-estimate.json)。Pod作成から停止までを時給で計算すると合計約$4.29です。停止後の保存領域とOpenAI利用料は別で、実請求とは未照合です。
- 各 `native/MODEL/hardware.json` は重み読込・モデル構築の秒数を記録します。最初の推論を含むウォームアップ全体はこの値に含めておらず、起動から常駐準備完了までの総cold start時間は未集計です。各動画の同名JSONは描画時間、フレーム数、口パク、固定後の実描画骨の検証値を記録しています。
- 実行手順は [docs/masked_models.md](../../docs/masked_models.md)。既存の日本語直接入力の実験・コード・動画は保持しています。重み、トークン、VRM本体はGitへ追加していません。

## RunPodの保持

- lab_proxy: Pod `tinrkdtvq2bme2`、停止確認 `True`、保持期限 UTC `2026-10-17T06:37:31.333278+00:00`。
- b300: Pod `9j8ej45smouv7m`、停止確認 `True`、保持期限 UTC `2026-10-17T07:04:22.794798+00:00`。

停止したPodの永続ボリューム `/workspace/retained` に、元の重み、固定ソースと仮想環境のアーカイブ、実行コード、ログ、結果を保存しています。再開後は `/workspace/retained/resume.sh` で `/tmp/masked_runtime` を再構築できます。

24時間後の削除は、このクラウド環境で動くローカルwatcherによるbest effortです。RunPod側の強制TTLではなく、環境が停止・交換されるとwatcherも停止します。その場合はRunPod Consoleで期限を確認して削除するか、手順書のwatchコマンドを再開してください。チェックアウト外の共有領域にもprivate stateの控えを保存していますが、環境交換後の自動再開は検証していません。削除すると保持した環境データは失われます。
