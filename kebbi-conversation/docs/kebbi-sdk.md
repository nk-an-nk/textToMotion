# NUWA SDKの境界と確認事項

## 確認した公式資料

- [日本語マニュアル](https://developer-docs.nuwarobotics.com/sdk/NUWA_Robot_SDK_jp.html)
- [NuwaRobotAPI 2.1.0.08](https://developer-docs.nuwarobotics.com/sdk/javadoc/reference/com/nuwarobotics/service/agent/NuwaRobotAPI.html)
- [CloudASRサンプル](https://github.com/nuwarobotics/NuwaSDKExample/blob/master/app/src/main/java/com/nuwarobotics/example/voice/CloudASRActivity.java)
- [公式サンプル](https://github.com/nuwarobotics/NuwaSDKExample)
- [モーションプレビュー](https://developer-docs.nuwarobotics.com/sdk/kebbi_motion_preview/showPic.html)
- [OpenAI互換の基準としたChat Completions仕様](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)

メーカー指定AARのクラス署名もjavapで確認し、このファイルを使ってreal flavorをコンパイルします。
版: `NuwaSDK-2023-10-11_v2.1.0.08_513b45c_release.aar`。
機種とファームウェアの互換性・音声エンジンの言語対応は実機接続時に確認してください。
別バージョンのAARを使ったコンパイル成功や実機動作は保証しません。

## 呼び出し

| 機能 | 使用API / 通知 |
| --- | --- |
| 初期化 | NuwaRobotAPI(Context, IClientId)、registerRobotEventListener |
| 接続完了 | onWikiServiceStart、onWikiServiceRecovery |
| 音声イベント登録 | 接続完了後のregisterVoiceEventListener |
| ASR | setListenParameter(RECOGNIZE, language, en-US / ja-JP)、startSpeech2Text(false) |
| 認識結果 | onSpeech2TextComplete、JSON内のresult文字列 |
| ASR停止 | stopListen |
| TTS | startTTS(text, ENGLISH / JAPAN)、onSpeakState(START)、onTTSComplete |
| モーション一覧 | requestMoitonList → 遅延したgetMotionList |
| 再生 | motionPlay(id, showMp4)、onStartOfMotionPlay、onCompleteOfMotionPlay |
| 停止/失敗 | motionStop(true)、onStopOfMotionPlay、onErrorOfMotionPlay |
| 解放 | release |

AIR-H201の正常再生ではonStopOfMotionPlayの直後にonCompleteOfMotionPlayが届くことを実機で確認しました。
停止通知だけをエラー扱いせず、完了通知・エラー通知・上限タイムアウトで再生結果を確定します。
利用者の明示的な停止は会話トークンの無効化で処理します。

`startSpeech2Text(false)` は公式CloudASRサンプルで「ウェイクアップ待ちなし」の開始に使われています。
`requestMoitonList` はSDKの綴りどおりです。一覧の準備完了通知が公開APIにないため、250ms間隔で最大8秒まで非同期に確認し、非空リストが2回一致した時点で表示します。
0件の場合は名前を推測しません。ロボット側のサービス・バージョンを確認して再取得します。

ASR結果はSDKのJSON形式を検証してresultを読みます。SDKヘルパーの例外出力から本文がログへ出ることを避けるため、アプリ側でパースしています。
SDK内部のログ出力そのものはアプリで制御できません。

## モーション設定

実機版は `config/gesture_mapping.json` が初期値です。ファイル名ではなく実機一覧に存在するIDだけを設定します。
モーション管理画面で一覧、単独再生、カテゴリ割り当て、保存、無効化、複数候補に対応しています。
設定はアプリ専用のSharedPreferencesに保存し、mockとrealはアプリIDが異なるため混ざりません。

```json
{"greet":[{"id":"実機一覧から選ぶID","durationMs":4000,"showMp4":false,"scene":"挨拶","cooldownMs":5000,"enabled":true}],"none":[]}
```

durationMsは参考メタデータで、完了時刻の代用にはしません。完了通知と45秒の上限タイムアウトを用います。
MP4を含むモーションは画面や音声も含む可能性があるため、実機プレビュー後に登録してください。

## 未確認の実機依存部分

AIR-H201でSDK接続・英語TTS・ASR・モーション単独再生を確認しています。[実機記録](device-verification.md)を参照してください。
その他の機種の検証は未実施です。
会話ごとのSDK再接続の所要時間、停止直後の通知順序、認識結果JSONの形式、TTS開始通知の発火は実機で確認してください。
SDKの通知には処理IDがないため、古いサービス通知が新しい接続へ配送される特殊なケースをアプリだけで完全に識別することはできません。
