# Kebbi実機の確認記録

確認日: 2026-10-29。以下はモックではなくreal版アプリでの結果です。

## 環境

- 本体: NUWA AIR-H201
- Android: 9 / API 28（ADBで確認）
- 本体画面: KebbiOS 12.3、バージョン 1.2809.100WW.22(MR8)（写真で確認）
- メーカー指定AAR: NuwaSDK-2023-10-11_v2.1.0.08_513b45c_release.aar
- アプリID: jp.ojimalab.kebbi.conversation
- 初回APKのSHA-256: `965b8790b85702b5ad542c6cd0ebacf83eb89c8e7b900bd3d3ad71b3585e7409`
- [ビルド実行](https://github.com/nk-an-nk/textToMotion/actions/runs/40823139967)、ソース ed66c8a953870d05af072ad4623853aaf1e8a170

Codespacesは使用枠または予算上限により起動できず、GitHub Actionsの標準Ubuntuランナーでビルドしました。
AAR・Android SDK・Gradleの処理はクラウド内で実行し、MacはADBとAPKのみを使用しました。
Actionsの成果物は保持期間1日のため、期限後は手動実行で再ビルドしてください。

## 確認できたこと

| 項目 | 結果と根拠 |
| --- | --- |
| USB接続 | ADBでdeviceとして認識し、モデルとOSを取得 |
| real APK | インストールSuccess、MainActivityの前面起動を確認 |
| SDK接続 | 実機画面で「実機モード」「SDK: 接続済み」を確認。アプリのログにonServiceConnected |
| TTS単独（英語設定） | 手動入力hello kebbiから「TTSのみ」を実行。本体からの発声を利用者が確認 |
| TTS通知 | 同じ会話IDでtts_start_notification、tts_complete、turn_complete、metricsを確認 |
| ASR単独（英語設定） | 利用者が認識結果の表示を確認。実機画面に「認識した発話: hello」、ログにasr_complete・turn_complete・metrics |
| モーション一覧 | 実機の管理画面に動作IDを表示。先頭の000_A1_SHand_B2を画面で確認 |

TTSの記録は開始通知が要求開始から56ms、完了通知が1081ms、metricsのturn_msが1092msでした。
これはSDK通知とアプリ内時計による値で、音響的な発声開始・終了時刻の実測ではありません。

「テキストで会話」ではバックエンド未接続のためbackend_timeoutとなりました。
この経路にはllm_request_startが記録され、TTS要求に達していません。
SDKのTTS単独試験とは区別しています。

## モーション終了通知の修正と再確認

初版で666_BA_Nodheadを単独再生し、本体のうなずきを利用者が確認しました。
ただし実機はplay_stopの直後にmotion_completeを通知し、初版アプリは先行する停止通知をmotion_stoppedエラーとして処理していました。
この順序は[メーカー資料](https://developer-docs.nuwarobotics.com/sdk/NUWA_Robot_SDK_en.html)にも記載されています。

RealRobotAdapterを修正し、停止通知は記録だけにして、完了通知またはエラー通知を待ちます。
利用者の停止操作は従来どおり会話トークンを無効化し、完了が届かない場合の45秒期限も維持します。

- 修正ソース: 1e11265a10aa4daaf2bf662468c75b55b9b6ccbf
- [修正版ビルド](https://github.com/nk-an-nk/textToMotion/actions/runs/40824661484): 成功
- 修正版APK SHA-256: `789c75241dfe5d7cd6046d32dcc0f31027527d2275938ecb03d1b252c20bfb7c`
- 修正版を実機へ入れ、再びうなずいたことを利用者が確認
- 同一会話IDでmotion_request → motion_start_notification → motion_stop_notification → motion_complete → turn_complete → metricsを確認
- この再試験のmotion_errorは0件。metricsのturn_msは1433ms

GitHub Actionsの実行ごとにデバッグ署名が変わり、通常の上書きインストールはUPDATE_INCOMPATIBLEとなりました。
この試験ではアプリ専用の設定・ファイルをMacへ退避し、入れ替え後に復元しました。既に許可されていたマイク権限も復元しています。

## マッピング保存とTTS＋モーション同時実行

修正版でgreetに666_BA_Nodheadを割り当てて保存し、アプリ専用設定にIDが保持されたことを確認しました。
Hello Kebbiを手動入力して「TTS＋ジェスチャー」を実行し、発声しながらうなずいたことを利用者が確認しました。
同じ会話IDでTTS要求・モーション要求・両開始通知・両完了通知・turn_complete・metricsが記録され、この試験にはerrorおよびmotion_errorがありません。

- tts_request: 26ms、motion_request: 29ms（要求差3ms）
- tts_start_notification: 45ms、motion_start_notification: 115ms（SDK開始通知差70ms）
- tts_complete: 1037ms、motion_complete: 1376ms
- turn_ms: 1382ms

数値はアプリ内時計とSDK通知の指標です。音響・映像・モーターの外部計測による同期精度ではありません。
この試験のgreet→うなずきはテスト用の割り当てで、他カテゴリは未割り当てです。

## 初回SDK試験の未確認範囲

- ASRの精度・繰り返しの安定性、日本語ASR・TTS
- 再起動後のマッピング保持、他の動作・カテゴリ、物理的な同期精度
- 再接続の所要時間、停止直後の通知、通信断、長時間・連続会話
- 音声入力ASRから外部LLMへ接続する一連の会話（下記の0.2.0追加試験で確認）

SDK全機能の互換性・安定性を確認したという意味ではありません。
ASR試験は一部語句の認識を確認した段階で、入力句全体の正確な認識を保証するものではありません。
SDK基本機能の単独試験とTTS＋既存モーションの同時実行まで確認済みです。
バックエンドを経由した実機会話と外部LLM接続は、これらのSDK試験と区別して下記に記録します。

## LLM比較用アプリ0.2.0の追加確認

[ビルド](https://github.com/nk-an-nk/textToMotion/actions/runs/40826924864)、ソース `f7d9cf342e045f92be59e4e83f195c9e79e425f9`。
実機用APK SHA-256は `9a1263825611eacdf1a52bab95887e749259efbc668910e92a2f54762f138b1a`。
既存のマッピング・設定を退避して復元し、マイクの許可も復元しました。
実機画面でSDK接続済み、バックエンド接続済み(openai)、IDLEを確認しました。
今回のバックエンドは利用者が承諾したMac上の一時プロセスで、USB経由・localhost待受けです。
キーはMacのサーバープロセスにのみ読み込み、ロボットへは保存していません。
モデルは `gpt-4.1-mini-2025-04-14` です。

### カテゴリ経由・従来7種

Hello Kebbi!を手動入力して「テキストで会話」を実行し、LLMの返答を発声してうなずいたことを利用者が確認しました。
端末の同一ターンにmotion_complete、tts_complete、turn_completeと以下のmetricsを確認しました。

- 選択ラベル: greet、実行ID: 666_BA_Nodhead
- llm_ms: 950、turn_ms: 4362
- TTS要求: 980ms、動作要求: 982ms（要求差2ms）
- TTS開始通知: 1001ms、動作開始通知: 1085ms（開始通知差84ms）

拡張カテゴリの多様な物理動作、長時間の連続会話は未確認です。
現在の実機登録はgreet→666_BA_Nodheadの1件のため、動作の多様性を比較するには登録を増やす必要があります。

### 動作ID直接選択・手動入力

同じHello Kebbi!の入力で、LLMの返答の発声とうなずきを利用者が確認しました。
端末ログで `requested_motion_id=666_BA_Nodhead`、候補数1、`fallback=false`、同じIDへのmotion_requestを確認しました。
同一ターンで両開始・完了通知とturn_completeを確認し、error/motion_errorはありません。

- llm_ms: 1470、turn_ms: 3845
- TTS要求: 1479ms、動作要求: 1481ms（要求差2ms）
- TTS開始通知: 1491ms、動作開始通知: 1570ms（開始通知差79ms）

### 動作ID直接選択・音声入力からの一連の接続

「音声認識 → 会話」から英語で話しかけ、認識後のLLM返答の発声とうなずきを利用者が確認しました。
同一ターンでasr_start/complete → llm_request_start/response_received → llm_selection → TTS/動作要求・開始・完了 → turn_completeを確認しました。
LLMが選んだIDは666_BA_Nodhead、候補数1、fallback=false、error/motion_errorはありません。

- asr_ms: 5960、llm_ms: 1640、turn_ms: 11677
- TTS要求: 7626ms、動作要求: 7627ms（要求差1ms）
- TTS開始通知: 7642ms、動作開始通知: 7735ms（開始通知差93ms）

直前の別の音声入力ターンでは、候補1件に対してLLMがmotion_id=nullを選び、音声のみで正常完了しました（asr_ms=3903、llm_ms=1242、turn_ms=8467）。
動作不要を選べる仕様のため、すべての返答で動作が起きるわけではありません。
これらは少数の接続・経路確認です。分類の適切さ、認識精度、多様な動作の選択、長時間安定性の評価とは区別してください。

## 全2,097動作・事前分類・日本語・速度記録（0.4.0）

ソース `40a89dc215afcb65e7872853aa68dcb5e06e4eef` の [ビルド](https://github.com/nk-an-nk/textToMotion/actions/runs/40831346475) と自動テストは成功しました。
APK SHA-256: `fa08e37590d0128f5c2f2b0e04aa4ca2e16a4052d842f932dc4a0643fdda50b3`。
本体への導入時は設定・アプリ専用ファイル・マイク許可を保持しました。

実機のSDK一覧は2,097件で、先頭000_A1_SHand_B2、末尾sadnessL_Sadを確認しました。
①は全一覧から、②は事前分類した25カテゴリまたは従来7カテゴリへの射影から選びます。
実機設定に全2,097 IDの分類表が保存され、画面に「事前分類表: 適用済み」「GIF 293件・その他は名称等の暫定分類」を確認しました。
これは2,097動作すべてを実際に再生したという意味ではありません。

メイン画面で日本語・カテゴリ経由25種を選択して音声会話を実行し、日本語の認識、LLMの返答の発声、身体動作、速度の数値表示を利用者が確認しました。
実機画面の言語=日本語、認識した発話=こんにちはを確認しました。
端末専用のlatency-history.jsonにlanguage=ja、input=conversation_voice、mode=category、profile=expanded、status=completedを確認しました。

| 記録 | 実行ID | ASR | LLM待ち | 認識確定→TTS開始通知 | 操作→TTS開始通知 | 全体 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 666_BA_RHandL03 | 4.803秒 | 1.619秒 | 1.656秒 | 6.484秒 | 10.149秒 |
| 2 | 666_BA_RHandR01 | 3.383秒 | 1.164秒 | 1.192秒 | 4.598秒 | 7.477秒 |

両方ともエラーコードなしでcompletedです。うなずき以外のIDを選び、前回再生した動作以外へ進んだことも記録で確認できました。
速度はSDK通知を受信したアプリ内時計による値で、音響/機械的な開始時刻の外部計測ではありません。
速度CSVの生成・エスケープ・欠測値と保存JSON・言語別集計はコアテストで検証済みです。端末の保存先ピッカーによるCSV書出し操作自体は未実施です。

APIの比較試験と分類資料の根拠は [全動作選択の速度比較](selection-benchmark.md) を参照してください。

## 一文一動作と継続会話（0.5〜0.6）

0.5.0（ソースb98a6984b741e696775c5f86f7b75f91965c3a0c）で、日本語の返答を文ごとに分けて動作し、ボタンを押し直さずに会話が継続したことを利用者が確認しました。
「好きな動物はパンダ」と話した後の質問でも、その内容を覚えた返答を確認しました。
ただし、TTS開始から動作を要求する方式では動作開始が132〜2,382ms遅れる例がありました。

0.5.1（ソース3513d9498da850b769fc9099dc2eea109e1a309f）では動作開始を先に待ち、開始通知の差は−17〜−9msになりました。
一方、文間は1,907〜2,196msとなり、利用者から声の遅さ・文の間の長さを指摘されました。

### 速度優先版0.6.0

- ソース: d367ea63f4391cac4b0cd4d93187e5b015bd292e
- [クラウドのテスト・ビルド](https://github.com/nk-an-nk/textToMotion/actions/runs/40836705036): 成功
- APK SHA-256: `fff98d0c6544e7beafbb2b24a32783cfee76005f04662b90899c776dc5142c64`
- APIモデル: gpt-4.1-mini-2025-04-14のまま。この実機試験時点では原則1〜2文を推奨。その後、この推奨だけを[試験的に解除](response-length-trial.md)。
- SDKのmotionPrepareで読み込み、準備済みmotionPlay()とTTSを続けて要求。
- 文ごとの接続更新を省き、音声通知の世代番号で古い文の通知を除外。

日本語・カテゴリ25種の実機試験で、利用者が「文の間が短くなり、自然になった」と確認しました。
同じ会話セッションの2応答で、各2文・各2動作がエラーなしで完了しました。

| 応答 | 文1の動作 | 文2の動作 | 文1の開始通知差 | 文2の開始通知差 | 文1終了→文2の発声開始通知 |
| --- | --- | --- | --- | --- | --- |
| 1 | 666_EM_Happy01 | 666_RE_Ask | −10ms | −7ms | 119ms |
| 2 | 666_BA_Nodhead | 666_RE_Request | −8ms | 0ms | 189ms |

開始通知差は「動作 − TTS」で、負値は動作側の通知が先です。
動作の準備完了ログを4件確認しました。速度履歴ファイルにも、各返答のsentenceCount=2と2つのmotionIdsが保存されていました。
その後の認識中に利用者が停止し、キャンセルとして記録されています。

少数回のSDK通知・アプリ内時計による確認で、音響・モーターの開始時刻の外部計測ではありません。
全動作・長文・長時間・通信障害時の性能を保証する結果でもありません。
詳細な出力契約と停止条件は [文単位出力と継続会話](sentence-conversation.md) を参照してください。


### 返答生成モデルの切替版0.7.1

- ソース: 5ccecf7ed83c45183491e9099712d7628d238e05
- [クラウドのテスト・ビルド](https://github.com/nk-an-nk/textToMotion/actions/runs/40845594938): 成功
- APK SHA-256: `acaa77d3e78b606c52f145e08b0aa7f8b5f1d4c3ba29b8a9898fb9ef2c76e619`
- 返答生成: 画面から4.1 mini、4.1、5.4 mini、5.4、6 Luna、6.1 Solを選択。5・6系は推論low。
- 動作選択: 全条件でバックエンドの固定モデル（現在4.1 mini）。文章の書き換えは行わない。

各モデルの文章生成と固定miniによる文ごとの動作カテゴリ選択を実APIで確認しました。全2,097候補を渡した直接選択も、4.1の文章生成→固定miniのID選択で正常応答しました。試験は合成の日本語学習・買い物入力であり、モデル品質の優劣を判定する反復比較ではありません。

実機へ0.7.1を導入し、返答生成モデル欄、SDK接続済み、バックエンド接続済み、事前分類表の適用済み（SDK 2,097動作）を画面で確認しました。CIのテスト署名が変わるため、元のAPKとアプリ専用領域を退避して入れ替え、設定・対応表・速度履歴を元のバイト列と照合して復元しました。マイク権限とUSBポート転送も再設定しています。

直前の0.7.0では、4.1による返答生成・miniによる動作選択で、音声入力の3〜4文の会話がcompletedとなった速度履歴を確認しています。0.7.1で追加した5・6系について、物理的な発声・動作の利用者確認は別途行います。CSV保存先を選ぶAndroid画面の操作確認も未実施です。詳しい操作と計測条件は[モデル比較](model-comparison.md)を参照してください。
