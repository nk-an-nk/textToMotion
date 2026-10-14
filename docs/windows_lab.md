powershell -ExecutionPolicy ByPass -c "irm https://chatgpt.com/codex/install.ps1 | iex"
# Windows研究室PCのセットアップ

対象として申告された構成: Ryzen 7 5700X（8コア）、RTX 5070（VRAM 12GB）、RAM 32GB、SSD 1TB。Windowsの通常ユーザー用Python仮想環境に導入します。SSH・WSL2・Dockerは不要です。

日本語音声対話・VRMを使う場合は [対話用の追加手順](conversation_vrm.md) を参照してください。`setup-conversation.ps1` はGPU・モデル準備前でもアプリだけを導入できます。モデル準備後は同じデータフォルダーを `start-conversation.ps1` で使用します。

**Windows実機とRTX 5070でのビルド・実推論は未検証です。** スクリプトは研究室PCで実際のCUDA演算・モデル推論・NPZ/JSON・MP4生成を検査し、その成功後だけ準備完了を記録します。既存のKimodo公式オンライン／ARDY CPU診断の実測時間は、この構成の速度を示しません。

## 初回の操作

1. [workブランチのZIP](https://github.com/nk-an-nk/textToMotion/archive/refs/heads/work.zip) をダウンロードして、十分な空き容量のあるフォルダへ展開します。Anaconda環境と混ぜず、このフォルダ専用の環境を作ります。
2. 展開したフォルダでPowerShellを開き、読み取りだけの確認を実行します。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup-windows.ps1 -CheckOnly
```

Python 3.12 x64、Git、Node.js 20.6以上/npm、FFmpeg、Visual Studio 2022 C++ Build Tools、NVIDIAドライバーの有無とGPU名を表示します。インストール・重み取得・仮想環境作成は行いません。`ExecutionPolicy Bypass` はこのPowerShellプロセスだけに適用し、PCの恒久設定を変更しません。研究室の管理ポリシーに従って実行してください。

3. [モデルのライセンス記録](../reports/licenses.md) と [NVIDIA Open Model Agreement](https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-agreement/) を確認します。テキスト処理には [Meta-Llama-3-8B-Instruct](https://huggingface.co/meta-llama/Meta-Llama-3-8B-Instruct) の利用承認も必要です。Hugging Faceアカウントで先に承認を受けてください。
4. 規約に同意した利用者が、次のコマンドを実行します。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup-windows.ps1 -InstallPrerequisites -AcceptModelLicense -Start
```

必要な前提ツールをwingetで導入し、アプリ用`.venv`とモデル別の仮想環境を作ります。C++ Build Tools等の導入時にはWindowsの管理者承認が必要になることがあります。既存ツールがそろっていれば `-InstallPrerequisites` を省略できます。wingetが利用できない場合の導入項目は下表を参照してください。

初回のテキストモデル取得では、Hugging Faceの読み取りトークンを**非表示の入力欄**へ入力します。トークンはセットアップのプロセス内だけで保持し、設定ファイルやログへ保存しません。既存の`HF_TOKEN`環境変数も利用できます。アクセス承認前のアカウントでは停止するため、承認後に同じコマンドで再開します。

5. セットアップと実生成検査が成功したら、このPCのブラウザで **http://127.0.0.1:8765** を開きます。PowerShellのウィンドウは起動中そのまま残します。Ctrl+Cでアプリを停止します。

## 次回から

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start-windows.ps1
```

ブラウザで同じURLを開きます。取得済みモデルを使い、外部テキストAPIやNVIDIA公式オンラインデモへ入力を送信しません。起動時に重みを追加ダウンロードしません。

## 発話文10通りの生成・時間比較

アプリを起動したまま、別のPowerShellで次を実行します。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run-ardy-examples.ps1 -Models "ardy,kimodo,text_to_vrma"
```

短い発話5通り（3秒）と中程度の発話5通り（6秒）を、同じ指定英訳・長さ・seed 0で3経路へ順番に渡します。合計30件です。アプリの同じジョブ待ち行列を使い、GPU上でモデルを並列実行しません。

中程度だけなら `-Group medium`、短い文だけなら `-Group short` を追加します。ARDYだけなら `-Models ardy` を指定します。入力文は [configs/ardy-utterances.json](../configs/ardy-utterances.json) を事前に編集できます。

| 区分 | 入力例 | モデルへ渡す英訳 |
|---|---|---|
| 短い発話 | こんにちは | `Hello.` |
| 短い発話 | ありがとう | `Thank you.` |
| 中程度 | 今日は新しい研究のアイデアを思いつきました。みなさんの意見を聞かせてください。 | `I came up with a new research idea today. I'd like to hear what you think.` |
| 中程度 | 説明が少し分かりにくかったかもしれません。もう一度、順番に説明します。 | `My explanation may have been a little unclear. Let me go through it again, step by step.` |

発話文の英訳をそのままモデル入力にします。会話ジェスチャーへの適合性は未検証で、音声入力はありません。画面の「ARDY：発話文の試行」から各文を個別に入力することもできます。

各成功ケースで、**骨格までの秒数・MP4までの合計秒数・書き出しのみの秒数・MP4リンク**を端末に表示します。`.motion-lab/batches/<日本時間の日時-ID>/summary.csv` と `records.json` を各試行後に保存します。失敗した入力はエラー行として残し、後続入力を続けます。MP4そのものは `outputs/<実験ID>/video.mp4` です。

| CSV項目 | 測定範囲 |
|---|---|
| `skeleton_seconds` | 入力から正規化骨格JSONを保存するまで。モデル読込・CPUテキスト処理・GPU生成・取得・変換を含む |
| `mp4_render_seconds` | 骨格JSONからフレームを描画し、FFmpegでMP4を保存する時間 |
| `total_seconds` | 上記2つの合計。待ち行列・利用者の操作待ち・初回セットアップを除く処理時間 |

同じ値を画面の「骨格まで」「MP4まで（合計）」と実験JSONにも記録します。「時間をCSVで取得」で全実験をExcel向けUTF-8 BOM付きCSVに保存できます。以前の動画や取り込みで測定されていない時間を推定して埋めません。

## text-to-vrmaの比較方式

[text-to-vrma](https://github.com/Kirakun0328/text-to-vrma) は **ARDYエンジン**を選択します。独立した動作モデルではなく、同じARDY Core8の出力へ公式のリターゲット・後処理・VRMA出力を加えた比較経路です。モデル本体とLlamaキャッシュは共有し、公式のPythonエンジンは1ジョブごとに起動・終了します。

LLM planner、Codex、Jev、追加の有料API、日本語自動翻訳は使いません。英訳をそのまま渡し、公式Python APIへseed 0を指定します。公式Node側の `generateMotionWithArdy` と `buildVRMA` を使用し、公式ソースは変更しません。Nodeの依存は公式npm lockを使ってruntimeのみ導入し、Electronは導入しません。

元 `.vrma` とspec JSONを保存し、VRMAに含まれる骨格階層・クォータニオン・hips軌跡からFKで共通の関節位置へ変換します。表情・視線は元VRMAに保持されますが、共通の骨格MP4には反映しません。公式後処理・履歴長40・腕の開き6度・CFG 3.0等の差をメタデータに記録します。直接ARDYは後処理なし・公式10秒窓の履歴・CFG 2.0です。同じ重みを使い、パイプラインの設定が異なることを踏まえて比較してください。

## 導入するもの

| 場所 | 内容 |
|---|---|
| `.venv/` | アプリ用Python依存 |
| `.motion-lab/envs/kimodo/`、`envs/ardy/` | モデルごとの専用Python環境 |
| `.motion-lab/upstreams/text_to_vrma/node_modules/` | text-to-vrmaのNode依存。Python・重みはARDY環境を共有 |
| `.motion-lab/checkpoints/` | モデル重み、公式LFS SHA-256照合記録 |
| `.motion-lab/hf-cache/` | Llama・LLM2Vecの共有キャッシュ。safetensorsを取得しoriginal PTHの重複取得を避ける |
| `.motion-lab/outputs/<実験ID>/` | 元NPZ、変換JSON、実験記録、MP4 |
| `.motion-lab/lab-verification/` | 初回のモデル別実生成検査の結果とMP4パス |
| `.motion-lab/logs/` | 秘密値を伏せた導入ログ、CUDA演算確認、モデル環境のpip freeze |
| `.motion-lab/lab-setup.json` | 完了した工程・構成の記録 |

初回の成功時は**MP4の絶対パス**を表示します。アプリの実験一覧にも同じ結果が現れます。その後の生成では「動画を作成」でMP4を取得してください。これらの重み・環境・生成結果はGit管理外です。

別ドライブへ重みと成果物を保存する場合は、セットアップ・起動の両方で同じ指定を使います。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup-windows.ps1 -AcceptModelLicense -DataDir D:\MotionLabData -Start
powershell -NoProfile -ExecutionPolicy Bypass -File .\start-windows.ps1 -DataDir D:\MotionLabData
```

## このPCに合わせた設定

[configs/lab-windows.json](../configs/lab-windows.json) を事前設定して配布できます。既定ではKimodo・ARDY・text-to-vrma（ARDY）を導入し、モデルは順番に実行します。Kimodoだけを先に導入する場合は `models` を `["kimodo"]` にしてください。text-to-vrmaを含める場合は、共有環境を準備する `ardy` を先に指定します。

- RTX 5070向けに **PyTorch 2.9.0 + CUDA 12.8 (`cu128`)** を選びます。既存installerの旧既定cu126を使うLinux手順とは別です。実際のGPU行列演算でカーネル互換性を検査します。
- **テキストエンコーダーはCPU、動作生成はGPU**です。12GB VRAMへLlamaと動作モデルを同時に載せる構成を避けます。ARDYは公式APIへCPU側の実エンコーダーを渡します。無条件診断への置き換えはしません。
- RAM 32GBでCPU側の8Bエンコーダーを使う構成を用意していますが、実ピークRAMと速度は未測定です。Ryzen 5700XでのCPUテキスト処理が待ち時間の主因になる可能性があります。
- 初回にデータ保存先ドライブの空き40GiBを確認します。必要な前提ツールを導入するドライブの追加容量は、そのWindowsインストーラー側で別途確認してください。
- WindowsのNVIDIAドライバーは研究室側で更新・管理します。スクリプトはドライバー、システムCUDA Toolkit、TensorRT、ファイアウォール、外部公開設定を変更しません。CUDAランタイムは仮想環境内のPyTorch wheelを使います。

## 再実行・失敗時

同じコマンドを再実行できます。完了した環境構築工程を構成ハッシュで再利用し、既存の重みはSHA-256を照合します。仮想環境・公式ソース・重み・生成結果を削除せず、取得済みデータを保持します。公式ソースのコミットが違う場合や重みが変更されている場合は、自動上書きせず停止します。

CUDA確認・テキスト条件付き生成・MP4書き出しのいずれかが失敗したモデルは準備完了にしません。GPUが利用できない場合にCPUや人工サンプルへ自動で置き換えません。`lab-setup.log` と `outputs/<実験ID>/inference.log` で原因を確認してください。

Python依存のうちアプリはlock、モデル本体は公式ソースのコミットとPyTorch/CUDA版を固定しています。**Windows/CUDAモデル環境の推移的な依存すべてを事前lock済みという意味ではありません**。実機で解決されたバージョンは環境別pip freezeに残します。

| 問題 | 対応 |
|---|---|
| Pythonが見つからない | Python 3.12 x64を導入。winget ID: `Python.Python.3.12` |
| Git/Node/npm/FFmpegがない | winget ID: `Git.Git`、`OpenJS.NodeJS.LTS`、`Gyan.FFmpeg` |
| C++ビルドで失敗 | Visual Studio 2022 Build Toolsの「C++によるデスクトップ開発」とWindows SDKを導入 |
| NVIDIAドライバー/CUDA演算で失敗 | 管理者にRTX 5070対応ドライバーを確認してもらう。スクリプトは勝手に更新しない |
| HF 401/403 | Llama利用承認と読み取りトークンを確認。値をチャットやログに貼らない |
| インストール直後にツールが見つからない | PowerShellを閉じて開き直し、同じコマンドを再実行 |
| パッケージ解決やMSVCビルドが失敗 | 完了とは扱わずログを確認。Windows実機の結果を受けて依存・ビルド設定を調整 |
