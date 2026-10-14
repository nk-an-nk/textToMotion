# 実生成の検証動画

## 日本語音声付きVRM動画

Realtime APIで実際に生成した「こんにちは。よろしくお願いします。」の日本語音声を追加し、音声時計に合わせたモーション再生と口の開閉を録画しました。両方ともH.264＋AAC、960×640、約5秒です。

| 動画 | モーションの出所 | 録画記録 |
|---|---|---|
| [kimodo-vrm-voice.mp4](kimodo-vrm-voice.mp4) | 保存済みKimodo：右手を挙げて手を振る | [JSON](kimodo-vrm-voice.json) |
| [ardy-vrm-unconditional-voice.mp4](ardy-vrm-unconditional-voice.mp4) | 保存済みARDY：テキスト・音声なしの無条件CPU診断 | [JSON](ardy-vrm-unconditional-voice.json) |

音声はOpenAI Realtime GA WebSocket、`gpt-realtime-2.1`、`marin`で生成した合成音声です。音声の長さは3.00秒、生成処理の所要時間は5.20秒、使用量は137 tokens（input 58 / output 79）。1回生成した同じ音声を2本で使用しています。[元WAV](../audio/realtime-hello.wav) と [API生成記録](../audio/realtime-hello.json) も保存しています。

動画は保存済みモーションと新規生成音声をブラウザで再生した録画です。今回の新規Text-to-Motion推論やライブWebRTC会話ではありません。ARDYの動作は発話文で条件付けしていません。再現方法は [音声付き録画手順](../../docs/vrm_recording.md) を参照してください。

## VRMアバターの実行画面録画

以前録画した無音版も保持しています。両方ともH.264、1280×720、約5秒です。

| 動画 | モーションの出所 |
|---|---|
| [kimodo-vrm.mp4](kimodo-vrm.mp4) | 下記のKimodo右手を振る実生成結果をVRMへ適用 |
| [ardy-vrm-unconditional.mp4](ardy-vrm-unconditional.mp4) | 下記のARDY無条件CPU診断結果をVRMへ適用 |

アバターは `AvatarSample_VRM1.0` / pixiv VRoid Project。個人の非営利研究用の描画動画として出典を表示し、元VRMはGitへ追加していません。`allowRedistribution=false` はモデルファイルの再配布に関する設定です（[公式メタデータ仕様](https://github.com/vrm-c/vrm-specification/blob/master/specification/VRMC_vrm-1.0/meta.md)）。アバターとアプリのコードを同じライセンスとして扱いません。

元モーションのハッシュ、実描画フレーム数、動画の検査結果は [録画記録](vrm-recordings.json) にあります。30fpsのMP4はソフトウェア描画のフレーム反復を含み、RTX 5070の性能測定ではありません。

Realtime音声の生成・音声付き録画は [再現手順](../../docs/vrm_recording.md) と `scripts/generate_demo_speech.py`、`scripts/record_vrm_demo.cjs` を使用します。人工検証音による事前の録画検証と、上記の実API音声による録画を区別して記録しています。

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
