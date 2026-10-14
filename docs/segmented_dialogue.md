# 文ごとに音声とジェスチャーを生成する

従来の一括発話・保存済みモーション再生は保持し、別の生成スクリプトと書き出しスクリプトを追加しました。[連結動画](../reports/segmented/english-lesson/combined.mp4) と [5区間の一覧・計測](../reports/segmented/english-lesson/README.md) を保存しています。

1. こんにちは！
2. 今日も一緒に楽しく英語を勉強しましょう！
3. まずは英語で挨拶してみよう。
4. Hello! How are you today?
5. 元気なときは、I'm happy! って言ってみてね。

`/` で指定された区切りをそのまま使います。④の英語2文は1区間、⑤の `I'm happy!` は同じ区間の一部です。区間の設定は [segmented_english_lesson.json](../configs/segmented_english_lesson.json) に分離し、発話文と、モデルへ渡す英語の動作指示をそれぞれ保存しています。今回の動作指示は発話内容に合わせて設定したものです。

各区間でRealtime APIの音声を生成して長さを測り、その長さに合わせてKimodoで別々に動作を生成します。5区間すべてに独立した成功通知・元NPZ・骨格JSON・音声・入力・ハッシュがあります。以前の3秒の動作の再利用や反復はありません。

**再生時は各区間の音声と動作を同じフレームで開始します。** 前の区間が終わると、次の区間の音声と動作を開始します。音声は短縮せず、30fpsの境界まで最大約33msだけ末尾に無音を追加します。姿勢は区間の境目で最大250ms補間し、腰の位置を引き継ぎます。音声RMSから口を動かします。

Kimodo公式デモは最短2秒です。①では2秒の新規動作を保存し、再生時に約0.967秒へ縮めています。元の動作は変更せず、`motion_seconds`、`playback_seconds`、`playback_speed` に両方の長さと速度を記録します。短い動作は速く見える可能性があります。

これは生成してから連結動画を作るバッチ処理です。ライブ会話中にGPU推論が間に合うかどうかの検証や、音声波形で条件付けしたジェスチャーモデルの実験とは別です。

## 実行

Gitリポジトリは **https://github.com/nk-an-nk/textToMotion.git / `work` ブランチ**です。既存の環境・モデル設定と、使用条件を確認したVRM 1.0を使います。アプリを起動し、ChromiumとFFmpegを準備してください。APIキーは `OPENAI_API_KEY` または `realtime` の環境変数で渡します。キーをコマンド引数やログへ書きません。

```bash
.venv/bin/python scripts/generate_segmented_dialogue.py \
  --config configs/segmented_english_lesson.json \
  --model kimodo --output-dir .motion-lab/segmented/run-01 --budget-usd 5

node scripts/export_segmented_dialogue.cjs \
  --manifest .motion-lab/segmented/run-01/manifest.json \
  --avatar /path/to/licensed-avatar.vrm \
  --output .motion-lab/segmented/run-01/combined.mp4
```

Windowsネイティブの場合（パスを実際のVRMへ置き換えてください）:

```powershell
.\.venv\Scripts\python.exe scripts\generate_segmented_dialogue.py --config configs\segmented_english_lesson.json --model kimodo --output-dir .motion-lab\segmented\run-01 --budget-usd 5
node scripts\export_segmented_dialogue.cjs --manifest .motion-lab\segmented\run-01\manifest.json --avatar C:\Models\licensed-avatar.vrm --output .motion-lab\segmented\run-01\combined.mp4
```

`--budget-usd 5` は新規音声5回を許可する既存のアプリ内予算チェックです。実際に5ドルかかったという意味でも、プロバイダー側の課金上限でもありません。各 `voice.json` にAPI使用量を保存します。新規生成は出力先を変えて実行してください。

生成が途中で失敗した場合は、同じ設定と出力先で再実行すると、入力とハッシュが一致した成功済みの音声・動作を使って残りを進めます。不完全な音声や出典記録のない骨格は上書きせず停止します。動画が途中まで書き出された場合は、その動画を別名で保存してから書き出しを再開してください。従来の重み・結果は保持します。

`--model ardy`、`--model text_to_vrma` も選択できます。text-to-vrmaは既存のARDYエンジン設定を使います。ただし、今回のクラウドではそのローカルのテキスト条件付き推論の前提が不足しており、収録済みの5区間を実生成したのは **Kimodoのみ**です。[ARDYの公開サービスを使う別経路](ardy_segmented.md) と、同じ音声を使う比較用の `--speech-source` も追加しました。モデルの準備が不足すると音声API呼び出し前に停止します。研究室GPU側の準備は [Windows手順](windows_lab.md) を参照してください。

## 出力と時間

`segments/01` ～ `segments/05` に、区間の `speech.txt`、`request.json`、`voice.wav`、`voice.json`、`original.npz`、`original.metadata.json`、`motion.json`、`motion-generation.json`、`inference.log`、`video.mp4` を保存します。最初の失敗の記録も残します。

`manifest.json` は各区間の開始・終了フレーム、発話文、動作指示、生成時間、出典を保持します。`timeline.wav` は元のPCM音声を区間ごとに連結したものです。`combined.mp4` は5区間のH.264映像を連結し、このPCM音声を一度だけAACに変換します。個別AAC音声のエンコーダー遅延が区間の境目で積み重ならないようにしています。

個別動画と連結版は正面の **1920×1080 / 30fps / H.264 CRF16＋AAC**。各出力フレームを一度ずつ描画し、低解像度動画の拡大を行いません。VRM本体はGitへ追加しません。収録したアバターは AvatarSample_VRM1.0 / pixiv VRoid Project、個人の非営利研究用の描画動画です。

動画の全デコード、フレーム数、各区間の元音声との開始位置の照合は次で再検査できます。API呼び出しはありません。

```bash
.venv/bin/python scripts/validate_segmented_dialogue.py \
  --manifest .motion-lab/segmented/run-01/manifest.json \
  --video .motion-lab/segmented/run-01/combined.mp4 \
  --output .motion-lab/segmented/run-01/validation.json
```

音声生成・文章から骨格生成の時間は `timings.csv`、音声生成＋骨格生成＋個別MP4書き出しまでの時間は `render-timings.csv` に出力します。`combined.json` には連結を含む書き出し時間、処理時間合計、描画フレーム数、各区間の同期開始・口の開閉・姿勢の連続性を保存します。処理時間合計は成功した生成と書き出しの合計で、失敗した初回の待ち時間を含みません。クラウドのソフトウェア描画時間はRTX 5070の性能測定ではありません。

従来版は `scripts/generate_demo_speech.py`、`scripts/export_vrm_video.cjs`、`scripts/record_vrm_demo.cjs` をそのまま使えます。新しい処理は `app/segmented_dialogue.py`、`scripts/generate_segmented_dialogue.py`、`scripts/export_segmented_dialogue.cjs` に分離しました。
