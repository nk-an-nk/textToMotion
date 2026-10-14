# RunPod検証：上限1,000円

2026-10-14、RunPod APIの認証・残高を確認し、専用のSecure Cloud RTX4090 Podを作成しました。実際の契約単価は$0.89/時、コンテナ40GB＋一時ボリューム40GBです。既存Pod・ネットワークボリュームを変更せず、追加チャージは行っていません。

7モデルの音声入力からの計測と正面1080p動画を作成しました。[処理と結果](audio_input_comparison.md)、[動画・CSV・終了記録](../reports/model-comparison/runpod-20261014/README.md)を参照してください。

予算の換算は安全側の仮定で1ドル200円、ストレージと25%の余裕を含みます。最大3時間で約676円です。これは実勢為替や最終請求額ではありません。必要な作業が終わり次第Terminateし、削除をAPIで確認します。

`scripts/runpod_trial.py` は作成前に実単価・残高を照合し、今回作成したPodのIDと名前を検証してから終了します。別プロセスが期限を監視します。ローカル環境の置き換えで監視が止まるため、試行中の再Publishは行いません。設定JSONはRunPod側の強制課金上限ではありません。追加入金、自動チャージ、ネットワークボリュームは使用しません。

GPUは実際にRTX4090、PyTorch2.8、CUDA12.8で演算を確認しました。推論プロセスにCPU8スレッド・affinity8、PyTorch allocator上限12,227MiBを設定しました。研究室のRTX5070/Windowsの速度をそのまま再現した試験ではありません。詳細と制約は[再現手順](audio_input_comparison.md)に記載しています。

NVIDIA graphicsライブラリの確認とWebGL診断は実施しましたが、このPodはDRM/modesettingへのアクセスが許可されず、Chromiumの描画はSwiftShaderです。CUDA骨格生成とCPUによる動画書き出しの時間を分け、GPU描画成功として扱っていません。

SSHの外向き接続が拒否されたため、今回所有するPodの保護されたHTTPS/WSS Jupyter経路を `scripts/runpod_jupyter.py` で使用しました。APIキーとゲートの認証情報はプライベート設定に保持し、Git・動画・ブラウザへ渡しません。HF/OpenAIキーはPodへ転送せず、gated Llamaは元のクラウドでCPU処理し、実際の特徴量だけをCUDA動作モデルへ渡しました。

終了時は動画、骨格、計測、固定コミット、環境バージョン、重みのSHA256を回収します。取得済みの重みはプライベートキャッシュに保存し、Gitへ再配布しません。Stopだけではディスク課金が残るため、今回のPodをTerminateして削除を確認します。
