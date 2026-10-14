# Windows研究室PC向けセットアップの検証範囲

記録日（日本時間）: 2026-10-14。

## 対象と実装

利用者から申告された構成はWindows、Ryzen 7 5700X、RTX 5070 / VRAM 12GB、RAM 32GB、SSD 1TB。提供されたクラウド環境はLinux・CPUのみで、このWindows PCには接続していません。

PowerShellのセットアップ・起動・発話文比較スクリプト、設定JSON、ユーザー用仮想環境の導入処理を追加。CUDA 12.8版PyTorchを選び、テキストエンコーダーをCPUへ配置します。公式モデルソースは変更せず、Kimodoは公式CLI、ARDYは公式の既存エンコーダー注入APIを使います。text-to-vrmaはARDYエンジン・公式Node関数・VRMA builderを使い、同じ重みとPython環境を共有します。環境・モデルファイルを削除せずに再開できます。

## 実施した確認

- **Python: 71 passed / 0 failed / 0 skipped**。新規の35件は、モデル同意前の停止、cu128の指定と依存解決中の維持、変更された重みの検出、秘密値の伏せ字、CUDA失敗時のCPU／外部APIへの置換禁止、CPUテキスト配置、途中失敗で準備完了にしないこと、完了した環境工程の再利用、時間の合計と操作待ち除外、CSV、VRMAのSLERP/FK/root保持、未知形式・バッファ範囲・循環の拒否を確認。テストのdoubleは実モデル推論の成功に数えません。[XML](lab-setup-tests.xml)。
- **Chromium: 5 passed / 0 failed / 0 skipped**。既存のカメラ・再生・音声同期・取り込み・比較に加え、短文／中程度の発話文が元日本語と英訳のまま入力され、指定秒数が変わることと、時間CSVのダウンロードを実ブラウザで確認。[XML](browser-tests.xml)。音声と画面時刻は同一ブラウザフレーム内で比較し、別々の通信で採取した時刻差を同期ずれと扱わない。
- PowerShell 7.5.4の公式Parserで4つの`.ps1`を構文検査。Linux上で`-CheckOnly`の入口を実行し、データフォルダを作成しないことを確認。これはWindows PowerShell 5.1／Windows実機の実行確認とは別です。
- PyTorch公式cu128 indexで、`torch-2.9.0+cu128-cp312-cp312-win_amd64.whl` の配布を確認。GPUカーネルのRTX 5070上での動作確認は未実施。
- 固定した両公式ソースでWindows/MSVC用のCMake・setuptools分岐を確認。コンパイル成功とは扱わない。
- LLM2Vecの公開adapter設定が `meta-llama/Meta-Llama-3-8B-Instruct` を参照することを確認。Llamaアクセス承認や重みの新規取得はこのクラウドで行っていない。
- text-to-vrma固定SHA `53c50504d1dc5137d4414b27ae8afaff89a62943` の公式npm lockからruntime依存を導入し、公式Node関数をimport。人為的な変換fixtureを公式VRMA builderへ渡し、44関節・30frames・hips軌跡を検証、H.264 MP4 1秒へ変換。これは形式・レンダリング検査で、text-to-vrmaのテキスト推論成功ではありません。

## 研究室PCで実行する検査

セットアップはモデルごとの仮想環境でCUDA行列演算を実行し、Torch build・GPU名・compute capabilityを保存します。実際の英語プロンプトから生成した元NPZまたはVRMA・正規化JSON・MP4を確認し、成功したモデルだけruntimeの準備完了を記録します。発話文の一括比較では短文5件・中程度5件を、直接ARDY／Kimodo／text-to-vrma（ARDY）へ順番に渡します。

未確認事項: Windows実機のMSVCビルド／依存解決、RTX 5070でのテキスト条件付き推論、ピークRAM／VRAM、生成時間、研究室PCの管理者権限・winget利用可否・NVIDIAドライバー。これらを事前に成功済みとは表示しません。

操作手順: [Windows研究室PCのセットアップ](../docs/windows_lab.md)。
