# 再現・閲覧手順

## MTGで確認

1. READMEから修正版gesture_transition.mp4を再生。前半の待機と右腕の上げ下げを見る。
2. experiment_results.csvの成功・失敗・取消と実験IDを確認。
3. モデル時間グラフと発話/動作の時間軸を比較。
4. 自然さ・意味的一致を処理成功と混同しない。

## 環境の再現

Python 3.12 x64、RTX 5070向けドライバー、Git、Node/npm、FFmpeg、VS2022 C++。このリポジトリのsetup-windows.ps1とconfigs/lab-windows.jsonを使用。モデル規約同意とLlamaアクセス承認が必要。ローカル認証ファイルは.gitignore対象、キーをGitへ追加しない。

```powershell
.\setup-windows.ps1 -InstallPrerequisites -AcceptModelLicense
.\setup-conversation.ps1
npx playwright install chromium
```

## 実験の再実行（有料Realtime API）

API利用の明示的許可を持つ利用者が実行する。scripts/run_realtime_experiment_server.pyはOPENAI_API_KEY環境変数を優先し、任意でローカルconfig/reaitimeapi.txt等を読む。キーの値は保存しない。セッション180秒、接続3回、事前許可3USDは実請求額の厳密な上限ではない。

```powershell
# 環境変数OPENAI_API_KEYを安全に設定してから、端末1で起動

.\.venv\Scripts\python.exe scripts/run_realtime_experiment_server.py
# 端末2。利用許諾済みのVRM 1.0をローカルに指定

$env:MOTION_LAB_TEST_VRM = 'C:\Models\VRM1_Constraint_Twist_Sample.vrm'
node scripts/run_realtime_vrm_experiment.cjs
```

実験スクリプトは比較C、8秒の右手指示、4096 tokensの長い音声応答を使う。出力先は.motion-lab/realtime-run-<日時>、既存録画を上書きしない。標準D/3秒期限の実証ではない。VRMは公式[pixiv/three-vrmモデル](https://github.com/pixiv/three-vrm/blob/dev/packages/three-vrm/examples/models/VRM1_Constraint_Twist_Sample.vrm)から取得しメタデータを確認する。ライブラリMITとモデルのVRMライセンスは別。

## ローカル記録の再集計

```powershell
.\.venv\Scripts\python.exe scripts/build_mtg_report.py
.\.venv\Scripts\python.exe -m pytest -q
npm run test:unit
npx playwright test
```
集計スクリプトは元の.motion-lab/outputsと3つの録画フォルダーが必要。公開CSV/JSON/動画は元環境がなくても閲覧できる。集計は推論やAPI呼出しをしない。scripts/download_llama_ranges.pyは転送問題時の補助取得処理で、最終公式SHA-256照合を行う。元のsetup_modelsとprepare_lab_textを先に使う。

モデル、重み、VRM本体はGitHubから取得できると称さない。tests/browser/live.spec.cjsは別の厳しい短期限E2Eで、今回の長応答C試行と同条件ではない。既存record_vrm_demo.cjsは保存済みモーション/音声の再生であり新規推論ではない。
