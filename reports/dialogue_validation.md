# 対話VRM統合の検証記録

検証日: 2026-10-14（日本時間）。開始時は `work` / `6697dda`、未コミット変更なし。既存のFastAPI・Three.js・モデルアダプター・VRMA変換・Windowsセットアップを拡張しました。

## 追補：正面・1080pと英語学習の発話

利用者指定の `configs/demo_english_lesson.txt` をRealtime APIへ入力し、日本語と英語を含む音声を実生成しました。要求した文章と実書き起こしは完全一致です。音声は12.50秒、生成処理は7.54秒、API使用量は input 136 / output 343 / total 479 tokensです。

正面カメラと白飛びを抑えた照明へ変更し、1920×1080・30fpsで各フレームを描画するオフライン書き出しを追加しました。無損失PNGからH.264 CRF 16へ変換し、音声は元WAVから直接AACへ変換します。13.50秒・405フレームの2本の動画に、保存済み3秒のKimodo/ARDYモーションと、残りの発話中のデフォルト動作・口の開閉を使いました。新規学習済みジェスチャー生成の成功には数えません。

正面カメラのリセット、実VRMと保存済みKimodo/ARDYの再生、公式VRMA再生のブラウザテストは **3 passed** でした。[映像の検査記録](videos/english-lesson-validation.json) にネイティブ解像度、全フレーム数、正面方向、音声の一致と再生結果を記録します。[完成した動画](videos/README.md) と [再現方法](../docs/vrm_recording.md) を参照してください。

## 追補：実Realtime音声と音声付きVRM録画

2026-10-14（日本時間）、利用者のPublish後に `realtime` の認証を実行環境で確認し、実際のOpenAI Realtime GA WebSocket / `gpt-realtime-2.1` / `marin` から「こんにちは。よろしくお願いします。」の音声を生成しました。WAVは3.00秒、生成処理の所要時間は5.20秒、API使用量は input 58 / output 79 / total 137 tokensです。実請求額は計測していません。

同じ音声を、保存済みKimodo右手を振るモーションとARDY無条件CPU診断モーションへ組み合わせ、実VRMの音声時計に沿った再生と口の開閉をMP4へ録画しました。新規Text-to-Motion生成、発話からARDYへの条件付け、ライブWebRTC会話とGPU推論を組み合わせたE2Eは未実施です。

[元音声とAPI記録](audio/realtime-hello.json)、[2本の音声付き動画](videos/README.md)、[録画の検査結果](videos/voice-recordings-validation.json) に根拠を保存しています。両動画のH.264＋AAC、全デコード、元音声との波形一致、描画姿勢の変化、口の開閉、ブラウザエラーなしを確認しました。

## 実行した検証

次の表と受入シナリオは初回の統合検証時点の記録です。追補で確認した実API音声生成は上記に区別して記録しています。

| 検証 | 結果 | 範囲 |
|---|---|---|
| 変更前Python | 71 passed | 既存機能の基準 |
| 変更前Chromium | 5 passed | 既存ビューアー・音声時計・CSV |
| Python全体 | **85 passed、失敗0、skip 0** | GA SDP形式、予算・認証ガード、翻訳、非同期取消、別GPUサービスのプロキシ、研究保存、既存の変換・動画 |
| JS制御・出力 | **16 passed、失敗0** | 0/1/3/10秒遅延、期限、割り込み、音声時計、Text-first整合性、Recorded/Kebbi出力、マイク許可待ちの取消 |
| Chromium全体 | **12 passed、失敗0、1 skipped** | 実VRM・保存済み学習済み結果、公式VRMA、連続再生、準備中の停止、オフライン音声・制御、既存画面 |
| PowerShell | **6ファイル構文OK** | Linux上のPowerShell 7.5.4による構文検査。Windows 5.1実機実行ではない |
| アプリだけの導入 | 初回・再実行OK | `scripts/setup_conversation.py`、依存チェックとアプリimport |
| 実サーバー起動 | OK | `scripts/start_conversation.py`、health・設定・HTML・VRMライブラリ・日本語計画の機能要求 |
| 実Realtime＋新規GPU推論 | **未実施** | APIキー・実行予算・CUDA GPUがないため、live E2Eをskip |

機械可読結果は [Python XML](dialogue-python-tests.xml)、[制御テスト](dialogue-unit-tests.txt)、[Chromium XML](browser-tests.xml) にあります。通常のブラウザ検証は有料APIを無効化した専用サーバーを使用し、実Realtimeへの接続を行っていません。

途中で、履歴の最後の行を選ぶ既存テストの仮定と、初回実験一覧読込より先に「起動済み」を表示する競合を検出しました。特定の実験IDで選択し、一覧読込後に起動済みを表示するよう修正しています。アサーションを削除したり、音声時計の許容誤差を広げたりしていません。

## 受入シナリオとの対応

| シナリオ | 検証済み | 未検証 |
|---|---|---|
| 1 通常会話 | 定型日本語・実ローカル音声時計・デフォルト動作 | Realtimeによる日本語の実会話・マイク |
| 2 意味的ジェスチャー | 嬉しい会話の計画、優先度、元文・英語指示保存 | 生成動作の意味的一致・自然さ |
| 3 右手を振る | 保存済みの実Kimodo出力→実VRM表示 | この統合アプリからの新規GPU生成＋実音声 |
| 4 遅延 | 制御の0/1/3/10秒、ブラウザの1秒遅延と短い期限での破棄 | 実API・GPUでの遅延分布 |
| 5 割り込み | 音声停止、ターン無効化、キュー取消、実行済み結果の再適用拒否 | 実マイク割り込みと実WebRTC接続 |
| 6 モデル不足 | バックエンドで実際の不足を検出、オフラインで動作不足でも再生継続 | 実Realtime会話中のGPU障害 |
| 7 VRM変換 | 身長の異なる自作VRM形式fixture2体、実AvatarSample1体、左右・有限値・脚長比・VRMAルート連続性 | 複数の第三者アバター、ねじれ・接地IK・人間の自然さ評価 |
| 8 実E2E | opt-in実テストと再現手順を実装 | **APIキー・GPU不足で未実施。モックの成功で代替しない** |

実アバターは別途取得済みの `AvatarSample_VRM1.0.vrm`（pixiv VRoid Project）をブラウザ内で読み込みました。モデル内のVRM 1.0メタデータは `avatarPermission=everyone`、`commercialUsage=personalNonProfit`、`allowRedistribution=false`。モデルファイルと検証スクリーンショットをこのGitリポジトリへ再配布していません。利用条件の公式URLもUIに表示します。

再生した既存結果はKimodo `9c59514de11744aeb0a97038e73c7e5d` とARDY `cfc9aaf72a0944cf8449a978df8d5e29`。ARDYは以前の**無条件CPU診断**です。どちらも今回の新規推論ではなく、保存済み結果のアバター適用検証です。音声は検証音または利用者が選択したWAVであり、AI音声生成の証拠ではありません。

## 仕様確認と制約

公式ガイドの `developers.openai.com`、AvatarSampleの利用条件サイトへのアクセスはクラウドのネットワーク設定で403でした。GA形式・モデル名・イベントは公式 `openai/openai-node` の現行生成済み定義で確認しました。

- `src/resources/realtime/realtime.ts` SHA-256: `649e40ef616f221e9c8fcf5573d5ddb41c31a244824d1fc54fb7d20fd547827e`
- `src/resources/realtime/calls.ts` SHA-256: `84b09f99bf6f894788cc251e12e613a47a180447ae443a1c6132ed1db0ac9c26`
- `gpt-realtime-2.1`、GA calls multipart、`response.output_audio_transcript.*`、`response.output_text.*`、`response.done`、WebRTCの音声バッファ開始・停止・clearを確認。初回は利用者アカウントのAPI利用権が未確認でしたが、追補の実WebSocket音声生成で同モデルの利用を確認しました。WebRTC calls経路は実接続未検証です。

予算は要求回数と事前予約枠のガードであり、実請求額の厳密なドル上限ではありません。出力デバイスの物理的な遅延、単語時刻、LLM内部の処理開始・終了、GPUピークメモリ、部分生成チャンクは未測定です。タイムスタンプの受信と実際の発声は分離しています。

JSONリターゲットは胴体基底と最小回転を推定します。関節位置だけでは求まらないねじれは復元しません。床補正は接地IKではなく、足滑りや汎用アバターへの完全な適合を保証しません。Kebbi出力は例外で拒否し、実機に指令を送信していません。

## 再開方法

[実行手順](../docs/conversation_vrm.md) にWindowsのアプリ導入・モデル準備・有料APIの明示許可・鍵の非表示入力・実E2E検証を記載しています。研究室PCでLlamaアクセスと実CUDA生成を準備し、OpenAI APIキー・利用予算・利用条件を確認したVRMを用意して `playwright.live.config.cjs` を実行してください。期限内の適用を確認できなければ、この最終条件は未達のままです。
