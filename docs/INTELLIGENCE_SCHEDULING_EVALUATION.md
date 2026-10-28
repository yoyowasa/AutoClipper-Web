# 定時同期・自己分析と選択ごとの30日評価（task-234）

## 定時実行

既存の `intelligence-worker` の保守処理から接続済み自チャンネルを点検する。
キュー、worker、DBテーブル、外部スケジューラは増やさない。

| 設定 | 既定値 | 意味 |
|---|---|---|
| `YOUTUBE_AUTOMATION_ENABLED` | `true` | 定時実行の有効化 |
| `YOUTUBE_AUTO_SYNC_HOUR_UTC` | `3` | 毎日の同期時刻（日本時間12時） |
| `YOUTUBE_AUTO_ANALYSIS_WEEKDAY` | `0` | 週1回の分析曜日。月曜=0〜日曜=6、同期と同時刻 |
| `YOUTUBE_MAINTENANCE_INTERVAL_SECONDS` | `60` | 点検間隔（30〜3600秒） |

- 週の分析は `syncBefore=always` で同期してから分析する。その日は別の同期を重ねない。
- 起動時は現在の周期の未実行分を1回実行し、停止中の全日分を積み直さない。
  処理中なら完了後に点検する。空キュー待機も点検間隔以内で解除する。
- 手動・自動の同期と分析は共通のDB claimを使う。SQLiteの書き込みロックを取って
  既存 `SyncRun` / `AnalysisRun` の実行中状態と周期を確認し、二重登録を防ぐ。
- 手動実行も当該周期の試行として数える。失敗も同じ周期では自動連打せず、
  同期は翌日、分析は翌週に再試行する。手動開始は引き続き使える。
- クォータ・認証・Codex・キュー登録の失敗は、既存履歴に安全な理由コードを残す。
  同期失敗時は分析に `STATISTICS_FAILED`、対応する同期に元の理由が残る。
  認証切れは再接続待ちとし、再接続後に再開する。有料APIや別プロバイダへ切り替えない。
- 派生指標の許可が無い場合は自己分析・独自集計をしない。

実装: [scheduling.py](../backend/app/intelligence/scheduling.py)、
[job_claims.py](../backend/app/intelligence/job_claims.py)、[worker.py](../backend/app/intelligence/worker.py)。

## 目標と期間

- 通常10万／ショート100万再生、初期30日を最終の区切りとし、初期7日は途中評価。
- 日付は既存の初期7日と同じ **America/Los_Angelesの公開翌日からの暦日**。
  30日目の終了後、その期間の公式値が返ってから判定する。厳密な720時間ではない。
- 公開累計や直近28日を初期30日の代用にしない。観測された0再生は0だが、
  未返却・期限切れ・形式不明・30日未到達は未判定／データ不足。目標未達をジョブ失敗にしない。
- `first30` を既存 `video_daily_stats` に保存する。公式の `creatorContentType` 別期間集計を使い、
  1同期90リクエスト・時間予算・初期期間レポート合計50件の上限を維持する。
  超過分は既存 `pending_reports` で次回に引き継ぐ。85本では複数周期に分けて7日と30日を回収する。
- APIの最終返却日と期間を確かめる。未返却を0にしない。
  [公式query仕様](https://developers.google.com/youtube/analytics/reference/reports/query)、
  [公式の日付定義](https://developers.google.com/youtube/analytics/dimensions#day)。
- 新しい分析返答は `goals={normal_views:100000,short_views:1000000,window_days:30,interim_days:7}` を必須にする。
  旧 `goal_views` は読み込み互換だけに残し、画面でも旧目標の分析と区別する。

## 選択と成績

- `production_links` で結び付いた最新の制作記録を読む。公開までの `choiceHistory` の最終適用値を種類別に選び、
  未採用案や公開後の編集を、その投稿動画の選択として数えない。
  文字スタイルはタイトル・フック・字幕を分け、同一値の再送で出所を手動に変えない。
  出所未記録を自動と推定しない。
- 範囲、タイトル／フック、サムネ、画角、スタイル、演出、投稿文等の記録ID・選択ID・値／ハッシュ・
  選択肢ID・出所・方針版を、対象動画・評価期間・観測時点・根拠ID・達否と一緒に保存する。
  値が2000文字を超える場合は省略を明記し、IDとハッシュで追跡する。
- キャラ×形式×種類／役割×出所×方針版×比較可能な設定で集計する。
  画角方式、フォント／サイズ、サムネの出所／構図、タイトルintent等を分ける。
  異なるタイトル文や範囲は動画ごとの根拠に残す。設定未記録なら方針単位の観測とする。
- 対象数と30日判定済み数を分け、中央値・到達率は判定済み動画だけで計算する。
  判定済み5本未満・出所未記録・版未記録はデータ不足。5本以上でも**効果は未確認**で因果を断定しない。
  同じ動画が複数の選択に属するため件数を足し合わせない。
- 既存 `ProductionAggregate.payload.choice_evaluations` に保存し、同期成功／一部成功後と分析入力作成時に更新する。
  集計失敗でも取得済み統計は残し、同期に `EVALUATION_FAILED` を記録する。
  元統計の最短期限（最大36か月）と、分析本文・入力の既存30日期限を超えない。
- `/intelligence` に「独自集計」として表示する。Codexには最大30グループ・4万文字の要約と根拠IDを渡し、
  省略数を残す。制作ヒントも既存の件数・形式・動画・期限の検証を通す。
  **選び方の自動更新・重み変更・版の切り替えと巻き戻しは残り作業3であり、本タスクでは行わない。**

実装: [choice_evaluation.py](../backend/app/intelligence/choice_evaluation.py)、
[evaluation_rules.py](../backend/app/intelligence/evaluation_rules.py)、[analysis_input.py](../backend/app/intelligence/analysis_input.py)。

## 契約・反映・未確認

プロンプトは `channel_self_analysis_v4`。`channel_self_analysis` の返答スキーマ指紋を更新したため、
**将来の反映時にホスト側Codex中継の再起動が必要**。
他の依頼種別・指紋・モデル、通常／分析レーンは変えない。
既存の手動同期・分析・改善試験の初期7日比較も維持する。
実装PRでは稼働環境・実Google同期・実Codex分析を変更／実行せず、モックと隔離環境で検証する。
定刻の実運用、公式30日値の到着、投稿成績への効果は反映後の受入事項。
