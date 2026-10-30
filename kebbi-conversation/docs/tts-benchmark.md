# NUWA標準TTSの開始待ち時間をUSB経由で測る

`realDebug` のみの `TtsBenchmarkActivity` が固定した短・中・長の日本語を各10回読み上げます。
最初に各文章を1回ずつウォームアップし、合計33回。LLM・バックエンド・ASR・モーションは呼び出しません。
会話アプリの設定・会話履歴・動作の割り当ては維持します。実行中は通常の会話を停止します。

## 計測区間

Kebbi内の `SystemClock.elapsedRealtimeNanos()` で次の4点を記録します。

1. `NuwaRobotAPI.startTTS(text, JAPAN)` の直前
2. その呼出しが返った直後
3. `onSpeakState(..., START)` のコールバック入口（UIスレッドへ転送する前）
4. `onTTSComplete` のコールバック入口

主要指標は3−1です。SDK処理・サービスとの通信・通知の配送を含む開始待ち時間で、
音声合成エンジン内部だけの計算時間ではありません。スピーカーから実音声が出た瞬間の測定でもありません。
USB転送・PCの待機・JSONファイルへの記録はこの計時区間に含みません。
`startTTS` が返る前にSTARTが届く可能性があるため、2−1を3−1から差し引きません。

SDK通知にはリクエストIDがありません。完了後750msの間隔を設けて1件ずつ実行し、
開始通知なし・エラー・45秒タイムアウト時は後続を中止します。失敗を0msとして平均しません。
各文章1回のウォームアップを除いた30回の平均・中央値・p95・最小・最大を集計します。
同じ文章の反復なのでエンジン/サービスのキャッシュ効果を含みます。キャッシュ消去や端末再起動は行いません。
最初のウォームアップは別行で残りますが、コールド起動性能とは呼びません。

## 実行

APKはGitHub Actionsの `Build Kebbi real APK` でビルドします。MacへのAndroid SDKやエミュレータの導入は不要です。
USBデバッグが許可されたKebbiにreal debug APKを上書きインストールしてください。
診断ActivityはDUMP権限を持つADB shellから起動でき、release版には入りません。

```bash
python3 kebbi-conversation/scripts/tts_benchmark.py \
  --adb /path/to/platform-tools/adb --output /path/to/result
```

`run-id.txt` と `device-trials.jsonl`、完了後に `trials.csv`、`summary.json`、`report.md` を保存します。
起動後の反復処理とログの保存はKebbi自身で実行します。USB切断やMacのスリープ中も、
Kebbiの電源が入り診断画面が前面にある限り処理は続きます。画面のボタンで中止できます。
USB再接続後、既存の実行を再開せずに結果だけ回収できます。

```bash
python3 kebbi-conversation/scripts/tts_benchmark.py \
  --adb /path/to/platform-tools/adb --collect --run-id tts_YYYYMMDD_HHMMSS \
  --output /path/to/result
```

結果を取得した後はKebbiのボタンで戻るか、通常の会話Activityを起動します。
設定した標準の声と速度をそのまま用います。比較時は声・速度・端末・音声サービスの状態を揃えてください。

メーカーのAPI説明: [startTTS](https://developer-docs.nuwarobotics.com/sdk/javadoc/reference/com/nuwarobotics/service/agent/NuwaRobotAPI.html)、
[onSpeakState / onTTSComplete](https://developer-docs.nuwarobotics.com/sdk/javadoc/reference/com/nuwarobotics/service/agent/VoiceEventListener.html)。
