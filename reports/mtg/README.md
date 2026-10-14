# 2026-10-14 MTG 成果物

Windows / RTX 5070 での3経路の新規動作生成と、日本語Realtime音声・VRM表示を実測した記録です。

- [MTG報告書](meeting_report.md) / [発表スライド構成](meeting_slides_outline.md)
- [実験計画と実施範囲](experiment_plan.md) / [全9試行のCSV](experiment_results.csv)
- [環境](environment_summary.md) / [モデル比較](model_benchmark.md) / [遅延分析](latency_analysis.md)
- [動作品質と確認限界](motion_quality_review.md) / [動画・証拠索引](evidence_index.md) / [再現手順](runbook.md)
- [Kimodo](videos/kimodo_demo.mp4) / [ARDY](videos/ardy_demo.mp4) / [text-to-vrma](videos/text_to_vrma_demo.mp4)
- **[修正版のジェスチャー切り替え](videos/gesture_transition.mp4)** / [日本語音声対話](videos/realtime_conversation.mp4)
- [生成時間グラフ](figures/model_latency.png) / [処理境界別時間](figures/inference_breakdown.png) / [発話と動作の時間軸](figures/speech_motion_timeline.png) / [録画の実フレーム比較](figures/gesture_comparison.png)

各モデルのsmoke比較は1試行ずつ、Realtimeは3試行です。遅延条件の制御テストを実APIの成功率と混同しません。短い動作・取消・失敗も記録しています。VRMモデル本体、APIキー、トークン、重みは含みません。
