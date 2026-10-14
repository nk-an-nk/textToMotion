# 2026-10-14 実験報告

## 目的

研究室PCで文章条件付き動作生成を動かし、日本語音声対話と3Dアバターのジェスチャーを同時に出せるか確認する。

## 実施内容

Kimodo / ARDY / text-to-vrmaのローカルGPUセットアップと3秒の新規生成、Realtime gpt-realtime-2.1 / marin とVRMのライブ録画3回、Windowsの出力変換・一時ファイル処理・英語秒数指定の修正。推論パイプラインは合計9試行（成功5、失敗3、取消1）。追加の大量反復ベンチマークは実施していない。

## 実測結果

| 経路 | 骨格まで | MP4まで | フレーム数 / FPS |
|---|---:|---:|---|
| Kimodo | 51.453秒 | 54.547秒 | 90 / 30fps |
| ARDY | 81.828秒 | 83.735秒 | 60 / 20fps |
| text-to-vrma | 73.937秒 | 77.249秒 | 90 / 30fps |

動画: [Kimodo](videos/kimodo_demo.mp4)、[ARDY](videos/ardy_demo.mp4)、[text-to-vrma](videos/text_to_vrma_demo.mp4)。いずれも今回の新規テキスト条件付き推論、3秒、seed 0、音声入力なし。
グラフ: [生成時間](figures/model_latency.png)、[処理境界別時間](figures/inference_breakdown.png)。[全CSV](experiment_results.csv)には失敗も含む。

## 発話とジェスチャー

| 試行 | 描画 | 音声開始 | 骨格生成 | 動作適用（入力から） | 動作長 |
|---|---|---:|---:|---:|---:|
| 1 | software SwiftShader | 0.966秒 | 120.671秒 | 不採用 | 2秒 |
| 2 | RTX 5070 Direct3D11 | 0.695秒 | 62.531秒 | 64.185秒 | 2秒 |
| 3 | RTX 5070 Direct3D11 | 0.679秒 | 68.094秒 | 69.115秒 | 8秒 |

採用は2/3回（66.7%）。これは長い応答と比較条件Cの3試行についての状態・イベント上の値で、一般的な成功率や標準Dの性能ではない。Trial 2は2秒だけで見づらく、使用者からジェスチャーが見えないとの指摘を受けた。Trial 3で8秒の動作と実映像の右手上げ下げを確認した。意味的一致・自然さ・連続会話中の品質は未採点。

[修正版の日本語音声対話](videos/realtime_conversation.mp4)、[デフォルト→生成→待機の切り替え](videos/gesture_transition.mp4)、[VRMの動作部分](videos/vrm_demo.mp4)、[実フレーム比較](figures/gesture_comparison.png)、[時間軸](figures/speech_motion_timeline.png)。音声は実API出力、動作も同じ試行中の新規GPU推論。録画は応答途中で終了しており、全応答ではない。

## 失敗とボトルネック

1. Kimodo NPZにはFPSがないため変換失敗。公式config.yamlからFPSを読むよう修正。
2. text-to-vrmaはVRMA生成後にWindowsのcaptureファイルロックで2回失敗。プロセスツリー終了と削除再試行を追加。
3. SwiftShaderのCPU描画時は骨格約120.7秒。発話終了後の結果を取消。GPU描画の別試行では約62.5秒／68.1秒。ただし描画方式・動作長・出力トークン数が変わっており、因果効果を定量化した比較ではない。
4. 英語three secondsを読めず既定2秒になっていた。単語の数値指定を処理する修正と回帰テストを追加。
5. モデルCLI起動、CPU LLM2Vec、GPU推論、変換が含まれるバッチ待ち時間が大きい。GPUのみ、文章処理のみ、VRAM/RAMピークは未計測。標準Dの3秒期限に間に合う性能を実証していない。
6. 元ログにLLM2Vec/PEFT重み読み込みのMISSING / UNEXPECTED表示がある。生成出力は取得できたが、埋め込みへの影響とキー互換性を独立検証していない。文章に対する意味的成功の根拠として処理完了だけを使わない。

## 次回の研究課題

同じ入力・seed・期間で複数反復し、モデル読み込み、CPUエンコード、GPU推論を個別に計測する。常駐ワーカー・キャッシュを検討。短い実会話の期限内採用率、単語同期、足滑り、指示の意味的一致を評価する。遅延0/1/3/10秒の制御テストはあるが実API動画比較は未取得。[再現手順](runbook.md)、[品質レビュー](motion_quality_review.md)。Kebbiは未実装で、実機関節・速度・安全制約の検証が必要。

## 保存・公開

公開ブランチはnakano/1014。動画は通常Gitで保存し、[証拠索引](evidence_index.md)に実験ID・日時・入力・来歴・圧縮・権利を記載。再配布不可AvatarSampleのモデル本体は含めない。今回の動画は公開許諾を確認したVRM1_Constraint_Twist_Sampleの描画を使用。
