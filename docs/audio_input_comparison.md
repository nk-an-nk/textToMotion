# 音声入力から教師の返答・動作生成を比較する

リポジトリは **https://github.com/nk-an-nk/textToMotion の work ブランチ**です。従来の動画・実装は保持し、新しい処理は専用スクリプトに分けています。

生徒の「先生、こんにちは！」は、PCM音声をRealtimeの `input_audio_buffer.append` へ送り、`commit` して処理します。生徒の文字を `input_text` へ送る処理はありません。音声認識結果と実際に生成された教師の返答文を検証してから、動作モデルへ渡します。

教師の返答は比較条件を固定するため「こんにちは！今日も元気そうだね！英会話の練習を始めましょう」に指定しています。発話文の文字列が実際の音声書き起こしと一致しない場合は成功と数えません。日本語を英語の動作命令に置き換えず、全文を入力しています。

## 2026-10-14の実測

生徒が話し終えた時点を0秒とします。各行で音声入力とRealtime応答を実行し、その後にモデルを起動して新規生成しました。1回ずつの測定です。

| モデル | 最初のRealtime音声 | 動作完了を観測 | 動作の処理のみ | Realtime音声からの追加待ち |
|---|---:|---:|---:|---:|
| Kimodo | 0.811秒 | 15.395秒 | 10.561秒 | 14.584秒 |
| ARDY | 0.568秒 | 187.660秒 | 19.323秒 | 187.092秒 |
| MotionLCM | 1.049秒 | 19.242秒 | 0.421秒 | 18.193秒 |
| MoMask | 0.824秒 | 24.082秒 | 0.707秒 | 23.259秒 |
| MMM | 0.880秒 | 23.828秒 | 0.548秒 | 22.948秒 |
| ReactMotion | 1.218秒 | 18.998秒 | 1.000秒 | 17.780秒 |
| MaAI | 0.773秒 | 19.606秒 | 1.604秒 | 18.833秒 |

「動作完了を観測」は、実際の音声入力終了からモデル読み込み、アップロード、起動、完了確認までを、同じクライアントの単調時計で測った値です。RunPodの完了確認は5秒間隔なので、最大5秒の確認待ちと通信も含みます。異なるマシンのUTC時刻を引いて応答遅延を作ってはいません。Kimodoは公式オンラインサービスの推論で、ローカルRTX4090の速度ではありません。

ARDYはLlama/LLM2VecをCPUで読み込み、CPUでテキスト特徴を計算してから、Core8をCUDAで実行します。この行には取得済み言語モデルの再読み込み約128秒も含みます。初回ダウンロードを含む別の読み込みは約641秒でした。動作処理19.323秒はCPU特徴計算8.123秒とGPU側の生成・正規化11.200秒の合計です。

起動待ちを減らすにはモデルを常駐させます。同一5文のバッチでは、読み込み後のMotionLCMが約0.037～0.041秒、MoMaskが約0.196～0.207秒、MMMが約0.038～0.071秒でした。バッチの最初の生成には初回処理の追加時間があります。これらは会話全体の応答時間ではありません。

## 動画の見方

[7モデルのデモ・共通入力の動画とCSV](../reports/model-comparison/runpod-20261014/README.md)に保存します。生徒の音声、文字起こし、Realtime最初の音声、動作完了、教師の発話開始を表示します。

動画は**実測した待ち時間を再現するオフライン再生**で、ライブ画面の録画ではありません。生徒は録音済みの合成音声です。マイクがないクラウド環境で実音声データを受信する流れを検証しました。待ち時間は短縮せず、教師の音声を動作完了まで保留し、教師の音声とジェスチャーを同じフレームで開始します。静止した待機画面の時計更新は1秒単位、生成後は30fpsです。

ReactMotionは生徒の書き起こしから**聞き手の全身反応**を生成します。MaAIは生徒の実音声から**頭部のうなずきパラメーター**を予測します。全身の話者ジェスチャーと同じ出力能力ではありません。会話デモでは教師の返答時に聞き手反応を再生することを記録し、共通5文の聞き手動画では口を動かしません。MaAIの胴体はアバターの基本姿勢で、学習済み全身生成として数えていません。

1920×1080、30fps、H.264 CRF16、AAC192kbpsです。アバターを正面に置き、表示用の骨格全体から各フレームの胴体yawを除去して根元を固定しています。元の骨格座標は保存しています。位置からのリターゲットには手首のひねりや厳密な足接地の復元に限界があります。

## 研究室PCで再現する

Ryzen7 5700X / RTX5070 12GB / RAM32GB / SSD1TB / Windowsを想定します。[Windowsの既存セットアップ](windows_lab.md)でGit、Python3.12、Node/npm、FFmpeg、アプリを準備した後に、追加モデルを専用venvへ導入します。

```powershell
git clone --branch work https://github.com/nk-an-nk/textToMotion.git
cd textToMotion
# 既にclone済みなら、既存の変更を確認してから git fetch origin work / git switch work / git pull --ff-only origin work
.\.venv\Scripts\python.exe scripts\setup_comparison_models.py --models motionlcm momask mmm reactmotion maai --download --accept-model-license
```

`--accept-model-license` は公式コード・モデル・データの規約を読んだ利用者が指定します。重みとVRMをGitへ再配布しません。Windowsの追加5モデルは今回のLinux検証を基にした手順で、Windows実機の完了確認はまだ行っていません。LinuxでMaAIを導入する際はPortAudio開発パッケージも必要です。

Python3.12、PyTorch2.8、CUDA12.8版を使います。古いCUDA版PyTorchへ置き換えず、RTX5070で実際のCUDA行列演算を確認します。今回の実測GPUはRTX4090 24GBで、各推論プロセスのPyTorch allocatorを12,227MiB、CPUスレッド・affinityを8へ制限しました。GPU名、実際のピークVRAMとRAMを記録します。OS・GPU世代・CPU速度・レンダラーは研究室PCと異なり、RTX5070の実測値としては扱いません。32GB RAMのハード上限をPodに設定した試験でもありません。ARDYのCPUテキスト処理のピークRAMは約14.4GBでした。

共通入力は `configs/segmented_english_lesson_common.json` です。`scripts/measure_realtime_response.py` で5文の実音声を生成・計測し、`scripts/generate_humanml_comparison.py` と `scripts/generate_listener_comparison.py` に同じ入力と音声ディレクトリを渡します。各出力は `timings.json` と `motion-generation.json` に保存します。音声認識込みの測定は `scripts/measure_audio_dialogue.py`、RunPodへの実生成まで測る検証用クライアントは `scripts/measure_audio_motion_dialogue.py` です。

研究室でのマイク入力は既存の `/conversation` 画面のRealtime接続・マイクボタンを使います。生徒の音声をWebRTCで送信し、音声認識結果から返答を開始します。今回の専用CLI検証と、マイク＋WebRTC＋ローカルモデルを組み合わせた実機のライブE2Eは別の検証です。CLIのRunPod用HTTPSブリッジは研究室のローカル実行に必要ありません。

ReactMotionの日本語には未知トークンがあり、HumanML3D系モデルも英語の動作記述を中心に学習しています。今回は入力を統一して速度を検証しました。文に合った教育用ジェスチャーの品質は、同じ入力の動画で別途評価してください。

共通5文のARDYではCPU特徴量を事前計算し、`skeleton_seconds` はCPUエンコード＋CUDA生成の処理時間の合計です。処理間の準備・待ち時間を含む実際の経過時間とは区別します。音声入力の会話表はこの事前計算を再利用せず、実際の返答文の受信後にエンコード・生成を実行して全体の経過時間を測っています。

研究室PCで録音済み音声からローカルモデルの処理まで一度に計測する場合、同じPowerShellのプロセスへAPIキーを非表示入力してから実行します。音声はmono PCM16 / 24kHz、出力先は未使用ディレクトリを指定します。

```powershell
$secureKey = Read-Host "OpenAI API key" -AsSecureString
$keyPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
try { $env:realtime = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPtr) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPtr) }
.\.venv\Scripts\python.exe scripts\measure_audio_motion_dialogue.py --backend local --model motionlcm --student-wav student.wav --output .motion-lab\lab-dialogue-motionlcm
Remove-Item Env:realtime
```

`--model` は7モデルを選べます。モデル・重み・GPUを事前に導入し、ARDYの利用承認・CPUエンコーダー検査も既存セットアップで完了させます。上記のlocal経路はRunPodやSSHを使いません。実機Windowsでのライブ統合は未検証です。動画素材の準備は `scripts/prepare_audio_dialogue_video.py`、書き出しは `scripts/export_audio_dialogue.cjs` を使用します。MaAIの公式うなずき補間は `scripts/synthesize_maai_head_controls.py` を専用MaAI環境で実行します。どの経路も元の予測・骨格を保持します。

MaAIの今回の生徒挨拶は最大 `p_nod=0.3219` で、表示閾値0.5を超えませんでした。会話デモにはうなずきを追加していません。共通5文では3イベントを検出し、公式 `maai.util.generate_natural_nod` で補間してVRMの頭部へ適用しています。
