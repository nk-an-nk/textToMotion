# 音声入力と7モデルの比較：動画・計測結果

生徒の「先生、こんにちは！」を録音済み合成音声としてRealtimeへ送信し、実際の音声認識・教師の返答から新規生成しました。生徒の文字列を入力として送信していません。各モデル1回ずつの実測です。動画は実測した待ち時間を再現するオフライン再生で、ライブ録画ではありません。

教師：**こんにちは！今日も元気そうだね！英会話の練習を始めましょう**

| モデル | 会話デモ | 共通5文の動画 | 最初の返答音声チャンク | 動作完了を観測（起動・通信込み） |
|---|---|---|---:|---:|
| kimodo | [MP4](audio-input-dialogue/kimodo/demo.mp4) | [MP4](common/kimodo/combined.mp4) | 0.811秒 | 15.395秒 |
| ardy | [MP4](audio-input-dialogue/ardy/demo.mp4) | [MP4](common/ardy/combined.mp4) | 0.568秒 | 187.660秒 |
| motionlcm | [MP4](audio-input-dialogue/motionlcm/demo.mp4) | [MP4](common/motionlcm/combined.mp4) | 1.049秒 | 19.242秒 |
| momask | [MP4](audio-input-dialogue/momask/demo.mp4) | [MP4](common/momask/combined.mp4) | 0.824秒 | 24.082秒 |
| mmm | [MP4](audio-input-dialogue/mmm/demo.mp4) | [MP4](common/mmm/combined.mp4) | 0.880秒 | 23.828秒 |
| reactmotion | [MP4](audio-input-dialogue/reactmotion/demo.mp4) | [MP4](common/reactmotion/combined.mp4) | 1.218秒 | 18.998秒 |
| maai | [MP4](audio-input-dialogue/maai/demo.mp4) | [MP4](common/maai/combined.mp4) | 0.773秒 | 19.606秒 |

0秒は生徒が話し終えた時点です。教師の音声を動作完了まで保留し、発話と動作を同じフレームで開始します。最初の音声チャンク受信と、スピーカーでの実再生開始は別です。RunPodの完了確認には最大5秒のポーリング待ちと通信が含まれます。

1920×1080 / 30fps / H.264 CRF16 / AAC192k。表示用に骨格全体の胴体yawを除去して正面へそろえ、根元を固定しています。元の骨格・予測は保持しています。GitHubで再生できない場合はDownload raw fileで取得してください。

ReactMotionは聞き手の全身反応で、会話デモでは生徒の音声認識結果を入力します。MaAIは生徒の実音声から頭部パラメーターを予測します。今回の挨拶では最大p_nod=0.3219で表示閾値0.5を超えず、うなずきを追加していません。共通5文では3イベントを検出し、公式MaAI補間を適用しました。胴体はアバターの基本姿勢です。

## 共通の英語学習文

全モデルに同じ5文をそのまま入力し、同じ実音声を使用しました。動作命令への変換・英訳・切り捨てはしていません。

1. こんにちは！
2. 今日も一緒に楽しく英語を勉強しましょう！
3. まずは英語で挨拶してみよう。
4. Hello! How are you today?
5. 元気なときは、I'm happy! って言ってみてね。

| モデル | 5区間の生成処理合計 | 読み込み後の1区間（初回を含む） | CPUによるMP4書き出し |
|---|---:|---:|---:|
| kimodo | 51.409秒 | 9.887～10.762秒 | 156.0秒 |
| ardy | 38.492秒 | 7.184～8.878秒 | 160.2秒 |
| motionlcm | 0.570秒 | 0.037～0.414秒 | 154.4秒 |
| momask | 1.512秒 | 0.196～0.705秒 | 154.8秒 |
| mmm | 0.757秒 | 0.038～0.527秒 | 156.5秒 |
| reactmotion | 2.597秒 | 0.280～0.837秒 | 238.6秒 |
| maai | 8.063秒 | 1.216～2.062秒 | 174.9秒 |

ARDYの共通5文は事前計算した公式LLM2Vec特徴を使用し、上表はCPUエンコード＋CUDA生成の処理時間です。音声入力の会話デモは実際の教師返答を受信してから言語モデルの読み込み・エンコードも実行して測っています。入力からMP4保存までのUTC経過時間は準備・待ち・再描画も含むため、単純な生成速度には使いません。CSVに処理時間と経過時間を分けて記録しました。

HumanML3D系・ReactMotionの日本語への意味的適合性は別途品質評価が必要です。旧英語動作命令の動画は既存reports/segmentedに保持しています。

## CSVと記録

- [音声入力→Realtime→動作完了の実測](audio-response-times.csv)
- [同一5文の生成・描画時間](common-input-times.csv)
- [同文の別リクエストで測ったRealtimeと骨格処理時間の差](separate-stage-latencies.csv)
- [PC・GPU・描画条件](reproducibility/hardware.json)
- [固定ソース・重みSHA256](reproducibility/source-and-weights.json)
- [モデル別環境バージョン](reproducibility/)
- [GPU終了・費用見積もり](trial-cleanup.json)
- [実装と研究室Windowsの再現手順](../../../docs/audio_input_comparison.md)

実機はRTX4090 24GB / Linux / AMD EPYCです。推論のCPUスレッド・affinityは8、PyTorch allocator上限は12,227MiB。32GB RAMのハード上限は設定していません。RTX5070 Windowsの実測値ではありません。骨格生成はCUDA、動画はSwiftShader CPUです。一部の描画・ロードが並走した実行値で、CPU描画時間も研究室PCと同一条件ではありません。

GPU Podは成果物回収後にTerminateし、APIで削除確認済みです。元VRMと約7.6GBの取得済み重みの控えはプライベートに保持し、Gitへ再配布しません。アバターの動画にはpixiv VRoid Projectを記載しています。Realtimeのusageは各JSONに保存していますが、最終API請求額は未取得です。

Python112テスト、JavaScript22テスト、ブラウザ13テストが成功し、ライブWebRTC＋ローカルGPU統合のブラウザテスト1件は未実行です。録音音声のRealtime WebSocket入力と実モデル生成は上記7モデルで別途実行しました。
