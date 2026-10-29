# LLMによるジェスチャー選択の比較

画面上部の「実験条件」で次の3条件を切り替えます。切替時は会話履歴をリセットします。

| 条件 | LLMの出力 | 端末での処理 |
| --- | --- | --- |
| ① 動作IDを直接選択 | 返答文 + motion_id | 候補として送ったIDか再確認し、その動作を再生 |
| ② カテゴリ経由・従来7種 | 返答文 + gesture | 登録した対応表の候補を設定順に選択 |
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

## 実機の動作候補を準備

1. 「モーション管理・単独再生」で実機の動作一覧から選び、単独再生で動きを確認します。
2. カテゴリを選び、説明欄に実際の動きと使いたい場面を記入して保存します。
   例：`666_BA_Nodhead` / `acknowledge` / `Gentle head nod for acknowledging or agreeing.`
3. 「LLMに渡す動作候補を確認」で登録内容を確認します。

有効な割り当てのIDを重複排除した集合が、①の候補一覧になります。
LLMにはIDと説明（カテゴリ名＋説明欄）を渡します。②では利用可能なカテゴリと意味を渡します。
**SDKに存在するだけでは①の候補に入りません。登録・有効化・SDK一覧への存在・クールダウン経過を満たすことが必要です。**
直接選択候補は最大256件で、超過時は登録順（カテゴリ順を含む）の先頭256件を使います。
1カテゴリに複数IDを登録した場合、①はその中からもLLMが選べます。②は設定順の最初の利用可能なIDを選びます。

2026-10-29のSDK動作試験では `greet → 666_BA_Nodhead` の1動作を確認済みです。
**15カテゴリへの切替だけで動作が15種類に増えるわけではありません。** 各カテゴリに動作を割り当てて初めて選択肢に入ります。
未割り当てのカテゴリはLLMに提示せず、候補なしの場合は音声だけで応答します。

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
動作ID/カテゴリは各要求の候補だけをenumとして渡し、サーバーと端末でも再確認します。
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
