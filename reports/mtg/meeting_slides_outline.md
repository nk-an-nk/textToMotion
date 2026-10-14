# MTG発表構成

1. 目的：文章→動作と日本語音声→VRMを研究室PCで成立させる。
2. 環境：RTX 5070 / RAM約32GiB、CPUテキスト処理・GPU動作生成。
3. 3経路の測定：[生成時間](figures/model_latency.png)。1試行ずつであることを明示。
4. ライブ録画：[修正版ジェスチャー](videos/gesture_transition.mp4)を先に視聴。
5. 同期：[時間軸](figures/speech_motion_timeline.png)。音声約0.7秒、動作約64〜69秒。
6. 失敗：FPS、Windowsファイルロック、遅い結果の取消、2秒に縮まった指定。
7. 品質：上げ下げは映像で確認、自然さ・意味一致は未評価。状態遷移だけでは品質を保証しない。
8. 次回：常駐化、反復測定、短い発話での期限内採用、Kebbiの関節仕様。

発表時は[meeting_report.md](meeting_report.md)と[evidence_index.md](evidence_index.md)を参照。スライドファイルを作成済みと称さず、本ファイルは構成案。
