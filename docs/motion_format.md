# モーション形式と実験記録

## 共通 JSON

`motion-lab/v1` は世界座標の関節位置 `positions[T,J,3]`、fps、関節名、親 index を保存します。共通骨格へのリターゲットは行いません。ARDY Core27、Kimodo SOMA77、BVH 等の関節順序・階層を保持して同じ画面に表示します。

- 正規化先: **右手系、Y-up、metres**。1つの root、有限座標、循環しない親子関係を検証します。
- 元の軸・単位を必ず明示。Z-up → Y-up は `(x,z,-y)` の正規回転、cm/mm は明示された係数で変換します。推定しません。
- root の世界移動はそのまま保持。比較用の左右位置ずらしはビューアーだけで行います。
- JSON の source_coordinates、metadata、元ファイルを保持。取り込みは、このインスタンスでの推論成功と扱いません。
- 骨格表示と簡易アバターは同じ関節から描画。簡易アバターは骨間の円柱であり、SMPL-X/SOMA の人体メッシュやリターゲットではありません。

## NPZ

ARDY/Kimodo の `posed_joints`、local/global rotations、root、contacts は、**元 NPZ** に保存します。ARDY 公式 CLI は fps を出力します。NVIDIA オンライン Download の NPZ は fps がないため、同じセッションの **Model FPS** 値を取得し、生成時のフレーム数と照合します。

正規化の階層は公式 skeleton registry または、確認済み source の静的 `bone_order_names_with_parents` から取得します。未知の関節数を推定しません。一般 NPZ 取り込みには `positions` / `posed_joints`、`joint_names`、`parents`、`fps` が必要です。pickle 読み込みは禁止し、展開サイズも制限します。

SMPL-X の poses は axis-angle パラメーターです。関節位置として読み替えません。`scripts/export_smplx.py` はユーザーが正規に取得した body model で FK を行う別処理です。betas/expressions/poses/trans の shape、flat_hand_mean の条件を記録します。LoM の公式デモは default False、StreamTalk の GetSMPLXModel は True を指定するため、この条件をモデルごとに保持します。元出力と body model の手 pose convention が異なる場合は、変換設定を確認してから使ってください。資産なしの NPZ は変換を拒否し、元ファイルをクライアント側に残します。

## BVH

明記された channel 順で intrinsic Euler 回転を合成し、親から FK します。End Site を保持します。標準の3軸 rotationまたは position→rotation の6channelを対象とし、interleaved channel を無理に変換しません。上方向と単位はアップロード時に指定してください。

## 実験と評価

`outputs/<experiment-id>/experiment.json` に入力文、モデルへ渡した英訳、音声のコピー、task_type、seed、モデル／source commit、checkpoint、device、生成時間、fps/長さ、ファイル SHA-256 を保存します。元 NPZ、変換 JSON、MP4、redacted inference.log を個別に取得できます。

Kimodo オンラインの時間は「外部エンコーディングと通知通信を含む生成 wall time」です。実行コンテナー内の Git commit、重み SHA、VRAM peak は公開デモから観測できないので null。公式 Space の Git revision、GUI のモデル名、公開 runtime の GPU 情報を代わりに記録し、ローカル GPU 実測と区別します。

加速度 RMS は有限差分の運動学的診断です。自然さや意味的一致のスコアではありません。semantic_alignment / naturalness は null、足接地の評価器や信頼できる真値がないため足滑りスコアも作りません。違う入力で関節位置が変わったことは検査しましたが、指示への適合性・順序保持は主観評価が必要です。

## 音声同期

PCM WAV を検証し、HTML audio.currentTime を再生の master clock に使います。seek / pause / playbackRate を同じ時刻に反映します。FFmpeg 動画にも音声を mux できます。**音声と人工サンプルの同期検査は、音声条件付きのモデル生成成功を意味しません**。モデル生成は task_type=audio とモデル固有アダプターを通る必要があります。
