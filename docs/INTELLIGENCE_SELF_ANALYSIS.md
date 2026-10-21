# Codexによる自チャンネル分析（統合③）

設定画面の「YouTube連携」でチャンネルごとに「分析する」を押す。
分析前の同期は「24時間以上経過していれば同期」（既定）、「同期してから分析」、
「保存済みの統計で分析」から選ぶ。同じチャンネルの分析は同時に1件だけ。
同期・Codex生成・検証はRQで行い、HTTPは開始の受付だけを返す。

## 専用キューとworker

- 切り抜き・字幕プレビュー・サムネ文言・書き出しは従来の `RQ_QUEUE_NAME`
  （既定 `autoclipper`）を `worker` が処理する。
- YouTube同期と自己分析は `RQ_INTELLIGENCE_QUEUE_NAME`
  （既定 `autoclipper-intelligence`）を `intelligence-worker` が処理する。
  設定で同じキュー名にはできない。Codexの応答待ちは切り抜きworkerを占有しない。
- Codex中継は通常レーン（従来どおり直列）と分析レーン（同時に1件）で並行処理する。
  自己分析の生成中も通常のタイトル/フック・サムネ・初期選定の処理ループは進む。
- `intelligence-worker` はCPU用DockerfileとCPUプロファイルを使う。
  GPU構成でもGPUの割り当てやCUDA事前検証は行わない。storageとRedisは共通。
- RQの失敗記録（時間切れ・例外・親プロセスが検知したSIGKILL）は両workerで共用する。
  アプリの保守処理は担当を分け、切り抜きの孤立ジョブ点検は `worker` だけ、
  同期/分析の取り残し・YouTube保持期限・認可stateの期限切れ点検は `intelligence-worker` だけが行う。
  RQ自体の保守処理はそれぞれ自分のキューだけを対象にする。各サービスは1プロセスで運用する。

### 反映前の確認

旧キューの仕事を自動移動する処理は無い。両キューの順番待ち・実行中・取り出し中が0件、
DBに実行中ジョブが無いこと、Codex中継のrequests/processingが空であることを確認してから反映する。
実行中として残った行の例外扱いは、従来どおりユーザーの明示指示がある場合だけ。
次の読み取りではRedis登録のcleanupを行わない。`$intelligenceQueue` は反映予定の
`RQ_INTELLIGENCE_QUEUE_NAME` の値に合わせる（下は既定値の例）。旧backendには新設定が無いため引数で渡す。

```powershell
$intelligenceQueue = "autoclipper-intelligence"
@'
import sys
from app.config import get_settings
from app.jobs.queue import get_redis_connection
from rq import Queue
settings = get_settings()
for name in (settings.rq_queue_name, sys.argv[1]):
    queue = Queue(name, connection=get_redis_connection())
    print(name, "queued", queue.count,
          "started", len(queue.started_job_registry.get_job_ids(cleanup=False)),
          "intermediate", len(queue.intermediate_queue.get_job_ids()))
'@ | docker compose exec -T backend python - $intelligenceQueue
```

DBをbackup()で複製・検証してから、GPU構成なら次の4サービスを作り直す（Redisは作り直さない）。

```powershell
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build backend worker intelligence-worker frontend
```

起動後は4サービス、backendのhealth、画面、両workerの監視キューと専用workerのCPUプロファイルを確認する。
task-208全体では新しいCodex依頼種別も追加しているため、ホスト側Codex中継の再起動も必要。
このPRでは稼働環境への反映は行わない。

## 入力と根拠

- 最新の成功または一部成功した同期の最終返却日を基準に、直近28日・前28日、
  チャンネルの日次推移、動画別の期間集計と初期7日を渡す。
- 公開累計とAnalyticsの期間集計を区別し、平均の再平均や独自指標は作らない。
- 通常・ショート・ライブ・不明に動画を分ける。形式別チャンネル全体の集計、
  流入元・維持率・CTR・スワイプ率は現在の同期に無いため、欠損として渡す。
- 動画別×日別の全行は渡さず、動画ごとに返却日分の期間合計、公式の直近28日・初期7日、
  viewsが最多のピーク日（同値なら新しい日）へ要約する。期間合計は最大60日間の返却済み日だけの
  加算可能な指標の合計で、返却日数・未返却日数を併記する。平均・割合は合算も再平均もしない。
  指標定義や出所が異なる日次行は合算せず欠損理由を残す。チャンネル全体の日次推移は最大60日分を残す。
- 根拠は `channel_reports` と各動画の `reports` に一度だけ収録する。
  `report.id` と `values` の指標名をコロンでつないだものが根拠ID。
  公式値は `r:<統計行ID>:<指標名>`、公開累計は `p:<動画ID>:<指標名>`、
  返却日合計は `v:<動画ID>:period_total:<指標名>`。
  出所・指標定義・タイムゾーンの共通値は `report_defaults` に置き、差がある場合だけ各reportで上書きする。
  出所・期間・観測日時はreportごとに保持し、NULLや未返却日を0に変換しない。
  同じ期間・指標定義・値・欠損理由のvideo_period/video_formatだけ重複を除く。
  検証用のID索引はサーバー側だけで展開し、入力に重ねて送らない。
- 結び付いた動画には `production:<recordId>` として制作記録の尺・フック・タイトル候補と選択、
  intent・選定理由・openingScore・キャラを付ける。結び付きの無い動画に推定で補わない。
- 対象は最終返却日から直近90日以内の公開動画と、形式別の公開累計views上位・下位各5本。
  成績上位・下位を先に確保し、残りを公開日の新しい順に埋め、最大100本までとする。
  公開累計が欠損の動画は順位づけから外し、0再生とみなさない。対象条件・候補総数・除外件数は `input_scope` に明記する。
- プロンプト全文（指示文を含む）の上限280,000文字に対し、260,000文字を入力予算にする。
  予算を超えたら古い公開動画から1本ずつ制作情報・根拠ごと省略し、チャンネル全体の日次推移を維持する。
  `budget_omissions` に省略動画のID・本数・report数を残し、形式別一覧と検証用ID索引からも除く。
  省略内容は保存する入力スナップショット・検証診断に残し、Reviewのlimitationsにもサーバーが必ず追記する。
  既存のlimitationsは捨てない。対象外の動画に結論を一般化しない。
  返答スキーマとCodex中継の指紋は変更しないため、task-216に伴う中継の再起動は不要。

## 返答と保存

Clip IntelligenceのReviewスキーマ（所見、仮説、代替説明、反対証拠、次の確認、制作案、
推薦面との関係）を使う。移植先の動画キーに合わせ、`baseline_video_id` は11文字の
YouTube動画ID文字列とした。所見・制作案の根拠ID、チャンネル、同期ID、基準動画の形式、
推薦面の公式説明との対応を検証する。不正な返答は保存しない。

### 個別の不備と診断（task-209）

分析ID・チャンネルID・同期ID・frameworkの不一致は、従来どおり分析全体を失敗にする。
それ以外の所見・提案は1件ずつ検証し、存在しない根拠ID、基準動画の形式不一致、
評価指標や項目形式の不備があるものだけを除外する。有効な所見が1件以上残れば、
提案が0件でも残った部分を成功として保存する。基準動画の形式がunknownの場合は
`BASELINE_FORMAT_UNKNOWN` とし、`BASELINE_FORMAT_MISMATCH` と区別する。
所見の形式と根拠動画の形式が違う場合も、勝手に全体形式へ置き換えず、その所見を除外する。

実行IDごとの `channel_analysis_validation` テーブルに除外件数・理由コード別件数・
項目位置（loc）を保存し、GETの `validation` と設定画面の最新状態・履歴で表示する。
同じ1件に複数理由が付く場合があるため、理由件数の合計と除外件数は必ずしも一致しない。
既存DBの列は変更せず、起動時のcreate_allで新テーブルを追加する。
診断にはCodexの出力値・本文・例外メッセージを含めず、未知の項目名も `[extra]` に置き換える。
出力本文はログに出さない。検証済みの所見・提案だけが既存の保持期限で保存される。
旧版で失敗した実行には診断が無く、消去済みの返答から後付けで復元はしない。
Codexの指示文・返答スキーマと中継の指紋は変更していない。

### 保存済み動画の形式を修復する

`creatorContentType` は、実データの `shorts` / `videoOnDemand` と、
[公式の列挙値](https://developers.google.com/youtube/analytics/dimensions#creatorContentType)
（`SHORTS` / `VIDEO_ON_DEMAND` / `LIVE_STREAM`）を同じように認識する。
大文字小文字・区切り文字を正規化し、liveStreamもliveとして扱う。
Storyや未指定などはunknownのままにし、動画の尺から形式を推定しない。

既存データの修復は、保存済みvideo_format / first7レポートを使う管理コマンドで行う。
既定はdry-runで、`--execute` を明示したときだけDBを更新する。

```bash
python -m app.maintenance repair-youtube-video-formats --dry-run
python -m app.maintenance repair-youtube-video-formats --execute
```

最新の観測にある形式が1つに定まる場合だけ更新する。値のない欠損レポートは無視する。
形式が競合する場合・根拠が無い場合・メタデータまたは統計の期限切れの場合は推定しない。
修復は勝手に起動時実行しない。稼働DBでの実行は反映後に別途承認して行う。

`channel_analysis_runs` に状態、入力スナップショット、検証済みReview、モデル、推論、
中継依頼IDを保存する。生成中に元の根拠が変わった場合も保存しない。
新しい分析が失敗しても、保持期限内の直近の成功結果は表示する。
採用・改善試験・選定への自動反映は行わない。

## Codex中継と時間制限

- 新しい依頼種別: `channel_self_analysis`。文字入力のみ。
- この種別だけ `gpt-6-astra` / `high`。既存種別のモデル・推論・スキーマ指紋は維持する。
- ホストの生成上限900秒、backendの中継待ち960秒。
  RQ上限は同期予算＋960＋60秒（同期予算の既定120秒では1140秒）。
- 履歴を残さない一時セッションで実行し、分析専用の中継ファイルとホストの一時作業領域を片付ける。
  強制終了で残った分析専用領域も入力と同じ期限を持ち、中継の起動時・以降1時間ごとの点検で期限切れを削除する。
- **反映時はホスト側Codex中継の再起動が必要。** PRの作成だけでは稼働環境は変わらない。

### 分析レーン

`channel_self_analysis` だけを専用の非daemonスレッドが取り出し、1件ずつ処理する。
通常ループは分析を取り出さず、従来の依頼は同じ順序で直列処理する。
両レーンはrequestsからprocessingへの `os.replace` によるclaimを使い、
processingに同じIDがある場合は上書きしない。既に応答がある依頼は再実行しない。

心拍は共有ロックの下で両レーンの状態をまとめる。
既存の `requestId` / `requestState` はどちらかが処理中ならprocessingを保ち、
通常依頼が動いていればそのIDを優先する。
追加の `normalRequestId` / `analysisRequestId` で各レーンの処理中IDを識別できる。
片方の完了で他方をidleにせず、更新時刻もそれぞれの処理中に更新する。

stop_requestでは両レーンが同じ停止ファイルを読み、実行中の子プロセスを停止する。
通常の中継終了処理でも停止要求を出し、分析スレッドと心拍の終了を待ってからstoppedを公開する。
メインスレッドのSIGTERMも停止要求へ変換する。割り込みで抜ける実行関数は子プロセスを終了させる。
`--once` は初回の両レーンの依頼を処理し終えてから終了する。
強制killや電源断でprocessingに残った依頼は、再起動時の既存処理でrequestsへ戻す。
応答が既にある場合は再実行せず、queuedのコピーがある場合も同じIDを二重実行しない。
モデル・推論・各依頼の時間上限・応答スキーマ指紋は変更しない。

## 保持期限

タイトル等を含む入力・Reviewは最大30日。ただし根拠のメタデータ・統計が先に期限を迎える場合は
その最短の期限まで。YouTube統計の36か月保持で分析文の寿命を延ばさない。
期限処理は入力・Reviewを消し、本文を含まない実行ID・モデル・時刻等だけを監査用に残す。
GETは期限切れの本文を返さない。停止していたworkerや中継の削除処理は再開後に動く。

## API

- `POST /api/intelligence/channels/{id}/analysis`
  - JSON: `{"syncBefore":"auto"}`（`always` / `never` も可）。`{}` は `auto`。
  - 202: 順番待ち。同期中・同一チャンネル分析中・再接続が必要なら409。
  - Origin確認は既存のYouTube連携と同じ。
- `GET /api/intelligence/channels/{id}/analysis`
  - `latestRun`、保持期限内の成功結果 `latestResult`、直近20件の `history`。
  - `Cache-Control: no-store`。失敗理由は許可した安全な文言のみ。

実チャンネルでのCodex実行と分析品質の受入確認は、反映後にユーザーが行う。
