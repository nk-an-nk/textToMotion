# 実生成の検証動画

## VRMアバターの実行画面録画

保存済みの実生成モーションを実際のブラウザ内VRMレンダラーで再生した動画も追加しました。両方ともH.264、1280×720、約5秒、**現時点では無音**です。

| 動画 | モーションの出所 |
|---|---|
| [kimodo-vrm.mp4](kimodo-vrm.mp4) | 下記のKimodo右手を振る実生成結果をVRMへ適用 |
| [ardy-vrm-unconditional.mp4](ardy-vrm-unconditional.mp4) | 下記のARDY無条件CPU診断結果をVRMへ適用 |

アバターは `AvatarSample_VRM1.0` / pixiv VRoid Project。個人の非営利研究用の描画動画として出典を表示し、元VRMはGitへ追加していません。`allowRedistribution=false` はモデルファイルの再配布に関する設定です（[公式メタデータ仕様](https://github.com/vrm-c/vrm-specification/blob/master/specification/VRMC_vrm-1.0/meta.md)）。アバターとアプリのコードを同じライセンスとして扱いません。

元モーションのハッシュ、実描画フレーム数、動画の検査結果は [録画記録](vrm-recordings.json) にあります。30fpsのMP4はソフトウェア描画のフレーム反復を含み、RTX 5070の性能測定ではありません。

Realtime音声の生成・音声付き録画は [再現手順](../../docs/vrm_recording.md) と `scripts/generate_demo_speech.py`、`scripts/record_vrm_demo.cjs` を使用します。今回の実行環境にAPIキーがまだ届いていないため、AI音声付きの動画は未生成です。人工検証音による音声トラック・口の開閉の検証は、AI音声の成功とは区別します。

## スケルトンの実生成動画

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
