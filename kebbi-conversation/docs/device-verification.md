# Kebbi実機の確認記録

確認日: 2026-10-29。以下はモックではなくreal版アプリでの結果です。

## 環境

- 本体: NUWA AIR-H201
- Android: 9 / API 28（ADBで確認）
- 本体画面: KebbiOS 12.3、バージョン 1.2809.100WW.22(MR8)（写真で確認）
- メーカー指定AAR: NuwaSDK-2023-10-11_v2.1.0.08_513b45c_release.aar
- アプリID: jp.ojimalab.kebbi.conversation
- APKのSHA-256: `965b8790b85702b5ad542c6cd0ebacf83eb89c8e7b900bd3d3ad71b3585e7409`
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

## 未確認

- ASRの精度・繰り返しの安定性、日本語ASR・TTS
- モーション単独再生・マッピング保存・発話との同時実行
- 再接続の所要時間、停止直後の通知、通信断、長時間・連続会話
- 実機からバックエンドへの会話接続、外部LLMの実接続

SDK全機能の互換性・安定性を確認したという意味ではありません。
ASR試験は一部語句の認識を確認した段階で、入力句全体の正確な認識を保証するものではありません。
次は、実機一覧に存在するIDでモーション単独再生を確認します。
