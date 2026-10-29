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

## 未確認

- ASRの精度・繰り返しの安定性、日本語ASR・TTS
- 再起動後のマッピング保持、他の動作・カテゴリ、物理的な同期精度
- 再接続の所要時間、停止直後の通知、通信断、長時間・連続会話
- 実機からバックエンドへの会話接続、外部LLMの実接続

SDK全機能の互換性・安定性を確認したという意味ではありません。
ASR試験は一部語句の認識を確認した段階で、入力句全体の正確な認識を保証するものではありません。
SDK基本機能の単独試験とTTS＋既存モーションの同時実行まで確認済みです。
バックエンドを経由した実機会話と外部LLM接続は、これらのSDK試験と別に確認します。
