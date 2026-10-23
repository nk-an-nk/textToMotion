# NUWA Robot SDK 開発環境

GitHub CodespacesでNUWA Robot SDKを利用するための開発環境です。
アプリケーションコードは含めていません。text to motionのアプリへの組み込みも行いません。
NUWA Developerへの登録・ログインは不要です（メーカー回答に基づく）。

## 起動する

1. [Codespaceの作成画面](https://codespaces.new/nk-an-nk/textToMotion?ref=main)を開きます。
2. ブランチが `main` であることを確認し、`Create codespace` を押します。
3. VS Codeが開いた後も、初期設定の完了を待ちます。作成ログ末尾に `NUWA SDK development environment is ready.` と表示されれば準備完了です。

既存のCodespaceを使う場合は、変更を取り込んでからコマンドパレットの `Codespaces: Rebuild Container` を実行します。
通常の再開時に再インストールは不要です。初期設定に失敗した場合は `bash .devcontainer/setup.sh` で再実行できます。

## 用意されるもの

32GBのCodespaceでも展開できるよう、Universalイメージから軽量なPythonイメージへ変更しています。

| 項目 | バージョン・場所 |
| --- | --- |
| Java JDK | 17（公式Dev Container Java Feature） |
| Gradle | 8.7 |
| Android Command-line Tools | 19.0 / build 13114758 |
| Android SDK Platform | API 28、35 |
| Android Build Tools | 34.0.0 |
| Android Platform Tools | 初期設定時にGoogleから取得する `adb` など |
| NUWA Robot SDK | メーカー指定の 2.1.0.08 / 2023-10-11 |
| Python・Node.js | Python 3.12の公式イメージ + Node.js 22の公式Feature |

Android SDKは `/home/vscode/android-sdk`、NUWA SDK本体は次のパスに配置されます。

```text
sdk/nuwa/NuwaSDK-2023-10-11_v2.1.0.08_513b45c_release.aar
```

`ANDROID_HOME`、`ANDROID_SDK_ROOT`、`NUWA_SDK_AAR` と開発ツールの `PATH` は設定済みです。
NUWAのAARはGitに登録せず、メーカー指定URLから初期設定時に取得します。
SHA-256は `be9ccb81744cae7b31ea4506687e5bd33be38c9a431f0e0d1a245960a1918f72` です。
この値は今回取得したファイルから計算したもので、メーカー公表値ではありません。
初期設定スクリプトはAndroid SDKのライセンスに同意してコンポーネントをインストールします。

## 環境を確認する

Codespaceのターミナルで実行します。

```bash
bash scripts/check-environment.sh
```

Java、Gradle、Androidツールの起動、必要なSDKファイル、NUWA AARのチェックサムとZIPの整合性を確認します。
AARだけを再取得・確認する場合は `bash scripts/download-nuwa-sdk.sh` を実行します。

## 開発と実機確認

NUWA SDKはAndroid向けのAARです。PythonやNode.jsから直接importするライブラリではありません。
今後Androidプロジェクトを作る際は、このAARをアプリの `libs` に配置してGradle依存関係に追加します。
AGP 8.6.1を選ぶ場合は、この環境のGradle 8.7・JDK 17・API 35で構成できます。
公式サンプルは古いGradle構成を含むため、コピーするだけでこの環境でビルドできるとは限りません。

Codespacesでは編集やAPKのビルドを行い、Kebbi実機へのインストールと動作確認はロボットをUSB接続した手元のPCで行います。
クラウドのCodespaceから手元のUSBデバイスは直接見えません。
一般的なAndroidエミュレータにはNUWAのロボットサービスがないため、ロボットAPIの実行確認にはKebbi実機が必要です。

作業終了時は [Codespaces一覧](https://github.com/codespaces) から環境を停止できます。

## 公式資料

- [メーカー指定SDK本体](https://bj.bcebos.com/v1/nuwarobotics-files/sdk/NuwaSDK-2023-10-11_v2.1.0.08_513b45c_release.aar)
- [日本語チュートリアル（公式の現行リンク）](https://developer-docs.nuwarobotics.com/sdk/NUWA_Robot_SDK_Tutorial_jp.html)
- [NuwaRobotAPIリファレンス](https://developer-docs.nuwarobotics.com/sdk/javadoc/reference/com/nuwarobotics/service/agent/NuwaRobotAPI.html)
- [公式ドキュメント一覧](https://github.com/nuwarobotics/NuwaDocumentMD)
- [公式サンプル](https://github.com/nuwarobotics/NuwaSDKExample)
- [Android開発ツール](https://developer.android.com/studio#command-tools)
- [AGP 8.6の互換性](https://developer.android.com/build/releases/agp-8-6-0-release-notes)
