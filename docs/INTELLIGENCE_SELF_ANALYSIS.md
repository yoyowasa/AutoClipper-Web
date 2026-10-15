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
- Codex中継自体は共用・直列のまま。分析と同時にCodexを使うサムネ文言などを依頼すると、
  中継側の順番待ちや既存の待機上限による時間切れの可能性は残る。中継の並列化や優先順位変更は行わない。
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
- 動画別×日別の全行を重ねて渡さず、日次推移はチャンネルの日次、
  動画比較はネイティブの動画別期間集計・初期7日で行う。
- 数値の根拠IDは `r:<日次統計行ID>:<指標名>`、公開累計は `p:<動画ID>:<指標名>`。
  出所・対象・期間・観測日時・指標定義を共有グループへまとめ、NULLを0に変換しない。
- 結び付いた動画には `production:<recordId>` として制作記録の尺・フック・タイトル候補と選択、
  intent・選定理由・openingScore・キャラを付ける。結び付きの無い動画に推定で補わない。
- 入力は最大280,000文字。上限超過は理由付きで失敗し、黙って根拠を切り落とさない。

## 返答と保存

Clip IntelligenceのReviewスキーマ（所見、仮説、代替説明、反対証拠、次の確認、制作案、
推薦面との関係）を使う。移植先の動画キーに合わせ、`baseline_video_id` は11文字の
YouTube動画ID文字列とした。所見・制作案の根拠ID、チャンネル、同期ID、基準動画の形式、
推薦面の公式説明との対応を検証する。不正な返答は保存しない。

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
