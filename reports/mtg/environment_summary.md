# 実行環境

Windows、Python 3.12.10 x64、AMD Ryzen 7 5700X（8コア16スレッド）、物理RAM 34,269,339,648 bytes（約31.92GiB）、RTX 5070（12,227MiB）、NVIDIAドライバー610.88。PyTorch 2.9.0+cu128 / CUDA 12.8 / capability 12.0。動作モデルcuda、LLM2VecはCPU。

ライブTrial 1はSwiftShader CPU描画、Trial 2/3はANGLE NVIDIA Direct3D11。Realtimeはgpt-realtime-2.1、音声marin、入力はテキスト、日本語音声出力。Trial 1応答上限2048、Trial 2/3は4096 tokens。セッション上限180秒。予算3USDは事前許可枠であり実請求上限や実支払額の計測ではない。

公開時の基準はリモートwork e04c03c。モデルセットアップ測定時は6697dda、ライブ測定時は17b460bとローカルWindows修正。元モデルの固定リビジョン・ライブラリ一覧は[環境JSON](logs/environment.json)、[Kimodo GPU](logs/kimodo-gpu.json)、[ARDY GPU](logs/ardy-gpu.json)、各cuda-versions.txt、[元実験記録](logs/experiments/)参照。最新版と測定時の違いを隠さない。

APIキー、Hugging Faceトークン、重み、VRM本体、個人の音声・顔映像を含まない。ローカルユーザー名・絶対パスは置換した。生成した音声は合成音声で実在人物の録音ではない。
