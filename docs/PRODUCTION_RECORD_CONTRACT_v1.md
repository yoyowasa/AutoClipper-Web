# Production Record Contract v1

完成動画1本の制作情報を、Clip Intelligenceの投稿後分析に渡すための契約。
`schemaVersion: 1`。UTF-8のJSON、末尾に改行を付け、`write_json_atomic`で保存する。

## 保存場所と更新

`storage/production_records/<export_id>.json`。パスは`StoragePaths.production_record()`で組み立てる。
動画・字幕・投稿メタデータの公開とDBの完了更新が成功した後に作成する。
記録の保存に失敗した場合はIDと例外の種類だけを警告ログに出し、動画は完成済みのままとする。
ジョブ削除、保存期間切れ、プレビューの掃除では消さない。

- `createdAt`＝書き出し完了時刻。backfillも同じで、対象の`ExportItem.created_at`を使う。
  SQLiteのタイムゾーン無し日時はUTCとして扱い、ISO 8601の末尾`Z`で保存する。
  `--force`で既存記録を作り直す場合も、createdAtを同じ書き出し時刻へ修正する。
  `updatedAt`は更新時刻とcreatedAtの遅い方にし、常に`updatedAt >= createdAt`を満たす。
- 初回の`revision`は1。同じExportItemの通常の更新は+1。`createdAt`を保持し、`updatedAt`を更新する。
- 現在の字幕再書き出しはExportItemを新しいIDで作り直す。公開APIやIDは変更せず、
  同じjob・candidateの前の記録からrevisionとcreatedAtを引き継ぐ。
  新しいIDのファイルを作り、`previousRecordId`に前のIDを記録する。旧記録は保持する。
  前の記録が無い場合は1から開始する。
- 日時はUTCのISO 8601形式（`Z`または`+00:00`）。
- 候補が無い旧データは空配列、取得できない任意の値は`null`。推定値で埋めない。
- 記録は書き出し確定時のスナップショット。完成後のサムネ編集などはその時点では再保存しない。
  現在の状態への更新にはbackfillの`--force`を使う。

## 結び付けキー

`publicationTitle`は`export_download_name(export).stem`と完全に同じ値。
動画・サムネのダウンロード名から拡張子を除いたものと一致し、YouTube Studioの初期タイトルとの一致で結び付ける。
Windows禁止文字の全角化、制御文字の除去、末尾の空白・ピリオド除去、予約名への先頭`_`追加、
100文字の制限を既存のダウンロード規則からそのまま使う。タイトルが無い場合は連番名にする。
ユーザーがYouTube側でタイトルを変えた場合や同じタイトルを複数回投稿した場合の照合は、この契約では扱わない。

## フィールド

| フィールド | 型・意味 |
| --- | --- |
| schemaVersion | 整数、常に1 |
| performanceHints | 任意の配列。選定/タイトル・フック生成で参照した実績ヒント。旧記録にはなくてよい。未使用なら省略 |
| recordId | 文字列、ExportItemのID |
| revision | 1以上の整数、記録の更新回数 |
| createdAt / updatedAt | 書き出し完了時刻 / 記録の更新時刻。backfillもcreatedAtはExportItem.created_at。updatedAtはcreatedAt以上 |
| previousRecordId | 文字列またはnull、新IDでの再書き出し元の記録ID |
| jobId | 文字列 |
| type | `normal` / `short` |
| publicationTitle | 投稿タイトル兼ダウンロード名のstem |
| overlayTitle / hookText | 文字列またはnull |
| hookSceneStart / hookSceneEnd | 秒またはnull。本編の開始を0とした相対時刻。完成動画の冒頭に追加したフックの再生位置ではない |
| thumbnailKicker / thumbnailLine1 / thumbnailLine2 | サムネ文言。文字列またはnull |
| titleCandidates | 下記のタイトル情報 |
| postMetadataSource | 文字列またはnull。既存の`codex` / `manual` / `existing`など |
| bodyDurationSeconds | 本編の秒数。メタデータの本編尺、元動画のend-startの順で取得。どちらも無い旧データではExportItem.duration |
| completedDurationSeconds | ExportItem.duration。完成動画の本編＋フックの秒数 |
| source | 下記の元動画情報 |
| characterPresetName | 設定中のキャラプリセット名、無ければnull |
| selection | 下記の選定情報 |
| thumbnail | 下記の画像情報 |

### titleCandidates

`candidates: [{id, title, intent}]`、`selectedId`、`recommendedId`、`intent`。
`intent`は選択した候補の値（`factual` / `engagement` / `concise`など）。
候補が無い場合は`candidates: []`、IDやintentが無い場合はnull。
字幕・プロンプト・候補の根拠全文は含めない。

### source

`title`、`url`、`start`、`end`。titleとurlはjob.settings_jsonの`youtubeSourceTitle`と`youtubeSourceUrl`だけから取得。
アップロードのファイル名をタイトルとして代用しない。start/endは元動画の絶対秒。
URLはHTTP(S)のみ。認証情報があるURLは出力せず、フラグメントとクエリを除去する（動画識別用の`v`だけ保持）。

### selection

`candidateId`、`reason`、`selectionReason`、`longformReason`、`topicKey`、`momentKey`、
`score`、`finalScore`、`ruleScore`、`aiScore`、`openingScore`、`parentStart`、`parentEnd`。
確定した書き出しメタデータとselected_clips.jsonにある値のみを使う。追加採点はしない。

`parentRangeAdjustments`はジョブの初期選定・最新再選定の要約に残る補正履歴。
候補のproposalIdは後段のcandidateIdと同一ではなく、候補ごとの対応が保存されていないため、
`parentRangeAdjustmentsScope: "job"`を明示する。特定の候補への補正と断定しない。
各履歴は`proposalId`、`reason: "parent_ratio_adjusted"`、`originalParentStart/End`、`originalRatio`、
`adjustedParentStart/End`、`adjustedRatio`、`sourceLimited`。

### thumbnail

`source: "video_frame" | "character_asset" | "unknown"`、`mode`、`frameSeconds`（本編内秒）、
`assetId`、`emotion`、`reason`、`emotionSelectionSource`。
旧方式の動画コマもvideo_frameとして記録する。画像ファイルのパスや画像自体は含めない。

### performanceHints（統合④、task-217）

各項目は`analysisId`（分析ID）、`generatedAt`（分析の生成完了日時、UTC）、`expiresAt`（利用時の保持期限）、
`target: selection | title_hook`、`text`（実際に入力したヒントの文）、`format: normal | short`。
旧記録の項目欠落は空配列として扱う。未使用時は書き出さない。schemaVersionは1のまま。
日時はUTCのISO 8601。選定サマリーと当該clipのタイトル/フック入力記録から、同形式の項目だけを投影する。
選定側はジョブの初期選定・再選定で使用した参考情報の履歴であり、個別clipへの因果効果を示さない。
YouTubeの生の統計・動画タイトル・絶対パスは含めない。記録は制作時点の参照履歴なので、後にヒントが期限切れになっても消さない。

## 含めない情報

明示したフィールドだけを書き出す。settings_jsonや書き出しメタデータの丸ごとのコピーは行わない。
ファイルの絶対パス、字幕全文、認証情報、ユーザーの連絡先・アカウント設定などの個人情報は含めない。
公開用タイトル、キャラ名、話題や選定理由など、この契約に明記した制作上の文言は記録する。

## 既存分のbackfill

backendで実行する。DB・動画・ジョブの出力ファイルは変更しない。

```bash
python -m app.maintenance backfill-production-records --dry-run
python -m app.maintenance backfill-production-records --execute
# 既存記録も現在のメタデータで更新し、revisionを増やす
python -m app.maintenance backfill-production-records --execute --force
```

指定なしもdry-run。対象はDBでcompletedのジョブのExportItem。
dry-runは読み取り・形式検証だけを行い、ディレクトリも記録も作らない。
既存ファイルは`--force`なしではスキップする。force更新もcreatedAtは対象のExportItem.created_atとし、revisionは+1。
結果は`eligible`（作成・更新の対象数）、`written`、`skipped`、`targets`（ExportItemのID）、`errors`をJSONで返す。
一部が失敗しても残りを処理し、errorsがあれば終了コード1。エラーにはIDと例外の種類だけを含める。
実際の書き込みはストレージの変更ロック内で行い、既存ファイルの有無を取り直してから原子的に保存する。
