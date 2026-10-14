# ReactMotion / MaAI の聞き手比較

2026-10-14に公式チェックポイントでCUDA推論を実行しました。[音声入力からの比較と再現手順](audio_input_comparison.md)、[動画・CSV](../reports/model-comparison/runpod-20261014/README.md)を参照してください。

| モデル | 入力 | 今回の出力 | 実装 |
|---|---|---|---|
| [ReactMotion](https://github.com/awakening-ai/ReactMotion) | 話者の発話文。会話デモは生徒の実際の音声認識結果 | VQ-VAE復号後の22関節、20fps | 公式T5生成＋VQ-VAE。無効トークン時の固定フォールバックは拒否 |
| [MaAI](https://github.com/MaAI-Kyoto/MaAI) | 実音声。JP nod_para、normal-ver2、ch1話者/ch2無音 | うなずきの確率・角度・速度・回数 | 学習済みの頭部パラメーターを保存し表示側で補間。胴体はアバターの基本姿勢 |

共通5文では同じ文字列・実音声を使用し、翻訳しません。ReactMotionは聞き手の全身反応で、話者の発話ジェスチャーとは役割が異なります。MaAIは学習済みの全身骨格を生成しません。共通5文の聞き手アバターには口の動きを付けません。

ReactMotionのソースは `73137065089d63479188c97ad8de2411d9be18a3`、生成重みは `awakening-ai/ReactMotion1.0` revision `f00075813798ff957a4768fbe393283e4c36560e`。公式Google DriveのVQ-VAE・mean/stdを使用しています。日本語には未知トークンがあるため、速度と意味の合致は別々に評価します。

MaAIのソースは `d4a156c69f75003aa99a296d210ed51fbbb45a7d`。公式のJP nod_para/normal-ver2選択とMimiを使用しています。元音声を16kHzへ変換して時系列順に処理し、各予測へ入力音声上の時刻と計算時間を記録します。英語混在文の品質は未評価です。

コードは双方MIT。ReactMotion1.0のモデルカードはMIT、VQ-VAE・データは別規約。MaAIは各モデルカード、MimiはCC-BY-4.0です。元VRMと重みはGitへ再配布しません。

追加モデルは `scripts/setup_comparison_models.py` で専用venvへ導入します。ReactMotionはテキストの全身骨格APIにも接続しました。MaAIは頭部制御の専用CLI・動画経路で検証済みで、全身骨格APIのアダプターは未実装です。
