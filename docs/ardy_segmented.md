# ARDYで5区間を生成する

Kimodo版と同じ発話音声・入力・開始フレームを使い、ARDYのジェスチャーを区間ごとに新規生成する実行経路です。音声を再利用するため、この比較ではOpenAI APIを追加で呼びません。従来のローカルARDYとKimodo版は保持しています。

## 現在の状態

2026-10-14：クラウドには公開Core8重みとCPU推論環境がありますが、ローカルのLLM2Vec / gated Llamaが未取得で、Hugging Face認証も未設定です。ローカルの無条件診断を、発話に対応したジェスチャー生成の代わりには使用しません。

公開コミュニティSpace [hugging-apps/ardy-human-motion](https://huggingface.co/spaces/hugging-apps/ardy-human-motion) は稼働しています。固定したソースを確認し、実際のNVIDIA ARDYとLLM2Vecを使うこと、Core27骨格定義が保持した公式ソースと一致することを確認しました。これは **NVIDIAがホストした公式デモではありません**。モデルは **ARDY-Core-RP-20FPS-Horizon40** で、研究室用の既定Core8とは予測ホライズンが異なります。

最初の生成要求は `You have exceeded your ZeroGPU runs limit. Authenticate with a Hugging Face token for more quota` で拒否されました。文章条件付きARDYの生成・動画出力は未完了です。拒否を迂回する処理、匿名リクエストの反復、サンプルへの置換は行いません。

[環境と実際の拒否の記録](../reports/ardy_segmented_readiness.json) を保存しています。実行経路の準備に対してPython 102テストとJavaScript 19テストが成功しました。これらのテスト成功は、公開サービスでのARDY推論成功を示すものではありません。

## 認証と実行

このクラウドの環境設定で `HF_TOKEN` を入力して保存・Publishしてください。トークンはチャット、Git、ログに貼りません。ネットワークシークレットの送信先は `huggingface.co` と `hugging-apps-ardy-human-motion.hf.space` に限定しています。無料のZeroGPU利用枠に従う推論で、有料GPUの起動・再開は行いません。認証しても利用枠・サービス障害で停止する場合は、そのエラーを記録します。

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

ソース固定：Space revision `344cab081ed29a48879683c0a78f80918b5a1681`、`app.py` SHA-256 `54d625cd8984c6980abc54a7fe953718205a44bfb53f651115ca68b47754d828`。稼働状態・固定ソース・要求した文・seed・NPZ内の文・フレーム数・有限な関節位置・応答とNPZの一致を検査します。バージョン変更、認証不足、利用上限は失敗として停止します。

実装は `scripts/ardy_online.py` と `adapters/ardy_online.py` に分離し、既存の `adapters/ardy.py` や研究室用のローカル生成コードは変更していません。[分割動画の実装・出力仕様](segmented_dialogue.md) も参照してください。
