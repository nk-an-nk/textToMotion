# CodespacesでAndroid画面を操作する

Android SDK・エミュレータ・APK・FastAPIはすべてCodespaces内で実行します。
Macはブラウザ表示だけに使い、ローカルのAndroid SDKやエミュレータは不要です。

## 起動

1. Codespacesを開き、リポジトリ直下で初回だけ実行します。

   ```bash
   bash kebbi-conversation/scripts/cloud-android.sh setup
   ```

2. バックエンドを起動しておきます（別ターミナル）。

   ```bash
   cd kebbi-conversation/backend
   LLM_PROVIDER=mock .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log
   ```

3. APKをビルドし、リポジトリ直下からAndroidを起動します。

   ```bash
   (cd kebbi-conversation/android-app && ./gradlew :app:assembleMockDebug)
   bash kebbi-conversation/scripts/cloud-android.sh run
   ```

4. CodespacesのPortsで6080を開き、URL末尾を `/vnc.html?resize=scale` にします。「Connect」で画面へ接続します。
   **ポートのVisibilityはPrivateを維持してください。** 画面配信サーバーとVNCはクラウド内のループバックへ接続します。
5. CPUに関するエミュレータの通知が出たらOKで閉じます。起動完了後にモックAPKを自動インストールして表示します。
6. アプリのAPI URL初期値 `http://10.0.2.2:8000` は、同じCodespaces内のFastAPIへ接続します。

runを実行したターミナルを開いたままにしてください。Ctrl+CでAndroidと画面配信を停止します。
Codespacesを停止すると実行中のサービスも停止します。再開後はバックエンドとrunを実行します。
既にAndroidが起動している場合、runは二重起動せず終了します。既存端末は `adb emu kill` で停止できます。
初回ダウンロードには数GB、Android起動には数分かかります。環境によりさらに遅くなります。
この環境には `/dev/kvm` がないため、CPUのソフトウェアエミュレーションを使います。
ログは `/tmp/kebbi-cloud-android/` に出力します。

## 確認済みの結果（2026-10-23）

既存Codespaces、Android 9 / API 28 x86_64、モック版APK、モックLLMで確認しました。
エミュレータの再起動後、起動完了までのログは約135秒でした。

- ブラウザにAndroidアプリ画面を表示し、マウス・キーボードで操作。
- SDK(MockRobotAdapter)とバックエンド(mock)の接続済み表示。
- テキスト会話で応答「Hello! Nice to meet you!」、greet / mock_waveの選択。
- モックASR→FastAPI→モックTTS＋モーション→両完了→IDLE。
- 認識開始直後に停止し、stoppedイベントとIDLE復帰。
- Logcatでasr_complete、llm_response_received、tts_complete、motion_complete、turn_complete、metricsを確認。

最初の起動は途中で終了し、再起動で成功しました。Android起動直後にはSystem UIの応答待ち通知も出ました。
この環境は動作が遅く、速度測定やKebbiの性能評価には使いません。
この確認にKebbi実機、実音声の認識・発声、物理モーション、外部LLMの実接続は含まれません。
日本語設定、障害シミュレーション全種、長時間実行の画面テストは未実施です。
