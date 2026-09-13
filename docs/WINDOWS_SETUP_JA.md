# Windows導入・起動手順

GitHubの`main`から取得したAutoClipper Webを、自分のWindows PCで起動する手順です。

## 1. 必要なもの

| 必要なもの | 用途・確認点 |
| --- | --- |
| Docker Desktopが対応する64bit Windows | 対応OSと仮想化の条件は[Docker公式のWindows要件](https://docs.docker.com/desktop/setup/install/windows-install/)で確認 |
| WSL 2・Docker Desktop | 動画処理、Web画面、データベース周辺のサービスを起動 |
| Python 3.11以上 | `Start AutoClipper.cmd`からランチャーを起動。以下では3.11を使用 |
| インターネット接続 | 初回のコンテナ・文字起こしモデル取得、Codexによる選定や文言生成 |
| CodexとChatGPTログイン | Codexでの切り抜き選定、タイトル・フック・サムネ文言生成を使う場合 |
| 保存用の空き容量 | 元動画に加え、作業中の映像・完成動画・モデルを保存する容量 |

通常の利用では、FFmpeg、Redis、Node.js、backend用Pythonライブラリを個別に入れる必要はありません。Docker側に含まれます。ZIPで取得する場合はGitも不要です。

### Intel内蔵GPU・メモリ16GBのPC

i5-1334U / メモリ16GB / Intel Iris Xeでは、**CPU互換設定**を使います。Iris Xeは、このアプリのNVIDIA CUDA用GPU設定の対象ではありません。

CPU設定は`base / ja / cpu / auto`です。長い動画の文字起こし・書き出しはGPU搭載PCより時間がかかります。処理時間と実機での安定性は、短い動画で確認してください。

## 2. WSL 2とDocker Desktopを入れる

1. [Docker公式のWindows導入ページ](https://docs.docker.com/desktop/setup/install/windows-install/)からDocker Desktopをインストールします。
2. WSLが未導入なら、管理者として開いたPowerShellで次を実行します。再起動を求められたらWindowsを再起動します。

   ```powershell
   wsl --install
   ```

3. WSLを更新します。

   ```powershell
   wsl --update
   ```

4. Docker Desktopを起動します。設定ではWSL 2のエンジンを使い、Linuxコンテナで動かします。
5. 新しくPowerShellを開いて確認します。

   ```powershell
   wsl --version
   docker version
   docker compose version
   ```

`docker version`でClientとServerの両方が表示される状態にします。Serverへ接続できない場合はDocker Desktopの起動完了を待ちます。仮想化のエラーはDocker公式の要件・案内に沿って解消してください。

## 3. Pythonを入れる

[Python公式のWindows手順](https://docs.python.org/3/using/windows.html)に従い、Python Install Managerをインストールします。新しいPowerShellでPython 3.11を追加します。

```powershell
py install 3.11
py -3.11 --version
py -3.11 -m tkinter
```

最後のコマンドで小さいテストウィンドウが開けば、ランチャーが使うGUIも利用できます。確認後は閉じてください。

既にPython 3.11が使える場合は再インストール不要です。`py install`を認識しない場合は旧Pythonランチャーの可能性があるため、公式手順でInstall Managerを確認してください。

## 4. GitHubのmainから取得する

1. [AutoClipper WebのGitHub](https://github.com/yoyowasa/AutoClipper-Web)を開き、ブランチが`main`であることを確認します。
2. **Code → Download ZIP**を選びます。
3. ZIPを展開し、`Start AutoClipper.cmd`があるフォルダーを、例えば`C:\AutoClipper`へ置きます。

ZIP内から直接実行せず、展開してから起動してください。以後、このフォルダーに動画や設定が蓄積されます。

初回のCPU起動では`.env`の手動作成は不要です。個別の環境設定が必要な場合だけ、アプリのフォルダーで次を実行します。既存の設定は上書きしません。

```powershell
if (-not (Test-Path -LiteralPath .env)) {
    Copy-Item -LiteralPath .env.example -Destination .env
}
```

## 5. Codex連携を確認する

Codexをインストールし、ChatGPTアカウントでログインします。AutoClipperはホスト側のCodex実行ファイルを探し、連携用の処理を起動します。PATH上の`codex`に加え、対応するCodexアプリのインストール先も探索します。

**Codexアプリが入っているだけでは、連携のログイン確認が通るとは限りません。** `codex`コマンドが使える場合は次で確認できます。

```powershell
codex login status
```

ChatGPTでのログインが未完了なら、`codex`を起動して「Sign in with ChatGPT」を選びます。CLIが見つからない場合は[Codex公式のCLI導入手順](https://learn.chatgpt.com/docs/codex/cli)のWindows向け案内に従い、導入後にAutoClipperを開き直してください。

この連携ではOpenAI APIキーの入力は不要です。任意のOpenAI API機能とは別の仕組みです。Codexの利用可能量・ログイン状態によって、選定や文言生成を実行できない場合があります。

## 6. AutoClipperを起動する

1. `Start AutoClipper.cmd`をダブルクリックします。
2. ランチャーが推奨設定で自動起動します。Intel内蔵GPUのPCで再試行する場合は**「CPU互換設定で起動」**を押します。
3. 初回はDockerイメージを準備するため待ち時間があります。文字起こしモデルも初回利用時に取得されます。
4. 起動完了後、ブラウザで[動画作成画面](http://localhost:3000/upload)が開きます。開かない場合はランチャーの**「Open App」**を押します。

「GPU必須で起動」は対応するNVIDIA環境向けです。Intel内蔵GPUのPCでは選びません。

### 最初の動作確認

1. まず短い動画（例: 5分程度）を選びます。
2. 作成する動画を「ショートのみ」、本数を1本にします。
3. 文字起こし設定がCPU用の`base / ja / cpu / auto`になっていることを確認します。
4. 作成を開始し、切り抜き予定の確認、字幕確認、書き出しへ進みます。
5. 完成MP4を開き、映像・音声・字幕を確認します。

初回の動作が確認できてから長尺動画や本数を増やしてください。CPUで処理中はWindowsのスリープを避け、ノートPCは電源につないで使用します。

## 7. 終了・次回起動

- 終了: ランチャーの**「Stop Services」**を押します。ブラウザを閉じるだけでは処理は停止しません。
- 次回: 同じフォルダーの`Start AutoClipper.cmd`を開きます。
- 出力先: **「Open Outputs」**で完成動画のフォルダーを開けます。

「Stop Services」は設定や保存動画を削除しません。動画処理中の停止は避けてください。

## 8. 更新方法

### ZIPで取得した場合

1. 動画処理の終了を確認し、「Stop Services」で停止します。
2. 既存フォルダーをバックアップします。特に`storage`、`.env`、`youtube`、自分で追加したフォントを残します。
3. 最新の`main`のZIPを別の場所へ展開します。
4. 新しいコードを元のアプリフォルダーにコピーします。既存の`storage`や`.env`など、保存データは削除・初期化しません。
5. `Start AutoClipper.cmd`を開き、**「再ビルドして起動」**を押します。

### Gitで取得した場合

変更や処理が残っていないことを確認して停止し、アプリのフォルダーで実行します。

```powershell
git switch main
git pull --ff-only origin main
```

その後「再ビルドして起動」を押します。ローカル変更や履歴の分岐で失敗した場合は、その内容を確認してください。設定を消すリセット操作で回避しないでください。

## 9. 別PCへの設定移行

**GitHubからの取得だけでは、今のPCのキャラ設定・作成した帯・動画は移りません。**

- キャラ設定などのサーバー保存情報は`storage/autoclipper.db`に含まれます。
- 作成した帯などの素材、元動画、出力動画も必要なので、DBだけでなく`storage`全体を移すのが確実です。
- 両PCでサービスを停止してからコピーします。移行先にデータがある場合は先にバックアップしてください。
- `.env`を引き継ぐ場合はPC固有の設定を確認します。Codexのログインは移行先PCで行います。
- ブラウザ内だけに保存されている設定は、フォルダーのコピーでは移りません。キャラ設定はTOP画面で保存してから移行し、移行後に呼び出して内容を確認してください。
- 追加フォントは別途導入が必要です。配布対象外のフォントについては[フォントの案内](../frontend/public/fonts/README.md)を確認してください。

## 10. 起動できないとき

| 症状 | 確認すること |
| --- | --- |
| Pythonがないと表示される | `py -3.11 --version`。インストール後はランチャーを開き直す |
| Dockerに接続できない | Docker Desktopが起動済みか、`docker version`にServerが表示されるか |
| WSL・仮想化エラー | WSL更新、Windows再起動、Docker公式のOS・仮想化要件 |
| GPU起動が失敗する | Intel内蔵GPUなら「CPU互換設定で起動」 |
| 画面が開かない | 「Refresh」「Open App」。3000番ポートを他アプリが使っていないか |
| Codexで選定・生成できない | ChatGPTログイン、利用可能量、Codex実行ファイルの検出結果 |
| 初回が遅い | コンテナやモデル取得中か「Docker Logs」「Launcher Log」で確認 |
| 更新したのに画面が古い | 「再ビルドして起動」後、編集を保存してからブラウザを再読み込み |

解決しない場合は、失敗した操作とエラー文をCodexに伝えてください。`.env`本文・APIキー・ログイントークンは貼らないでください。
