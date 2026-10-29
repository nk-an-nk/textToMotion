# 検証手順

## 自動テスト

リポジトリ直下で `bash kebbi-conversation/scripts/verify.sh` を実行します。
バックエンドの仮想環境が別の場所の場合は `KEBBI_PYTHON=/path/to/python` で指定できます。
実機版もビルドする場合は `KEBBI_VERIFY_REAL=true` を追加してください。

- Python: モック/外部互換APIの応答検証、未知カテゴリ、不正入力、上流エラー/タイムアウト、履歴・TTL・容量・直列化、任意の共有トークン、ログの本文・キーレダクション
- Java: 状態遷移、モーション存在確認、複数候補・有効化・クールダウン、TTS先/モーション先、重複・遅延・停止後の通知、ASR/LLM/再生タイムアウト、SDK切断、TTS失敗、動作失敗時のTTS継続
- HTTP結合: 実際のFastAPIを一時ポートで起動し、JavaのHTTPクライアント→モックLLM→MockRobotAdapter→両完了→IDLEとmetricsまで、カテゴリ7種/15種/ID直接選択の3条件で確認
- APK: mockDebugと、指定時にはrealDebugのビルド

単独で `./gradlew :core:test` だけを実行した場合、HTTP結合テストは接続先がないためskipします。
`verify.sh` はテストサーバーの起動・待機・終了まで実施し、HTTP結合テストを有効にします。
モックの合成IDは `mock_wave`、`mock_nod`、`mock_praise`。実機モーションとは無関係です。

## Android画面でのモック確認

1. backendをモックモードで起動し、mockDebugをエミュレータへインストール。
2. 設定でAPI URLを指定。「接続を確認」でSDK接続済み、バックエンド接続済み(mock)を確認。
3. `Hello, Kebbi!` を入力し「テキストで会話」。greet / mock_wave / SPEAKINGを経てIDLEに戻ること。
4. `I got 100 points!` でpraise / mock_praiseを確認。同じ動作をすぐ繰り返すとクールダウンで動作なしになること。
5. 日本語に切り替えて `こんにちは`、TTS単独、ASR単独、同時実行、モーション単独を確認。
6. 設定でtts_error・motion_error・各timeoutを選択。停止や期限到達後にIDLEへ復帰すること。
7. JSONイベント画面で同じconversation_idの要求・開始通知・完了・metricsを確認。
8. モーション無効化、未知/未割当カテゴリでも発話だけ継続すること。
9. 本文・端末ファイル保存が初期状態で無効であること。画面を離れると処理とセッションを終了すること。

アプリ画面のエミュレータ操作は、コアのHTTP結合テストとは別の確認です。
2026-10-23にCodespaces上のAndroid画面をブラウザから操作し、モック会話・ASR経路・停止・IDLE復帰を確認しました。
[クラウド画面の起動手順と確認範囲](cloud-android.md)を参照してください。全チェック項目の実施を意味しません。

## 実機確認チェックリスト

| 確認 | 期待結果 |
| --- | --- |
| 型番、OS、ファームウェア、SDK版 | 機種・言語エンジンと合わせて記録 |
| SDK接続/再接続 | 接続完了後だけ開始ボタンが有効 |
| ASR日本語/英語 | ボタンで認識開始、resultを表示し、発話前に停止 |
| TTS日本語/英語 | 指定言語で発話し、START/完了通知を記録 |
| モーション一覧 | 実機にあるIDだけを表示、空の場合は登録しない |
| 単独再生・割り当て・無効化 | 有効な実機IDのみ実行し、再起動後も設定を保持 |
| 同時実行 | 要求差・実開始通知差を計測し、両方が完了してIDLE |
| 停止・SDK切断・ネットワーク断 | 再生停止、古い通知を無視、再接続後に再開可能 |
| 連続100会話・30分実行 | 発話/動作の重複なし、メモリ・温度・通知順序を記録 |

2026-10-29にAIR-H201でUSB接続、real版の導入、SDK初回接続、英語TTSの発声と完了通知、ASRの結果表示、実機モーション一覧、666_BA_Nodheadの単独再生と正常完了、割り当て保存、TTSとの同時実行を確認しました。
[実機確認記録と未確認の範囲](device-verification.md)を参照してください。
表の全チェック項目を実施したという意味ではなく、発声と機械動作の実際の時刻差は未検証です。
常時認識・ウェイクワード・自動再認識、ストア公開、複数サーバープロセスの共有履歴は対象外です。

## ログを読む

端末は `adb logcat -s KebbiTrace` でJSONイベントを確認できます。
保存設定を明示的に有効にした場合は、debug版から `adb shell run-as jp.ojimalab.kebbi.conversation cat files/events.jsonl` で取得できます。
mock版はアプリID末尾に `.mock` を追加します。本文なしが初期設定で、ファイルが約5MBを超えると次の書き込みで置き換えます。
metricsの *_request_* はAPI要求時刻の指標、*_start_notificationはSDKが知らせた開始時刻です。

## LLM選択方式の追加検証（2026-10-29）

ソース `f7d9cf342e045f92be59e4e83f195c9e79e425f9`、アプリ0.2.0。
[GitHub Actions](https://github.com/nk-an-nk/textToMotion/actions/runs/40826924864)でPython34件、Javaコア・3条件のHTTP結合、mock/real APKビルドが成功しました。
実機用APK SHA-256は `9a1263825611eacdf1a52bab95887e749259efbc668910e92a2f54762f138b1a`。

Macでは利用者の承諾のもと軽量FastAPIバックエンドだけをlocalhostで一時実行し、ADB reverseでKebbiと接続しました。
Android SDK・Gradle・エミュレータはMacに導入していません。
OpenAIの `gpt-4.1-mini-2025-04-14` へ実接続し、合成した英語の挨拶/悲しみの2入力×3条件、計6要求がすべてHTTP200・有効JSONで完了しました。
バックエンドへのHTTP往復は1001〜1514msでした。小標本の接続試験であり、性能や再現性の評価ではありません。

| 入力例 | カテゴリ7種 | カテゴリ15種 | 直接選択（この接続試験の候補は1件） |
| --- | --- | --- | --- |
| Hello Kebbi! | greet | greet | 666_BA_Nodhead |
| 友達が遊んでくれず悲しい（英語） | acknowledge | empathy | 666_BA_Nodhead |

この6要求はバックエンド単体の接続試験です。実機の分類割り当て数とは別にテスト用カテゴリを提示しており、全カテゴリのロボット動作確認を意味しません。
APIキーはリポジトリの追跡ファイルとAPK内の全ファイルに含まれないことを検査しました。
実機での確認は [実機記録](device-verification.md)、条件と候補の準備は [比較実験手順](experiments.md) を参照してください。

## 全動作・速度履歴・日本語UI（0.4.0）

ソース `40a89dc215afcb65e7872853aa68dcb5e06e4eef` の [クラウド検証](https://github.com/nk-an-nk/textToMotion/actions/runs/40831346475) で、バックエンド・Javaコア・3条件のHTTP連携テスト、mock/real APKビルドが成功しました。
全SDK一覧を手動登録なしで提示すること、候補外IDの拒否、分類表の読込、粗い/詳細カテゴリの分離、言語設定、記録の上限・保存JSON・CSV・失敗/中断・言語別集計を確認しています。
APK SHA-256: `fa08e37590d0128f5c2f2b0e04aa4ca2e16a4052d842f932dc4a0643fdda50b3`。

実機から2,097件のSDK IDを取得し、事前分類を実機設定へ保存しました。GIFで説明を作れた293件と、名称由来の1,804件を区別しています。
英語・日本語それぞれ各条件8要求のAPI速度比較は [計測結果](selection-benchmark.md) を参照してください。合成した発話によるバックエンド比較で、全2,097動作の物理試験ではありません。

日本語でのASR→LLM→TTS＋手の動作、速度表示と端末の速度履歴ファイルまで実機で確認しました。[実機記録](device-verification.md)を参照してください。
