# textToMotion

Python・Node.js を使用できる GitHub Codespaces の開発環境です。
アプリケーションコードやプロジェクト固有の依存パッケージはまだ追加していません。

## Codespaces を起動する

1. [Codespace の作成画面](https://codespaces.new/nk-an-nk/textToMotion?ref=main)を開きます。
2. ブランチが `main` であることを確認し、`Create codespace` を押します。
3. 環境の準備が終わるとブラウザで VS Code が開きます。

`.devcontainer/devcontainer.json` に指定した公式 Universal イメージを使用します。
Python・Node.js・npm・Git・GitHub CLI などを含み、Python と Jupyter の VS Code 拡張を追加します。

ターミナルで次のコマンドを実行し、実際のバージョンを確認できます。

```bash
python --version
node --version
npm --version
git --version
gh --version
```

## 開発を始める

Python の依存パッケージを追加する場合は、プロジェクト内に仮想環境を作成します。

```bash
python -m venv .venv
source .venv/bin/activate
```

Node.js プロジェクトを作成する場合は `npm init` を実行します。

Web サーバーを動かす場合は `0.0.0.0` にバインドし、VS Code の `Ports` タブから転送先を開きます。
API キーなどは [Codespaces secrets](https://github.com/settings/codespaces) に登録します。

環境設定を変更した場合は、コマンドパレットから `Codespaces: Rebuild Container` を実行します。
作業終了時は [Codespaces 一覧](https://github.com/codespaces)から環境を停止できます。

## 参考

- [GitHub: 開発コンテナーの概要](https://docs.github.com/en/codespaces/setting-up-your-project-for-codespaces/adding-a-dev-container-configuration/introduction-to-dev-containers)
- [GitHub: Codespace の作成](https://docs.github.com/en/codespaces/developing-in-a-codespace/creating-a-codespace-for-a-repository)
- [公式 Universal イメージ](https://github.com/devcontainers/images/tree/main/src/universal)
