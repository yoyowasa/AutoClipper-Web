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
- 書き出し確定時に作成し、完成後のサムネ再生成が成功したときも対象の1件を更新する。
  キューへの登録・生成失敗・古い要求の破棄では更新しない。記録失敗は動画やサムネの成功を取り消さず警告する。
  記録失敗からの復旧や過去分の現在状態への更新にはbackfillの`--force`を使える。

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
| choiceHistory | 任意の配列。下記の制作上の選択履歴。欠落した旧記録は空配列として読み、過去の判断を推定しない |
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

### choiceHistory（残り作業1-A、task-221）

既存の`selected_clips.json`・clip plan・字幕確認・タイトル／フック案・サムネ文言案・書き出しメタデータに
作業中の履歴を保持し、完成時にこの配列へ集約する。新しいDBや恒久ファイル群は作らない。
同じexportの更新と再書き出しでは前の制作記録の履歴を引き継ぎ、IDで重複を除く。
ジョブ出力を削除しても、候補の比較に必要な値は制作記録に残る。

| フィールド | 意味 |
| --- | --- |
| id | 履歴項目の識別子。候補IDとは別 |
| kind | `range` / `title_hook` / `thumbnail` / `framing` / `text_style` / `effects` / `post_copy` / `publication` |
| scope / clipId | `clip`は当該clip、`job`は選定全体など。対応を確認できない候補を個別clipの根拠と断定しない |
| stage | `proposed`は生成案、`applied`は保存した選択、`removed`は計画から外した候補、`published`は公開した成果物、`observed`は選択元が不明な保存値の観測 |
| source | `automatic` / `manual` / `preset` / `default` / `fallback` / `unrecorded`。確認できる呼び出し経路だけで記録する。手動操作からの生成要求と、生成された案の採用は別の履歴 |
| recordedAt / appliedAt | 観測時刻／実際に適用・公開した処理の時刻（UTC）。未記録の過去の適用時刻は補わない |
| inputRevision | 既存の入力ハッシュ・字幕根拠ハッシュ・計画revision・サムネrender revision等。形式はkindに依存 |
| policyVersion | 当該処理の固定の版識別子、または生成器の既存prompt version。記録の更新回数`revision`とは別。成績から自動更新しない |
| timeBasis | `source`は元動画内秒、`clip`は本編内秒。時刻値のない履歴では省略可 |
| reason | 記録された理由。nullまたは省略は「理由未記録」であり、成功・不採用理由を推測して補わない |
| candidates | `{id, values, outcome, reason}`。outcomeは`proposed` / `selected` / `not_selected` / `rejected`。生成しただけの案を不採用扱いにしない |
| selectedIds / recommendedId | 採用と推薦を別に記録する。字幕確認のtitle_hookのIDは公開タイトル候補のID。手書きや古い根拠に対応するIDを捏造しない |
| values | 種類・範囲・文言・尺・score・openingScore・話題・画像候補時刻／ID・素材／表情・画角・スタイル・サムネのtemplateDesignなど、コードで許可した比較用の値だけ。旧履歴にない値は未記録 |

字幕や範囲の変更後は根拠ハッシュが変わる。古い案は過去の履歴として保持するが、現在の字幕根拠と一致しない
タイトル候補は現在の選択履歴に結び付けない。状態／プレビュー更新だけでは同一の選択を繰り返し記録しない。
「切り抜き確認に戻る」で字幕確認データを破棄するときも、その履歴は既存の計画ファイルへ引き継ぐ。
範囲変更のバックグラウンド処理が準備中の間は適用済みとして記録しない。

投稿文には連絡先等が含まれ得るため、description・tags・hashtagsは比較用ハッシュと採用元を残し、本文を履歴に複製しない。
スタイルは許可したフォント名・サイズ・色・位置等だけを残し、任意の辞書やファイルパスを丸ごと複製しない。

描画時の記録（task-224、`existing-render-decisions-v1`）:

- `framing`: 指定された`shortLayout`と実際の`resolvedLayout`、`framingOffsetX/Y/Zoom`、`cropX/Y`、検出元・代替理由・試した方式、`outputSize`とバナーを除く`contentViewport`を記録する。通常は元の画角（`source`）。`settingSource`はclip上書き／ジョブ設定／既定を区別する。キャラ名だけから「プリセット由来」「人が変更した」と推定しない。手動操作の履歴は従来の`applied`に残る。
- `text_style`: `outputSize`と`renderedTextStyles`に、実際のASS生成で使った役割（title/hook/subtitle）、フォント・要求サイズ・縮小後の`effectiveFontSize`・色・縁取り・位置・許容幅・行数・収まり結果を保存する。同一の結果を`eventCount`でまとめ、字幕本文は複製しない。採用元の`source`は`segment_override` / `clip_override` / `job_settings` / `layout_settings`（従来の個別設定値と既定を解決したレイアウト）。履歴の`source=automatic`は既存の文字収まり計算を指し、手動のフォントや位置を自動で選び直した意味ではない。
- `effects`: `additionalEffects: "none"`を明示する。既存フック挿入と静的画角調整は別項目であり、動的演出選択を実装したことにはしない。
- 入力revisionはASS・区間・画角指定・出力サイズのハッシュ。旧記録への補完や既存ジョブの再適用は行わず、今後の書き出し／再書き出しに記録する。記録の失敗は警告に留め、動画の書き出しを失敗にしない。

`publication`はその版の完成物の値を示す。過去分のbackfillではstageを`observed`とし、appliedAtを補わない。
この観測を、当時の自動決定や適用時刻の証拠にはしない。

1-Aは既存経路で取得できる記録を追加する基盤。プリセット／既定値の詳細な由来、描画時の最終解決値、
後続1-B〜1-Dで追加する自動決定は各タスクで接続する。全選択の記録や成績による自動方針更新の完成を意味しない。

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
