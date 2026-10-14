# モデルの実測

| 経路 | 骨格まで | MP4まで | フレーム数 / FPS |
|---|---:|---:|---|
| Kimodo | 51.453秒 | 54.547秒 | 90 / 30fps |
| ARDY | 81.828秒 | 83.735秒 | 60 / 20fps |
| text-to-vrma | 73.937秒 | 77.249秒 | 90 / 30fps |

Kimodo入力はRaise your right hand and wave for three seconds.、ARDY / text-to-vrmaはHello.（元入力はこんにちは）。全て3秒・seed 0。Kimodo77関節、ARDY27関節、VRMA由来44関節。text-to-vrmaはARDY Core8と同じ重みを使い、公式リターゲットと後処理を追加する経路。

骨格までの時間は入力受付からJSON保存まで、MP4までにはその後の描画を含む。official_command_secondsはモデル読み込み・CPU文章処理・GPU生成などを含み、GPU単体の推論秒数ではない。各1試行、モデル入力・CFG・後処理が異なるため有意な速度順位や平均値・分散は求めない。測定中のダウンロード時間は含まない。

[CSV](experiment_results.csv) / [時間グラフ](figures/model_latency.png) / [処理境界](figures/inference_breakdown.png)。
