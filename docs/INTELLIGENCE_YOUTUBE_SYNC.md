# YouTube連携・自チャンネル統計の同期（task-205）

task-234の拡張: 毎日同期・週1回の分析、初期30日レポートと制作上の選択の評価を追加。
[定時同期・30日評価](INTELLIGENCE_SCHEDULING_EVALUATION.md)を現行の追加仕様とする。
以下の「含まない」は統合①の当初範囲。

Clip Intelligence統合①。本人のOAuthと公式統計の取得だけを移す。
制作記録との結合、Codex分析、独自指標、制作への反映、分析画面、旧アプリのデータ移行・停止は含まない。
Clip Intelligenceのファイル・DB・認証情報は読み取り/参照だけとし、実行時の依存にはしない。

## 反映後の接続手順

1. ユーザーが `C:\BOT\ClipIntelligence\config\google-client.json` を
   AutoClipperの `storage/secrets/google-client.json` へコピーする。本文は表示・共有しない。
2. `http://localhost:3000/settings`（動画作成画面の「YouTube連携・設定」）を開く。
3. YouTube Studioで確認した自チャンネルのUCから始まる24文字のIDを入力し、「接続する」を押す。
4. Googleの画面で対象チャンネルを選び、YouTubeとAnalyticsの閲覧を許可する。
   指定IDと `channels.list(mine=true)` の返却IDが一致した場合だけ保存する。
5. 設定画面へ戻って「同期する」を押す。接続成功と同期成功は別の状態。
   最終成功日時、今回の結果、Analyticsの最新返却日を確認する。

実際のGoogle認可はユーザーが反映後に行う。競合チャンネルやAPIキーによる取得は扱わない。
認可・取得に金銭の自動支払いや他のAPIへの自動切替はない。

## 認証・秘密情報

- スコープは `youtube.readonly` と `yt-analytics.readonly` の2つだけ。
- `POST /api/intelligence/oauth/start` と `GET /api/intelligence/oauth/callback` を使用する。
- DesktopクライアントのループバックURLは既定
  `http://localhost:8000/api/intelligence/oauth/callback`。
  `YOUTUBE_OAUTH_REDIRECT_URI` でポート/ループバックホストを変えられる。
  外部ホスト、HTTPS、別のパス、query/fragmentは拒否する。
- stateは10分間有効・1回限り。HttpOnly/SameSite=LaxのブラウザcookieとPKCEにも結び付ける。
- 認可開始と同期のPOSTは、設定したフロントエンド以外のOriginを拒否する。
- トークンは `storage/secrets/youtube_tokens/<channel_external_id>.json`。
  一時ファイルを600で作成・書き込み後に置換する。親ディレクトリは700（Linux）。
  WindowsのACLをこの数値だけで保証するものではない。
- state/PKCEの一時情報も同じsecrets配下へ600で保存し、消費時または保守で削除する。
- APIにはトークン/クライアントシークレット/資格情報ファイルの本文を返さない。
  OAuthライブラリの資格情報debugログを抑止し、uvicornのcallbackアクセスログからqueryを除く。
- `invalid_grant` や401は「再接続が必要」にする。生のAPIエラー・例外文は保存/返却しない。
- `storage/secrets/` はGit対象外。バックアップの共有にも秘密情報を含めないこと。

## 取得と保存

参照元の `collect_self` / `native_report` の基本取得を移植し、動画別日次を追加する。
V2の流入元・維持率などの詳細分析やCodex実行は移していない。

|対象|取得範囲・粒度|
|---|---|
|動画一覧|本人のuploads最新200本＋既に追跡している動画のメタデータ再取得。公開動画だけ登録|
|公開統計|最新のviewCount / likeCount / commentCount。内部Analyticsのviewsとは別に保存|
|チャンネル日次|米国太平洋時間の昨日まで60日|
|期間集計|Analyticsの最終返却日まで28日と、その前28日。日次平均を再平均しない|
|動画別日次|同じ60日、既知の自動画でfilter。複数動画はday,video、単一動画はdayに既知IDを添える|
|動画別期間集計|同じ28日、動画ごとの公式集計|
|動画の形式|同じ28日のcreatorContentType。Shorts/通常/ライブを尺から推測しない。返却なしはunknown|
|初期7日|公開翌日から7暦日（America/Los_Angeles）、1回で最大50本。未取得分は次回に継続|

内部の10指標: views、engagedViews、estimatedMinutesWatched、averageViewDuration、
averageViewPercentage、likes、comments、shares、subscribersGained、subscribersLost。
NULLはUNAVAILABLE、空のレポートはNO_ROWS。0へ埋めない。負数のlikes、100%超の平均視聴割合も公式値のまま保持する。
チャンネル/動画、日次/期間、公開/内部の値を混ぜて足し合わせない。

5テーブルをSQLAlchemyのcreate_allで追加する（既存テーブルの列は変更しない）:

- `channels`: 本人チャンネルID、名前、メタデータ更新日、最終成功同期日。
- `channel_connections`: 接続状態、認可確認日、安全なエラーコード。資格情報はDBへ入れない。
- `youtube_videos`: 公開動画ID、タイトル・公開日時・尺・公式形式、最新公開統計と欠損理由。
- `video_daily_stats`: 対象チャンネル/動画、集計種別・期間・dimension、指標、欠損理由、出所・定義版・取得時刻・期限。
- `sync_runs`: queued/running/success/partial/failed、対象期間、最新返却日、件数、打切り、失敗理由。

HTTPはRQへの登録だけを行う。同一チャンネルの二重同期はDBのuniqueなclaimで409。
`YOUTUBE_SYNC_BUDGET_SECONDS` は30〜300秒、既定120秒。APIは最大90要求、各通信のI/Oタイムアウトは最大10秒。
RQはこの上限＋30秒（既定150秒）。通信中はORMのautoflushを止め、取得完了後に一括commitする。
必須部分の失敗では今回の統計を公開せず、前回の成功分を残す。失敗履歴は別途commitする。
workerの強制終了と取り残しは、失敗ハンドラ/保守からsync_runsをfailedにする。

### 動画別日次の分割・一時障害（task-206）

- `day,video`は動画数×日数が200以下になるよう分割し、必ず1応答で終了する。
  60日なら3本ずつで最大180行。85本は29要求、20本は7要求、1本は1要求。
  200行ちょうどの場合も2ページ目へ進まない。指標と対象の60日間は変えない。
- HTTP 500/502/503/504は0.25秒、0.5秒待って最大2回再試行する。
  再試行も90要求と時間の上限に数え、期限を超える待機は行わない。
- 動画別日次・動画別28日・形式・初期7日だけは、5xxが続いても`API_5XX`の欠損として
  `sync_runs.missing_reports`へ対象動画・期間・HTTPステータス・Google理由コードを記録し、
  他のレポートを保存して`partial`とする。既知の指標を一時障害のNULLで上書きしない。
  新規の欠損行はNULLと`API_5XX`で保存し、同じ範囲の取得に成功すると置き換える。
- 本人確認・動画一覧/メタデータ・チャンネル日次/28日/前28日は必須で、失敗すれば全体を`failed`にする。
  401（再接続）、403（権限/利用枠）、429（利用枠）、通信エラーも従来どおり全体失敗。
  400/404/409/410はそれぞれ別コード、その他は`API_HTTP_ERROR`とHTTPステータスを記録する。
  Googleの`errors[].reason`は識別子だけを残し、メッセージ本文・資格情報は保存しない。
- 任意レポートの要求数/時間上限、または初期7日の50本上限で打ち切った場合、
  `truncated=true`/`partial`とし、未実行の要求を`missing_reports`の`pending_reports`へ保存する。
  次の手動同期は、必須部分を更新してから保存した期間・動画の続きだけを先に取得する。
  続きを完了した後の同期から、再び全体の現在期間を更新する。非公開/削除済み動画は続きから外す。
  既存のJSON列を使うためDB列の追加・マイグレーションは不要。
- 85本のモック（全日データあり・形式1種類・初期7日対象85本）では最初が89要求、
  次が43要求で完了。実際の速度・再試行数で上限に達した場合も取得済み分と続きを保存する。
  画面の`NO_ROWS`件数にはAPI障害や打切りを含めず、既存のエラー表示に安全な理由を渡す。

## 利用条件・保持期限

2026-10-15のユーザー決定により、既定は `youtube_derived_allowed=True`、
`youtube_extended_storage=True`、確認日2026-10-15、
参照URLは [YouTubeの追加ポリシー](https://developers.google.com/youtube/terms/derived-metrics-policy)。
composeでも `YOUTUBE_DERIVED_ALLOWED` / `YOUTUBE_EXTENDED_STORAGE` を設定できる。

- 統計は取得日から最大36暦月（3年後の同日、閏日は月末へ）。extended_storageがfalseなら30日。
- タイトル・名前・公開日時・尺・形式は、30日更新できなければ消す。opaque IDと期限内の統計は独立保持する。
- workerの `run_maintenance_tasks` で期限処理する。動画出力を掃除する既存lifecycleはsecretsや統計を削除しない。
- 保持期限内であっても、このタスクでは派生指標を生成しない。

一次資料: [Channel reports](https://developers.google.com/youtube/analytics/channel_reports)、
[Desktop OAuth](https://developers.google.com/identity/protocols/oauth2/native-app)。
