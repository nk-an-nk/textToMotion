# 実生成の検証動画

実モデルが生成した関節位置を共通レンダラーでスケルトン表示した MP4 です。両方とも H.264、640×480、3秒、音声なしです。GitHub のファイル画面で再生できない場合は **Download raw file** で取得してください。

| 動画 | 入力・生成経路 | フレーム数 | 実験記録 |
|---|---|---|---|
| [kimodo-wave.mp4](kimodo-wave.mp4) | `Raise your right hand and wave for three seconds.`、seed 0、NVIDIA 公式オンラインデモ、SOMA77 | 90 / 30fps | [Kimodo](../kimodo_api_result.json) |
| [ardy-unconditional.mp4](ardy-unconditional.mp4) | テキスト・音声なし、seed 0、ARDY Core8 公開重み、CPU、Core27 | 60 / 20fps | [ARDY](../ardy_cpu_result.json) |

ARDY は無条件診断です。動作指示・会話ジェスチャー生成の成功とは数えません。意味的一致・自然さの採点は未実施です。モデルとライセンスの出典は [ライセンス記録](../licenses.md) を参照してください。

元の `outputs/<実験ID>/video.mp4` と同一内容で、SHA-256 は次の通りです。

```text
0ff06157012ee589e4ff988234c5ed0ee7d9e1d02990121b7ee3aa3fe17d2765  kimodo-wave.mp4
e55175a080a573b1ca534e1af0a9018ead18f6aa8e31d64cef2595961c12e414  ardy-unconditional.mp4
```
