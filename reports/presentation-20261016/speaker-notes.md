# 音声対話 × Text-to-Motion × VRM：報告スライド原稿

報告日：2026-10-16（日本時間）。本編18枚、付録12枚。全18本の動画をPowerPoint内に埋め込み。

## 01. 音声対話 × Text-to-Motion × VRM

生成速度・会話の応答遅延・費用・研究室PCでの実行を検証

既存の実推論・音声入力・動画・CSVを再集計した報告。追加のGPU課金やモデル推論は実施していない。実験日の原記録はUTC、報告日は日本時間。

出典：報告日 2026-10-16（日本時間） / nk-an-nk/textToMotion / work

## 02. 生成単体の高速化は確認。会話の待ち時間には課題が残る

「生成が速い」と「会話の返答が速い」を分けて評価する

MotionLCMはRTX4090で初回を除く4つの異なる区間の中央値。Kimodoの0.435秒はB300、149フレーム、3反復の中央値。3.252秒は別の実音声入力会話1回の値であり、同じ統計量や実行条件ではない。

出典：[R1] common/*/motion-generation.json  [R3] benchmark/summary.json  [R4] dialogue-times.csv

## 03. 目標は、音声の返答と上半身ジェスチャーをそろえること

評価対象：録音した生徒音声 → Realtimeの実応答 → 新規の動作生成 → VRM表示

学生は録音済み合成音声を実時間で送信。生マイクの連続会話や自由回答の試験ではない。基準時刻は生徒の発話終了。教師の全文を受信してから動作を生成し、教師音声は骨格受信まで保留する。

出典：[R2] audio-response-times.csv  [R4] dialogue-*/measurement.json

## 04. 7モデルを実生成。出力する役割が異なるモデルを含む

話し手のジェスチャー、聞き手の全身反応、頭部反応を区別する

text-to-vrmaはARDYを用いる変換・後処理経路であり独立した動作モデルではない。公式Node関数と形式変換は確認したが、今回の7モデル実測に実生成データは含まない。MaAIは生徒音声を使い、ReactMotionは会話デモで生徒の認識文を使う。

出典：[R1] common-input-times.csv  [R2] README.md  [R8] model_compatibility.md

## 05. 研究室PCの制約を意識しつつ、GPU環境を段階的に拡張

RTX 4090の制限実験とB300実験は、RTX 5070 / Windowsの実測ではない

RTX4090はCPUスレッドとaffinityを8に設定、PyTorch allocator上限を12227MiBに設定。GPU自体は24GBであり12GB GPUそのものではない。RAM32GBのハード上限は未設定。B300はCPU推論8スレッド、ホスト可視192論理CPUを割当コア数と混同しない。API観測の割当は24vCPUと251GB。Kimodoの旧共通5文は4090ではなく公式オンラインL40S表示の経路。

出典：[R5] reproducibility/hardware.json  [R6] benchmark/hardware.json  docs/windows_lab.md

## 06. 共通の英語学習5区間と、生徒→先生の短い会話を使用

日本語・英語を含む利用者指定文を、英訳や動作命令に置換せず入力

共通5文の後期比較は原文をそのまま使用。最初期の文分割デモは発話に合わせた英語動作命令を使っており、その結果を後期共通入力と混同しない。ReactMotionとMaAIは聞き手として評価。会話の教師返答は固定しており自由回答の試験ではない。

出典：[R1] common-input-times.csv  [R2] audio-input-dialogue/*/measurement.json

## 07. 計測を3段階に分け、Realtimeとの差を明確に定義

同じ「生成時間」でも、読み込み・通信・描画を含むかで値が変わる

T_audioは生徒発話終了から最初の教師音声チャンク受信まで。T_boneは同じ起点から骨格受信または動作完了観測まで。差はT_bone−T_audio。スピーカー再生の物理遅延、口形の音素一致、運動品質の誤差ではない。動画では両方を同一フレームで開始するよう音声を保留。MP4書き出しはCPU処理。

出典：[R1–R4] 計測CSV・measurement.json / docs/audio_input_comparison.md

## 08. 共通5区間の記録：生成処理と動画化を別々に保存

GPU・入力処理・役割が異なるため、この表だけでモデルの性能順位は決められない

Kimodoは公式オンラインでテキスト処理と通信を含む骨格取得時間。ARDYはCPUテキスト特徴を事前計算し、その実処理時間をCUDA生成に加算した。モデルロードは別、会話版では実際に受け取った教師全文からエンコードする。MaAIは同じ発話の音声を使う。描画はCPU SwiftShaderで一部並行実行。UTC入力→MP4経過時間は待ちや再描画が入るため速度比較に使わない。

出典：[R1] common-input-times.csv / 値は各5区間の合計

## 09. 同じRTX 4090・入力5区間ではMotionLCMが最短

初回を除く4区間の中央値。文と生成長は区間ごとに異なる（48〜72フレーム）

MotionLCM 0.0388537359秒、MMM 0.0607730370秒、MoMask 0.2023586521秒。これは同一文の反復中央値ではなく異なる4文の中央値。初回区間は40フレームで0.414、0.527、0.705秒。GPUピークはTorch allocated値で全デバイス使用量や必要VRAMの保証ではない。各モデルの意味適合性・品質は未採点。

出典：[R1] common/{motionlcm,mmm,momask}/segments/*/motion-generation.json

## 10. 従来の会話経路では、起動・中継の待ちが大きかった

生徒の発話終了を0秒とする。各モデル1回、常駐化前の実測

完了観測の時間は純粋な骨格生成ではない。ローカルGPU経路は起動とモデルロード、RPC、最大5秒の完了ポーリング等を含む。ARDYは言語モデルの読込・CPUエンコードも実施。Realtime接続の旧3秒終了待ちもある。Kimodoは公式オンラインである。ReactMotion/MaAIの聞き手反応を先生のジェスチャー品質ランキングに使わない。

出典：[R2] audio-response-times.csv / Kimodoは公式オンライン、他はRTX 4090

## 11. Kimodo / B300：20ステップでは生成単体が1秒未満

同じ教師返答・149フレーム（約4.97秒）・batch=1・各設定3回の中央値

各設定を1回ウォームアップ後、seed0/1/2で計測。毎回テキスト特徴を再計算。入力処理、CUDA生成・復元、CPU転送、上半身JSON化まで含む。モデルロード・ネットワーク・動画化は除く。動作モデルfloat32、テキストエンコーダーbfloat16。TF32は許可設定であり全カーネルがTF32とは断定しない。torch.compileは使用せず、後処理も無効。100→20ステップの品質・FIDは未評価。

出典：[R3] benchmark/summary.json・hardware.json / Kimodo-SOMA-RP-v1

## 12. B300でも、骨格が届くまでの追加待ちは約3.25秒

別途実施した音声入力の会話：先生の全文を受信してから動作生成を開始

高速経路は最初の音声0.685386秒、全文1.673376秒、生成送信1.782977秒、骨格受信3.936996秒。追加待ち3.251610秒。内訳は全文待ち0.987990秒、送信まで0.109601秒、生成0.496237秒、中継・通知・保存用NPZ等を含む残差1.657782秒。残差は純粋なネットワーク遅延ではない。生成した長さは通常144frames/4.8秒、高速162frames/5.4秒で、前スライドの149framesとは別実行。GPUと常駐化、接続終了待ち短縮等を同時に変えており、旧15.395秒からの変化をGPUだけの効果とは扱わない。

出典：[R4] dialogue-{fp32-100,tf32-20}/measurement.json / 各1回・同一クライアント時計

## 13. 上半身・正面1080pのデモで、実測した待ち時間を確認

PowerPoint：画像をクリックして動画再生 ／ PDF：同梱mediaフォルダーのMP4を再生

この動画は実測した待ち時間を再現するオフライン再生でありライブ録画ではない。音声は実際のRealtime応答、動作は受信した全文から実生成。発話と動作を同一フレームにそろえて開始する。動画内の表示時刻と30fpsの切り上げにより、実再生開始は通常5.00秒、高速3.9667秒。PowerPointでは2本のMP4を埋め込む。PDFは静止画プレビューで音声動画は同梱MP4またはindex.htmlを使用。

出典：[R4] video-{fp32-100,tf32-20}/demo.mp4 / AvatarSample_VRM1.0・pixiv VRoid Project

## 14. 文ごとに発話・動作を同期し、連結する経路を実装

一括生成の既存コードは保持。文分割版・ARDY版・上半身版は独立した経路

初期の分割デモでは発話に対応する英語動作指示を使用。Kimodo骨格合計72.91秒、音声25.32秒、描画237.03秒、成功処理335.27秒。ARDY Horizon40コミュニティSpaceは骨格115.29秒、描画1038.91秒、成功処理1154.20秒、最初の入力からMP4完成1219.86秒。これらは後期Core8/4090の共通原文比較と異なる。区間音声の開始位置はPCM検査で0サンプル差。短い音声の区間はモデル最短長の骨格を生成して再生速度を調整、元骨格を保持。B300は全77関節を生成後、上半身67関節を抽出。腰・脚の表示を固定するため上半身専用モデルへの高速化ではない。

出典：[R7] segmented/english-lesson*/README.md  [R4] B300 README.md

## 15. B300の1会話は約5円相当。ただし借りている間は連続課金

$8.99 / 時、1ドル200円で換算。モデル常駐済み・起動と待機の費用は別

GPU料金は生徒音声入力開始から骨格受信までの約6.8725秒/5.8374秒を時間換算。骨格生成単体だけの費用0.97円/0.25円を総費用とは扱わない。Realtimeはinput text89/audio19、output text38/audio96（通常）、output text61/audio108（高速）。100万tokenあたりtext input$4/output$24/audio input$32/output$64。reasoning23tokensはoutput text61に含まれる内訳として二重加算しない。料金確認2026-10-15、確定請求額は未取得。ASR・ストレージ・起動・待機・動画化は合計から除外。研究用の録音済み入力作成費用も1会話の見積もりに含まない。

出典：[R4] usage・入力開始〜骨格受信  [R9] trial-cleanup.json  [P1] OpenAI公式モデル料金

## 16. 研究室PCでは、小型モデルから常駐実行を検証する

Windows / RTX 5070 12GB / RAM32GB。セットアップ用スクリプトと専用仮想環境を用意

SSH・WSL・Dockerを前提としないWindowsネイティブ手順。Python/Node/FFmpeg/BuildToolsを事前チェックし、専用venvと固定ソースを用いる。現物Windows/5070のビルドと実推論は未検証。Torchピークだけで必要VRAMを保証しない。KimodoのGPUテキストエンコーダー込み15.3GiB構成は12GBに収まらない。CPUテキストエンコーダーは公式に提供されるがCPU待ちが増える可能性があり5070で再測定する。初回loadやRAM容量、Blackwell対応CUDAビルドも確認が必要。

出典：docs/windows_lab.md / configs/lab-windows.json / [R1][R3] VRAM記録

## 17. 論文の順位との比較は限定的。品質を含む優劣は未確定

ユーザー提示のMoSCo比較表と、今回の実験では入力・生成長・計測範囲が異なる

MoSCo表はユーザーが提示した紹介画像から引用。原論文Table1の独立再検証や全14モデルの再現ではない。画像のAITSはMotionLCM0.030秒、MoMask0.120秒、RTX4090/HumanML3D。今回の初回を除く4文の中央値では0.039秒/0.202秒で順序は同じだが条件や統計量が違う。MoSCo本体、TEMOS、MotionMamba等は実行していない。FIDを今回の日本語会話ジェスチャーにそのまま適用して順位を決めない。

出典：[U1] ユーザー提示のMoSCo紹介画像（Table 1）  [R1] MotionLCM・MoMask実測

## 18. 次は常駐・短区間化と、品質評価を組み合わせる

GPUの大型化だけでは、今回の会話経路の追加待ちを1秒以内にできなかった

達成済みと未達を明示。B300で生成単体1秒未満は確認したが、会話での差は3.252秒。次の仮説はモデル常駐の徹底、全文完了前の短い意味区間での開始、Jupyter中継から直接サービスへの変更、保存用NPZ転送を同期経路から外す。これらの効果は未測定。複数音声・複数seed・反復回数を増やして品質とp50/p95を測り、5070Windows実機と同条件に近づける。

出典：判断根拠：[R1–R4] / 右の施策は提案であり、達成時間の予測ではない

## 19. 付録：初期調査からの到達点と、未測定の経路

古い「未実行」の記録を、後続の成功記録と混同しない

初期CPU環境では9モデルを調査しARDY無条件CPUとKimodo公式オンラインの動作指示を実行。後続でARDY Horizon40のテキスト条件付き生成、Core8のGPU実生成、7モデル比較とB300Kimodoを追加した。初期のStage3未達という表記は初期日付の範囲。会話内容の意味に合った自然なジェスチャーの品質検証は引き続き未達。text-to-vrmaは形式変換fixtureをモデル生成成功に数えない。

出典：[R7] segmented/english-lesson*/README.md  [R8] execution_results.md・model_compatibility.md

## 20. 付録：初期の文分割デモは、発話に合わせた動作指示を使用

共通原文5区間の後期比較とは、入力・モデル・サービス・描画条件が異なる

Kimodoは公式オンライン、ARDYはHorizon40の公開コミュニティSpace。両方とも原発話そのままではなく発話に合わせた英語動作指示を使用。ARDYの音声は既存のKimodo音声を共有し、追加OpenAI音声生成は0回。各動画は14.133秒、424フレーム、1080p/30fps。最短長制約を満たす新規骨格を生成し再生速度を調整した区間がある。これはライブ会話の待ち時間ではない。

出典：[R7] reports/segmented/english-lesson*/README.md / 成功処理の合計

## 21. 付録：計測原本・固定バージョン・再現手順

Gitリポジトリ：github.com/nk-an-nk/textToMotion / work　　実験コード基準：3a37d6e

R1=reports/model-comparison/runpod-20261014/common-input-times.csvと各生成JSON。R2=同audio-response-times.csvと各measurement.json。R3=reports/kimodo-b300-20261015/benchmark/summary.json/hardware.json。R4=同dialogue-times.csvとdialogue-*/measurement.json/video-*/demo.mp4。R5=旧reproducibility/hardware.json/source-and-weights.json。R6=B300environment.json/benchmark/hardware.json。R7=reports/segmented/english-lesson*/README.md。R8=reports/execution_results.md/model_compatibility.md。R9=両試験trial-cleanup.json。U1=ユーザー提示のMoSCo紹介画像（原論文独立検証なし）。P1=OpenAIのgpt-realtime-2.1公式モデルページ、2026-10-15に料金確認。B300ソース58e781898b3d7e328a676a75d3e338c45dce3ad9、checkpoint revision defbe1f34f5fd031eb0ccfe19f3f92a9880c287b。MNTPとsupervisedの各448tensor照合を通った経路のみ報告値に使用。学習済み重みとVRM本体は資料へ再配布していない。

出典：原本はGitのworkブランチ。再集計値・費用式は同梱measurements.json。

## 22. 付録：全18本のデモ動画をPowerPoint内に収録

モデル名・画像をクリックすると、会話と共通5文の動画スライドへ移動

7モデルの会話と共通5文で14本、B300比較2本、初期の文分割2本の全18本をPPTX内に埋め込む。画像は外部MP4へのリンクではなく埋め込み動画スライドへの移動。会話動画は実音声入力と実モデル生成の計測値を再現するオフライン再生。実マイクのライブ録画ではない。ARDYは187秒の待ちが含まれる。ReactMotionとMaAIは聞き手。MaAIは今回の挨拶では最大p_nod0.3219で0.5閾値を超えず、うなずきイベントを追加していない。

出典：[R2] audio-input-dialogue/*/demo.mp4 / AvatarSample_VRM1.0・pixiv VRoid Project

## 23. デモ動画：Kimodo / 話し手の動作

スライドショーで動画をクリックして再生。左右の動画は個別に再生できます。

Kimodoの会話動画と共通5文の動画を、切り詰めずに全編埋め込み。会話では実測した待ちを再現するオフライン再生。生成・API・動画の再実行は行っていない。PDFは静止画で、外部MP4への補助リンクを用いる。左右を同時再生すると音声が重なるため、発表時は1本ずつ再生する。

出典：[R1・R2] kimodo / AvatarSample_VRM1.0・pixiv VRoid Project

## 24. デモ動画：ARDY / 話し手の動作

スライドショーで動画をクリックして再生。左右の動画は個別に再生できます。

ARDYの会話動画と共通5文の動画を、切り詰めずに全編埋め込み。会話では実測した待ちを再現するオフライン再生。生成・API・動画の再実行は行っていない。PDFは静止画で、外部MP4への補助リンクを用いる。左右を同時再生すると音声が重なるため、発表時は1本ずつ再生する。

出典：[R1・R2] ardy / AvatarSample_VRM1.0・pixiv VRoid Project

## 25. デモ動画：MotionLCM / 話し手の動作

スライドショーで動画をクリックして再生。左右の動画は個別に再生できます。

MotionLCMの会話動画と共通5文の動画を、切り詰めずに全編埋め込み。会話では実測した待ちを再現するオフライン再生。生成・API・動画の再実行は行っていない。PDFは静止画で、外部MP4への補助リンクを用いる。左右を同時再生すると音声が重なるため、発表時は1本ずつ再生する。

出典：[R1・R2] motionlcm / AvatarSample_VRM1.0・pixiv VRoid Project

## 26. デモ動画：MoMask / 話し手の動作

スライドショーで動画をクリックして再生。左右の動画は個別に再生できます。

MoMaskの会話動画と共通5文の動画を、切り詰めずに全編埋め込み。会話では実測した待ちを再現するオフライン再生。生成・API・動画の再実行は行っていない。PDFは静止画で、外部MP4への補助リンクを用いる。左右を同時再生すると音声が重なるため、発表時は1本ずつ再生する。

出典：[R1・R2] momask / AvatarSample_VRM1.0・pixiv VRoid Project

## 27. デモ動画：MMM / 話し手の動作

スライドショーで動画をクリックして再生。左右の動画は個別に再生できます。

MMMの会話動画と共通5文の動画を、切り詰めずに全編埋め込み。会話では実測した待ちを再現するオフライン再生。生成・API・動画の再実行は行っていない。PDFは静止画で、外部MP4への補助リンクを用いる。左右を同時再生すると音声が重なるため、発表時は1本ずつ再生する。

出典：[R1・R2] mmm / AvatarSample_VRM1.0・pixiv VRoid Project

## 28. デモ動画：ReactMotion / 聞き手の反応

スライドショーで動画をクリックして再生。左右の動画は個別に再生できます。

ReactMotionの会話動画と共通5文の動画を、切り詰めずに全編埋め込み。会話では実測した待ちを再現するオフライン再生。生成・API・動画の再実行は行っていない。PDFは静止画で、外部MP4への補助リンクを用いる。左右を同時再生すると音声が重なるため、発表時は1本ずつ再生する。

出典：[R1・R2] reactmotion / AvatarSample_VRM1.0・pixiv VRoid Project

## 29. デモ動画：MaAI / 聞き手の反応

スライドショーで動画をクリックして再生。左右の動画は個別に再生できます。

MaAIの会話動画と共通5文の動画を、切り詰めずに全編埋め込み。会話では実測した待ちを再現するオフライン再生。生成・API・動画の再実行は行っていない。PDFは静止画で、外部MP4への補助リンクを用いる。左右を同時再生すると音声が重なるため、発表時は1本ずつ再生する。

出典：[R1・R2] maai / AvatarSample_VRM1.0・pixiv VRoid Project

## 30. デモ動画：文ごとの発話・ジェスチャーを同期して連結

初期の文分割デモ：発話に合わせた英語の動作指示を使用した別条件の実験

KimodoとARDY Horizon40の初期文分割動画を全編埋め込み。音声を共有し各区間の発話とジェスチャーを同じフレームで開始して連結した。後期の共通原文5区間比較とは入力と生成経路が異なる。2本とも既存の14.133秒、424フレームの完成動画。

出典：[R7] segmented/english-lesson* / AvatarSample_VRM1.0・pixiv VRoid Project
