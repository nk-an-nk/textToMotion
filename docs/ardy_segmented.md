# ARDYで5区間を生成する

Kimodo版と同じ発話音声・入力・開始フレームを使い、ARDYのジェスチャーを区間ごとに新規生成する実行経路です。音声を再利用するため、この比較ではOpenAI APIを追加で呼びません。従来のローカルARDYとKimodo版は保持しています。

## 現在の状態

2026-10-14：Publish後のHugging Face認証（HTTP200）を確認し、5区間すべてで文章条件付きARDYの新規ジェスチャー生成に成功しました。[音声付き連結動画と各区間の時間](../reports/segmented/english-lesson-ardy/README.md) を保存しています。同じ音声・発話文・動作指示・seed・再生開始フレームの [Kimodo版](../reports/segmented/english-lesson/README.md) と比較できます。

クラウドには公開Core8重みとCPU推論環境もありますが、ローカルのLLM2Vec / gated Llamaは未取得です。今回のテキスト条件付き動作は公開サービスのリモート推論結果です。

公開コミュニティSpace [hugging-apps/ardy-human-motion](https://huggingface.co/spaces/hugging-apps/ardy-human-motion) は稼働しています。固定したソースを確認し、実際のNVIDIA ARDYとLLM2Vecを使うこと、Core27骨格定義が保持した公式ソースと一致することを確認しました。これは **NVIDIAがホストした公式デモではありません**。モデルは **ARDY-Core-RP-20FPS-Horizon40** で、研究室用の既定Core8とは予測ホライズンが異なります。

匿名利用枠で拒否された初回の [検査記録](../reports/ardy_segmented_readiness.json) も保持しています。利用者のトークンで認証後、通常の利用枠内で生成できました。Gradioクライアントの認証引数は、2.xの `token` と旧版の `hf_token` に対応しています。

元NPZ内の入力文と応答を照合し、5つの異なる学習済みモデル出力と共通Core27骨格を確認しました。各区間の出典・生成時間・ハッシュは `segments/<ID>/motion-generation.json`、`original.metadata.json` と `manifest.json` にあります。

## 認証と実行

このクラウドでは `HF_TOKEN` の保存・Publishと認証を確認済みです。新しい環境では環境設定から入力してください。トークンはチャット、Git、ログに貼りません。ネットワークシークレットの送信先は `huggingface.co` と `hugging-apps-ardy-human-motion.hf.space` に限定しています。無料のZeroGPU利用枠に従う推論で、有料GPUの起動・再開は行いません。認証しても利用枠・サービス障害で停止する場合は、そのエラーを記録します。

```bash
.venv/bin/python scripts/generate_segmented_dialogue.py \
  --model ardy --ardy-backend community_demo \
  --speech-source reports/segmented/english-lesson/manifest.json \
  --output-dir .motion-lab/segmented/english-lesson-ardy --budget-usd 0

node scripts/export_segmented_dialogue.cjs \
  --manifest .motion-lab/segmented/english-lesson-ardy/manifest.json \
  --avatar /path/to/licensed-avatar.vrm \
  --output .motion-lab/segmented/english-lesson-ardy/combined.mp4

.venv/bin/python scripts/validate_segmented_dialogue.py \
  --manifest .motion-lab/segmented/english-lesson-ardy/manifest.json \
  --video .motion-lab/segmented/english-lesson-ardy/combined.mp4 \
  --output .motion-lab/segmented/english-lesson-ardy/validation.json
```

アプリ、Chromium、FFmpeg、ARDY専用環境が必要です。クラウドでは保持した環境を使います。モデルと条件付き推論の準備が済んだ研究室Windowsでは、Pythonの実行ファイルを `.\.venv\Scripts\python.exe` へ読み替えます。ローカルのCore8を使うときは `--ardy-backend local` に変更し、[Windowsセットアップ](windows_lab.md) に従ってLlamaの利用権とテキストエンコーダーを準備してください。

公開サービスは最短1秒・最大10秒、モデルは20fpsです。音声を切らず、動作の長さをネイティブ20fpsのフレーム境界へ切り上げて生成し、再生時は各発話区間の長さへ合わせます。①の動作は1秒、再生は約0.967秒になります。音声と動作は区間の同じフレームで開始し、個別5本を連結します。

`--speech-source` は元の5区間と文・順序・音声ハッシュ・実際の書き起こしが一致するときだけ再利用します。元の音声生成記録をそのまま保存し、今回の音声生成時間は0秒、元の生成時間は `speech_original_generation_seconds` に別記します。骨格・MP4の生成時間は既存のCSVへ出力します。完了済みの出力は再実行で変更しません。

`timings.csv` の `input_to_skeleton_seconds` は動作指示を生成処理へ渡す直前から、正規化した骨格JSONの生成完了までの実測時間です。キュー・テキスト処理・転送・変換を含み、GPUカーネルだけの時間ではありません。入力・完了のUTC時刻も保存します。

`render-timings.csv` の `input_to_mp4_seconds` は同じ入力時刻から個別MP4完成までの経過時間です。他の区間の生成、描画開始待ちも含みます。`skeleton_and_mp4_processing_seconds` は骨格生成とその区間の動画書き出しの処理時間の合計です。両者を区別し、連結版の経過時間は `combined.json` の `input_to_combined_mp4_seconds` に保存します。

ソース固定：Space revision `344cab081ed29a48879683c0a78f80918b5a1681`、`app.py` SHA-256 `54d625cd8984c6980abc54a7fe953718205a44bfb53f651115ca68b47754d828`。稼働状態・固定ソース・要求した文・seed・NPZ内の文・フレーム数・有限な関節位置・応答とNPZの一致を検査します。バージョン変更、認証不足、利用上限は失敗として停止します。

実装は `scripts/ardy_online.py` と `adapters/ardy_online.py` に分離し、既存の `adapters/ardy.py` や研究室用のローカル生成コードは変更していません。[分割動画の実装・出力仕様](segmented_dialogue.md) も参照してください。
