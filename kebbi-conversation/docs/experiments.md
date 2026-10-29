# LLMによるジェスチャー選択の比較

画面上部の「実験条件」で次の3条件を切り替えます。切替時は会話履歴をリセットします。

| 条件 | LLMの出力 | 端末での処理 |
| --- | --- | --- |
| ① 動作IDを直接選択 | 返答文 + motion_id | SDKの全候補として送ったIDか再確認し、その動作を再生 |
| ② カテゴリ経由・従来7種 | 返答文 + gesture | 事前分類したカテゴリ内で、未使用/前回再生が古い動作をローカル選択 |
| ② カテゴリ経由・拡張15種 | 返答文 + gesture | 同じ対応表を拡張カテゴリ込みで使用 |

①も既存モーションを使います。新しい関節軌道の生成は含みません。
どの条件も音声認識・音声合成はKebbi標準、返答生成は同じバックエンド・同じLLMです。
返答文と動作選択は1回のLLM呼出で生成します。

## カテゴリ

元の7種は感情だけでなく会話の意図も含みます。
`none` は動作しない選択肢で、7種/15種には数えません。

| ラベル | 意味 | 対応する条件 |
| --- | --- | --- |
| greet | 挨拶 | 従来・拡張 |
| acknowledge | 相づち・聞いていることを伝える | 従来・拡張 |
| praise | 具体的に褒める | 従来・拡張 |
| surprise | 驚く | 従来・拡張 |
| explain | 説明する | 従来・拡張 |
| think | 考える | 従来・拡張 |
| question | 質問する | 従来・拡張 |
| joy | 穏やかな喜び | 拡張 |
| empathy | 共感・慰め | 拡張 |
| encourage | 励ます | 拡張 |
| apologize | 謝る | 拡張 |
| farewell | 別れの挨拶 | 拡張 |
| confused | 穏やかな困惑 | 拡張 |
| excited | わくわく・高揚 | 拡張 |
| calm | 落ち着かせる・安心させる | 拡張 |

## 0.3.0以降の動作一覧と事前分類

①は実機SDKが返す全動作（例: 000_A1_SHand_B2〜sadnessL_Sad）を候補にします。
手動のカテゴリ登録は不要で、会話ごとにIDと動作説明をLLMへ渡します。クールダウン中のIDは除きます。
APIの受入れ上限は4096候補です。Structured Outputsのenum上限を超える一覧ではenumだけを省略し、一覧全体をプロンプトへ渡してサーバー/端末で所属を検証します。一覧を先頭256件で切り捨てる旧仕様は廃止しました。

②は事前に作った分類表をバックエンドから取得して端末へ保存し、会話中にはカテゴリ名と意味だけをLLMへ渡します。
追加のLLM呼び出しは行わず、同じカテゴリの利用可能な候補から未使用または前回再生が最も古いIDを端末で選びます。
カテゴリ表の無効化は②に適用されます。①はSDK全一覧を使うため、カテゴリ割り当ての有効/無効とは独立です。

事前分類にはメーカーの説明やGIF/動画プレビューから作った説明を使います。
取得できた画像は時系列のフレームに展開して視覚入力とし、出典と分類根拠を残します。
画像がない動作は名称由来の推定と区別し、映像で確認したという扱いにはしません。
メーカーの公開プレビュー: [Nuwa Public Motion Preview](https://developer-docs.nuwarobotics.com/sdk/kebbi_motion_preview/showPic.html)。
ロボットの型番/SDK一覧との照合は必要です。

分類表は `MOTION_MAPPING_FILE` または起動スクリプトの `--motion-mapping` で指定します。
アプリはSDK一覧の取得後に一度読み込みます。「事前分類表を再取得」でも更新できます。
「モーション管理」では手動で分類や説明を修正できますが、再取得するとサーバーの分類表で置き換わります。

## API契約

従来のリクエストに次を追加できます。既定は `category/basic` です。

```json
{
  "session_id": "experiment-01",
  "text": "Hello Kebbi!",
  "language": "en",
  "selection_mode": "direct",
  "gesture_profile": "basic",
  "available_gestures": ["greet", "none"],
  "available_motions": [
    {"id": "666_BA_Nodhead", "description": "greet: gentle head nod to greet"}
  ]
}
```

`gesture_profile` は `basic` / `expanded`。`selection_mode` は `category` / `direct`。
直接選択の応答は `speech/gesture/language/timing` に任意の `motion_id` を追加します。
直接選択時の `gesture` は `none`。カテゴリ経由時には `motion_id` を返しません。
動作不要時の `motion_id` は省略します。Androidは省略とnullの両方を受け付けます。

`LLM_JSON_MODE=true` は現在、OpenAIの厳密なJSON Schema出力を有効にします。
候補数がenum制限内なら動作ID/カテゴリをenumとして渡し、上限を超えた場合もサーバーと端末で所属を再確認します。
候補外・無効化・SDK一覧から消えたID・クールダウン中のIDは再生せず、音声のみとします。
他のOpenAI互換サービスを使う際はStructured Outputsへの対応を確認してください。

## Mac上の一時バックエンドとUSB

Python環境に `backend/requirements.txt` を導入したうえで、リポジトリのルートから実行します。
Android SDK、Gradle、エミュレータはMacに不要です。

```sh
python kebbi-conversation/scripts/run-live-backend.py --key-file /absolute/path/to/key.txt
adb -s ROBOT_SERIAL reverse tcp:8000 tcp:8000
```

Kebbiの設定のバックエンドURLは `http://127.0.0.1:8000` にします。
USB経由のADB reverseがロボット側のlocalhostをMac側のlocalhostへ中継します。
キーはサーバープロセスにだけ渡し、ロボット・APK・Git・ログには保存しません。
既定モデルは `gpt-4.1-mini-2025-04-14`、`--model` で変更できます。
サーバーはlocalhostにだけ待受けます。USB再接続後はreverseの再設定が必要なことがあります。

終了時はサーバーでCtrl+C、`adb -s ROBOT_SERIAL reverse --remove tcp:8000`。
同じ環境を再利用しない場合、一時的に導入したPython依存パッケージも削除できます。

## 比較の手順と記録

- 同じ発話群を用意し、同じ言語・LLMモデル・動作集合・クールダウン条件で試します。
- まず従来7種と①を比較し、カテゴリ数の効果は7種と15種で別に比較します。
- 条件の順番を交代させ、各試行は新しい会話から始めます。クールダウン終了を待ってください。
- 会話履歴を引き継ぐ実験なら、条件ごとに同じ会話列を入力します。
- 返答文も共同生成されるため、同じ発話でも返答が変わり得ます。動作選択だけの因果効果を切り分ける設計ではありません。
- 適切さ、動作なし率、選択IDの分布、LLM所要時間、TTS/動作開始差を比較します。

端末のJSONイベントには条件、選択ラベル、要求ID、実行ID、候補数、フォールバック、所要時間を残します。
サーバーは条件・モデル・選択結果・時間を記録します。会話本文は既定では記録しません。
「JSONLをアプリ専用領域へ保存」を有効にすると、端末のJSONLを後で回収できます。
音声/動作の開始通知の差は実際の音・関節の物理的な同期精度とは異なります。

仕様：[OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat)。

## 返答速度の画面表示・保存

会話の完了後に「最新の返答速度」を表示します。「返答速度・履歴 / CSV保存」で条件別平均と直近200件を確認し、保存先を選んでCSVを書き出せます。

- LLM待ち: バックエンドへの要求から応答まで（通信を含む）。純粋なモデル推論時間ではありません。
- 返答開始: 音声入力はASR結果確定から、手動入力は送信から、TTS開始通知まで。
- ASR: 認識開始から結果確定まで。話している時間や認識エンジンの待ちも含みます。
- 操作→発声: 開始操作からTTS開始通知まで。音声入力ではASRも含みます。
- 全体: 開始操作からTTS・動作の両方が完了するまで。

速度履歴は会話本文・キーを含めず、JSONログの設定と独立してアプリ専用領域へ自動保存します。
成功・一部失敗・エラー・中断を残し、平均は成功した会話だけを入力経路別・条件別に計算します。
未計測は0ではなく空欄/—です。単独ASR/TTS/動作テストは平均に混ぜません。
`files/latency-history.json` をADBのrun-asから回収することもできます。
「速度履歴を消去」で初期化でき、モデルや分類表を変更して比較をやり直すときにも使えます。
