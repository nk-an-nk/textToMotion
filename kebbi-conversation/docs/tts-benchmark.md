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

## AIR-H201での実測（2026-10-30）

アプリ0.7.2、SDK 2.1.0.08。33回すべて正常完了し、各文章1回のウォームアップを除外した30回を集計しました。
値は `startTTS` 直前〜START通知入口で、単位はmsです。

| 文章長 | 回数 | 平均 | 中央値 | p95 | 最小 | 最大 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 短文・12文字 | 10 | 11.810 | 10.440 | 18.907 | 7.060 | 22.035 |
| 中文・33文字 | 10 | 14.147 | 13.657 | 19.467 | 9.561 | 19.858 |
| 長文・73文字 | 10 | 11.968 | 11.273 | 20.108 | 7.542 | 22.855 |
| 全体 | 30 | 12.642 | 11.553 | 21.055 | 7.060 | 22.855 |

SDK呼出し自体の平均は0.395ms。START通知〜完了通知の平均は短文2.777秒、中文6.506秒、長文15.713秒です。
後者は読み上げを含む時間で、音声合成だけの計算時間ではありません。
単一端末・単一セッションの参考値です。声と速度は変更していませんが、NUWA側の実効設定値は未取得です。
過去の約242msは動作準備なども含む別の区間なので、今回の値との差をTTS高速化と解釈しないでください。
STARTと実音声開始が一致するかは未検証であり、音声合成全体がボトルネックかどうかはこの値だけでは断定できません。
[計測用APKのクラウド検証](https://github.com/nk-an-nk/textToMotion/actions/runs/41019054017)は成功しました。
