# 動画・証拠索引

## 公開許諾と来歴

動画に使ったアバターはVRM1_Constraint_Twist_Sample、© 2022 pixiv Inc.。実ファイルのVRMメタデータはavatarPermission=everyone、commercialUsage=corporation、allowRedistribution=true、modification=allowModificationRedistribution。モデル利用により得られた映像の公開は[VRM Public License 1.0](https://vrm.dev/licenses/1.0/)の第1条(14)、第2条(a)(1)とライセンス設定を根拠に確認。[実メタデータとSHA](logs/avatar_license.json)。VRM本体は配布しない。別のAvatarSampleの再配布不可VRMも含めない。OpenAI marinによる合成音声、テキスト入力は研究説明のみ。マイクや実在人物の録音なし。

基準環境はWindows / Ryzen 7 5700X / RTX 5070 / PyTorch 2.9.0+cu128 / CPU LLM2Vec。ライブ映像はGPU Direct3D11、失敗試行のみSwiftShader。各元記録は[experiments](logs/experiments/)に保存。以下の抜粋は同じライブ新規推論を撮影した動画の編集で、別の推論や保存済み動作を使った別会話ではない。

## MP4一覧

### [kimodo_demo.mp4](videos/kimodo_demo.mp4)

- 実験ID: `fb31b848c7c74f0aba06fd38ab998e62` / モデル: kimodo / パイプライン状態: succeeded
- 生成日時: 2026-10-14T18:20:29.476489+09:00（実験開始日時。動画編集日時とは区別）
- 元入力: Raise your right hand and wave for three seconds.
- 動作モデル入力: `Raise your right hand and wave for three seconds.`
- 内容: 今回の新規テキスト条件付きGPU生成。骨格描画、無音。
- 仕様: 3.000秒、640×480、h264、音声なし、0.03MiB
- 来歴: new_inference_skeleton / SHA-256 `949bc812f0115717c2ca6f006fbeabac6c80601d8c7da8f8af785b2f35dd97dd`

### [ardy_demo.mp4](videos/ardy_demo.mp4)

- 実験ID: `0934428dd4644c5d87d9816c352f901b` / モデル: ardy / パイプライン状態: succeeded
- 生成日時: 2026-10-14T18:21:24.904728+09:00（実験開始日時。動画編集日時とは区別）
- 元入力: こんにちは
- 動作モデル入力: `Hello.`
- 内容: 今回の新規テキスト条件付きGPU生成。骨格描画、無音。
- 仕様: 3.000秒、640×480、h264、音声なし、0.03MiB
- 来歴: new_inference_skeleton / SHA-256 `a98ecaff1b4bf8bed070b1d88b71ee3a867f5605ce642d6b126ffde40e33f381`

### [text_to_vrma_demo.mp4](videos/text_to_vrma_demo.mp4)

- 実験ID: `0492cb2804054a2b89046a7c5f6d469b` / モデル: text_to_vrma / パイプライン状態: succeeded
- 生成日時: 2026-10-14T18:35:00.602897+09:00（実験開始日時。動画編集日時とは区別）
- 元入力: こんにちは
- 動作モデル入力: `Hello.`
- 内容: 今回の新規テキスト条件付きGPU生成。骨格描画、無音。
- 仕様: 3.000秒、640×480、h264、音声なし、0.03MiB
- 来歴: new_inference_skeleton / SHA-256 `5ee596ff26dfd9050033c19f59cb663441085a580a6a135902b6880beaae240f`

### [realtime_late_cancelled.mp4](videos/realtime_late_cancelled.mp4)

- 実験ID: `753b2940004541ddbcb2a2b999eb4c61` / モデル: kimodo / パイプライン状態: cancelled
- 生成日時: 2026-10-14T19:03:45.385506+09:00（実験開始日時。動画編集日時とは区別）
- 元入力: 日本語で、研究用の音声対話アバターがどのように文章から声と動きを作るか、初心者向けに詳しく説明してください。音声認識、応答生成、動作生成、3Dモデルへの適用、遅延の課題について順番に、二十文以上、千二百文字程度で話してください。急がず、ゆっくり落ち着いて説明してください。
- 動作モデル入力: `Raise your right hand and wave for three seconds.`
- 内容: 実API音声は成功。動作は発話終了に間に合わず取消。動作成功動画ではない。
- 仕様: 89.059秒、790×538、h264、音声あり、3.15MiB
- 来歴: live_failure_recording / SHA-256 `7866106faffd703c6d1b050895b28f1a93a221549663a35998910bf869bfd305`

### [realtime_brief_gesture.mp4](videos/realtime_brief_gesture.mp4)

- 実験ID: `eaa34d251d0346df891192a86290bd36` / モデル: kimodo / パイプライン状態: succeeded
- 生成日時: 2026-10-14T19:06:49.407067+09:00（実験開始日時。動画編集日時とは区別）
- 元入力: 日本語で、研究用の音声対話アバターがどのように文章から声と動きを作るか、初心者向けに詳しく説明してください。音声認識、応答生成、動作生成、3Dモデルへの適用、遅延の課題について順番に、二十文以上、千二百文字程度で話してください。急がず、ゆっくり落ち着いて説明してください。
- 動作モデル入力: `Raise your right hand and wave for three seconds.`
- 内容: 初回GPU描画試行。新規動作採用、2秒の短い動作で見づらい。
- 仕様: 70.900秒、790×538、h264、音声あり、2.86MiB
- 来歴: live_new_inference_recording / SHA-256 `d0ff0ab7c667272a79b9d7d8bc3d804247570742eda7e3d49393ae75040153c2`

### [brief_gesture_excerpt.mp4](videos/brief_gesture_excerpt.mp4)

- 実験ID: `eaa34d251d0346df891192a86290bd36` / モデル: kimodo / パイプライン状態: succeeded
- 生成日時: 2026-10-14T19:06:49.407067+09:00（実験開始日時。動画編集日時とは区別）
- 元入力: 日本語で、研究用の音声対話アバターがどのように文章から声と動きを作るか、初心者向けに詳しく説明してください。音声認識、応答生成、動作生成、3Dモデルへの適用、遅延の課題について順番に、二十文以上、千二百文字程度で話してください。急がず、ゆっくり落ち着いて説明してください。
- 動作モデル入力: `Raise your right hand and wave for three seconds.`
- 内容: 上記録画の58秒以降の抜粋。同じ推論の再編集。
- 仕様: 12.000秒、790×538、h264、音声あり、0.52MiB
- 来歴: live_new_inference_recording / SHA-256 `408bae4543412cc90e072cc51ee8ec4533d71e68b5a79a9c5ae012289cafeb29`

### [realtime_conversation.mp4](videos/realtime_conversation.mp4)

- 実験ID: `fb707be72644490ab0757d4822f38101` / モデル: kimodo / パイプライン状態: succeeded
- 生成日時: 2026-10-14T19:19:53.988635+09:00（実験開始日時。動画編集日時とは区別）
- 元入力: 日本語で、研究用の音声対話アバターがどのように文章から声と動きを作るか、初心者向けに詳しく説明してください。音声認識、応答生成、動作生成、3Dモデルへの適用、遅延の課題について順番に、二十文以上、千二百文字程度で話してください。急がず、ゆっくり落ち着いて説明してください。
- 動作モデル入力: `Raise your right hand above your shoulder and wave repeatedly for 8 seconds.`
- 内容: 修正版。実Realtime日本語音声と8秒の新規生成動作を同一発話中に適用。応答途中で録画終了。
- 仕様: 81.150秒、790×538、h264、音声あり、3.40MiB
- 来歴: live_new_inference_recording / SHA-256 `2edb714b72848e02b96459b40518f817689fe2deb3067edc8d9190ff5a9a3618`

### [gesture_transition.mp4](videos/gesture_transition.mp4)

- 実験ID: `fb707be72644490ab0757d4822f38101` / モデル: kimodo / パイプライン状態: succeeded
- 生成日時: 2026-10-14T19:19:53.988635+09:00（実験開始日時。動画編集日時とは区別）
- 元入力: 日本語で、研究用の音声対話アバターがどのように文章から声と動きを作るか、初心者向けに詳しく説明してください。音声認識、応答生成、動作生成、3Dモデルへの適用、遅延の課題について順番に、二十文以上、千二百文字程度で話してください。急がず、ゆっくり落ち着いて説明してください。
- 動作モデル入力: `Raise your right hand above your shoulder and wave repeatedly for 8 seconds.`
- 内容: 修正版録画67秒から13秒の抜粋。デフォルト→生成→デフォルトの遷移。別の新規推論ではない。
- 仕様: 13.000秒、790×538、h264、音声あり、0.76MiB
- 来歴: live_new_inference_recording / SHA-256 `a9db0c3fcd766f6550f4921337d3ef3ea3e8c85f4a97b92cac84ab72cbc996a5`

### [vrm_demo.mp4](videos/vrm_demo.mp4)

- 実験ID: `fb707be72644490ab0757d4822f38101` / モデル: kimodo / パイプライン状態: succeeded
- 生成日時: 2026-10-14T19:19:53.988635+09:00（実験開始日時。動画編集日時とは区別）
- 元入力: 日本語で、研究用の音声対話アバターがどのように文章から声と動きを作るか、初心者向けに詳しく説明してください。音声認識、応答生成、動作生成、3Dモデルへの適用、遅延の課題について順番に、二十文以上、千二百文字程度で話してください。急がず、ゆっくり落ち着いて説明してください。
- 動作モデル入力: `Raise your right hand above your shoulder and wave repeatedly for 8 seconds.`
- 内容: 修正版の適用付近8秒の抜粋。描画された右腕の上げ下げを確認。
- 仕様: 8.000秒、790×538、h264、音声あり、0.53MiB
- 来歴: live_new_inference_excerpt / SHA-256 `ddbdefa19f578278e04e070dcf29d693e9fabe622341047d55c21399390d17ec`

## 圧縮・抜粋と元動画

ライブ元動画はVP8/Opus WebM。[Trial 1](videos/source/trial_1.webm)、[Trial 2](videos/source/trial_2.webm)、[Trial 3](videos/source/trial_3.webm)を保持。MP4はH.264 CRF20 / preset fast / yuv420p、音声AAC、faststartへ変換したため再圧縮による差がある。速度変更、フレーム補間、動作の合成は行っていない。ログは認証情報・ローカルパスを置換し、改行をLFへ統一、末尾空白を除去した。元ログはローカルに保持。詳細サイズ・SHA・コーデックは[動画manifest](logs/video_manifest.json)と[成果物manifest](logs/artifact_manifest.json)。

gesture_transitionはTrial 3録画の67秒から13秒、vrm_demoは69秒から8秒の抜粋。brief_gesture_excerptはTrial 2の58秒から12秒を指定し元動画終端まで。元のライブ録画は応答途中で終了する。失敗Trial 1は音声のみ成立、動作不採用と明示。

各ファイルはGitHubの100MiB制限未満で通常Gitを使用。LFSは使用しない。[GitHub大容量ファイル仕様](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)。GitHubでの埋め込み再生の可否はUIに依存するため、ファイルページのRaw/Downloadから取得できることを検証する。

## 作成していない成果物

遅延0/1/3/10秒の実API比較動画、Kebbi実機動画、自然さの評価票、GPU単独・CPU単独の時間分解、実請求額は未作成。既存workのreports/videos内にある過去動画は今回の新規推論回数に含めない。
