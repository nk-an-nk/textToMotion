# 実験報告スライド（2026-10-16・日本時間）

- `textToMotion_experiment_report_20261016.pptx`：編集可能な30枚。全18本のデモ動画を埋め込み。PPTX単体でも動画を保持します。
- `textToMotion_experiment_report_20261016.pdf`：閲覧・配布用。動画は静止画プレビュー。
- `index.html`：資料・動画一覧。MP4（H.264/AAC）対応ブラウザーではインターネットなしで同梱18本を再生できます。
- `speaker-notes.md`：日本語の発表者ノート・出典。PowerPointのノート欄にも収録。
- `measurements.json`：原本から再集計した数値と費用計算の前提。
- `media/`：B300会話2本、7モデル会話7本、共通5区間7本、初期文分割2本。
- `embedded-video-index.json`：全18本の埋め込み先スライド番号と元動画のSHA256。

動画の場所：B300比較は13枚目、7モデルの会話・共通5文は23〜29枚目、初期の文分割は30枚目。22枚目の動画目次から各スライドへ移動できます。PowerPointのスライドショーで動画をクリックすると再生できます。

ZIPを展開し、フォルダー構造を保ったまま利用してください。PDFでは動画を再生できません。PowerPointの動画再生が利用環境で制限される場合は `index.html` または `media/` のMP4を使用してください。ブラウザーがMP4に非対応の場合は、MP4を対応する動画プレイヤーで開いてください。PPTXの文字・表・棒グラフ・時間軸は編集可能です。フォントはNoto Sans CJK JPを指定しています。PDFではフォントを埋め込んでいます。

実験コードの参照リポジトリ： https://github.com/nk-an-nk/textToMotion/tree/work
参照コミット：`3a37d6e113f16a20fade819b8ba6c113d80d3a3b`

今回の資料作成では、追加の有料GPU起動・音声API呼び出しを行っていません。既存の学習済み重み・VRM本体を再配布していません。デモ映像のアバターはAvatarSample_VRM1.0 / pixiv VRoid Project。

注意：GPU・入力・役割・ロードや通信の含有範囲が異なる結果を、同一条件のモデル順位として扱わないでください。会話実測は各1回、B300単体生成は各3回。生成品質・日本語意味適合・FID・RTX5070 Windows実機・ライブマイク連続対話は未評価または未検証です。料金は計測時間と記録usageからの概算で、確定請求額ではありません。

再生成：リポジトリのルートで `python scripts/build_experiment_report.py` を実行。画像・MP4は既存成果物から同梱した `assets/` と `media/` を参照します。PDFはLibreOfficeでPPTXから出力します。
