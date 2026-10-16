# 報告用PowerPoint 更新版（2026-10-16）

49枚、動画60本を埋め込みました。PPTX単体で全動画を保持します。従来30枚・18本は第1期として残し、今回の19枚・42本を追加しています。

- `textToMotion_experiment_report_20261016_updated.pptx`：編集可能な更新版。約96MiB。スライドショーで動画をクリックして再生。
- 同名PDF：閲覧用の静止画。動画は再生できません。
- `index.html` / `media/`：全60本をブラウザー等で個別に再生。
- `speaker-notes.md`：日本語原稿と出典。PPTXのノート欄にも保存。
- `embedded-video-index.json`：全動画のスライド番号とSHA256。

追加実験は31枚目から。31〜37枚目にLLM英訳、測定範囲、90回の推論、会話6回、GPU仕様、料金、出力品質上の課題を整理。38〜43枚目は3モデル×2環境の本編12本、44〜49枚目は全区間単独30本です。

第1期は原文直接入力等の従来条件、第2期はLLM英訳入力です。条件の違う値を直接のモデル順位として比較しないでください。研究室PC実機は未測定で、RTX4090＋allocator12GB上限＋CPU8を代替としています。上半身を表示していますが推論は全身22関節。会話実測は各条件1回、品質やFIDの定量評価は未実施です。MoMaskの一部には大きく体を倒す出力が含まれます。

RunPodは両方停止し、重み・環境・結果を24時間保持しています。期限は10/17 15:37 / 16:04 JST。期限後削除watcherはこのクラウド環境上のbest effortです。

再生成は `python scripts/update_experiment_presentation.py`。既存更新版を上書きしないため、再生成時は出力フォルダーを退避してください。PDFはLibreOfficeから別途出力します。資料作成処理で追加GPUや有料APIを呼びません。元の重み・VRM本体は再配布せず、動画内にアバターのcreditを表示しています。

指定フォントはNoto Sans CJK JPです。PDFはフォントを埋め込んだ閲覧版です。

ブラウザーでローカルHTMLが制限される場合は、リポジトリのルートで `python -m http.server 8000 --bind 127.0.0.1 --directory reports/presentation-20261016-updated` を実行し、`http://localhost:8000/` を開けます。PowerPoint本体の埋め込み再生にはこのサーバーは不要です。
