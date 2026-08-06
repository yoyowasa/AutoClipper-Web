# Design QA: Task 103 TOP画面の情報整理

## 基準

- 参照デザイン: `C:\Users\peace.YAGURUMAGIKUHM\Pictures\Screenshots\スクリーンショット 2026-08-04 004821.png`
- 注釈前: `storage/temp/design-qa/task103-top-before-1821x1272.png`
- 実装: `http://localhost:3000/upload`
- 対象状態: 新規作成、動画未選択、折りたたみ初期状態
- 比較画像: `storage/temp/design-qa/task103-comparison-final.png`
- Before / After: `storage/temp/design-qa/task103-before-after.png`
- 実装画像: `storage/temp/design-qa/task103-top-after-1920x957-top.png`、`task103-top-after-1821x1272.png`、`task103-top-after-1280x767.png`、`task103-top-after-mobile-390x844.png`

参照画面は機能・文言の複製対象ではない。余白、罫線、情報密度、固定操作領域をTOPへ適用した。左の動画・JSON入力と字幕スタイル本体は変更対象外とした。

## 注釈への対応

- 手動の時間指定: 初期状態を閉じ、`自動選定 / 時間指定中`だけを表示。入力stateは展開中も保持。
- 右側要約: 入力・本数・工程の重複表示を削除。固有操作だった開始ボタンは生成設定下の固定操作バーへ移動。
- Short layout: `ショート画面`へ日本語化し、冒頭タイトル・字幕焼き込みと横一列へ集約。
- 左の入力動画・人気区間JSON: 構成と機能を維持。
- 4工程カード: 削除。実際の確認設定だけを`開始後の確認（必要な場合だけ）`へ格納。
- Short overlay title: `ショート冒頭タイトル`へ日本語化し、全幅単独配置を廃止。
- 字幕スタイル: `SubtitleStyleEditor`本体は未変更。

## 確認結果

- `1920x957`: `入力 340px / 設定 1547px`。開始操作バーをviewport下端に常時表示。
- `1821x1272`: document横overflow `0`。手動時間・確認設定は閉じ、字幕スタイル上端まで表示。
- `1280x767`: `入力 340px / 設定 907px`。横overflow `0`、開始操作を初期画面内に表示。
- `390x844`: 1列化、横overflowなし。モバイル用開始ボタンを上部に表示。
- desktop / mobileとも、実表示されるsubmitは`1`。
- 折りたたみ: 手動時間と確認設定の開閉を確認。手動時間の検証失敗時は自動展開し、最初の不足欄へfocus。
- 確認工程: 閉じたsummaryに`予定確認 + 字幕確認 / なし`の現在値を表示。
- 選択操作: ショート画面`auto → center_crop → auto`、冒頭タイトル`auto → always → auto`を確認。
- mode切替: 新規作成 / 完成動画再編集、見出し、JSON表示、CTA文言の連動を確認。
- 表記・密度: 処理モードと動画タイプを日本語化し、本数2項目をdesktopで全幅使用。
- 単一出力: `通常のみ`は本数欄`1409px`・見出し`字幕`、`ショートのみ`は本数欄`1409px`・ショート設定表示を確認。
- Browser console: error `0`、warning `0`。
- 参照画像と実装画像を同一比較画像で確認。P0 / P1 / P2相当の表示崩れなし。
- 独立再レビュー: P0 / P1 / P2 / P3なし。

## 未確定

- 実動画を選択してjobを作成するE2Eは未実行。
- デザインのユーザー受入は未確認。

final result: passed

# Design QA: Task 104 切り抜き予定画面の重複整理

## 基準

- 参照: このturnのBrowser Comment 1〜4に添付された`1821x1272`の切り抜き予定画面。
- 実装: `http://localhost:3000/jobs/job_46dcde5c8b1a40f1af54029fab4d0ea3/clips`
- 対象状態: Short 1選択、元動画`15:04.9 - 15:47.5`。
- 実装画像: `.codex_tmp/task104-clip-review-after-1821x1272.png`
- 今回は既存の全幅3列レイアウトを維持し、注釈4点に限定して比較した。

## 注釈への対応

- 中央上部の選択clipメタ情報: 左一覧との重複を削除し、進捗表示の直下から動画を表示。
- 左clip一覧の時刻: 5件すべてへ`元動画`を追加。
- Short 1の誤字: `その能面にしとったっちゃん`へ補正。
- 誤字原因: raw ASRへ混入したArabic文字を確認し、既知補正・想定外script guard・既存plan読込の冪等補正を追加。

## 確認結果

- 全体: 左clip一覧 / 中央動画・編集 / 右文字起こしの3列と外周余白を維持。
- 中央: 重複行の削除後も動画、開始・終了調整、冒頭への見せ場複製を同じ順序で表示。
- 左一覧: 通常2件・ショート3件の種別、タイトル、元動画時刻、選択状態を確認。
- 右一覧: Short 1選択に連動し、対象文字起こし区間も`その能面にしとったっちゃん`を表示。
- レイアウト: viewport`1821x1272`、document client width / scroll width=`1806 / 1806`、横overflowなし。
- タイポグラフィ・色・罫線: 既存の日本語UIフォント、文字サイズ、neutral系罫線、選択色を維持。
- 操作: 通常1からShort 1へ切替。動画、時間調整、見せ場複製、文字起こしの連動を確認。
- API: clip planと対象文字起こし区間にArabic文字なし。
- 既存成果物補正: ユーザー辞書を再適用せず、既知誤認識だけを冪等補正。
- Browser console: error `0`、warning `0`。開発用info / HMR logのみ。
- Next.js error overlayなし。P0 / P1相当の表示崩れ・機能回帰なし。

## 比較履歴

1. 注釈前: 中央と左でメタ情報重複、左時刻の基準不明、Short 1タイトルへ`農من`混入。
2. 実装後: 中央重複を削除、左時刻へ`元動画`、タイトルと文字起こしを`能面`へ補正。
3. 最終確認: Short 1選択状態で全体表示、横overflow、操作連動、API、browser logを再確認。

## 未確定

- 許可済み実動画を再文字起こしするE2Eは未実行。
- ユーザー受入は未確認。

final result: passed

---

# Design QA: Task 105 切り抜き調整パネルの縦幅圧縮

## 基準

- 参照: このturnのBrowser Comment 1〜2に添付された`1821x1272`の切り抜き予定画面。
- 実装: `http://localhost:3000/jobs/job_46dcde5c8b1a40f1af54029fab4d0ea3/clips`
- 対象状態: Short 1選択、scroll top、見せ場未設定。
- 注釈前: `.codex_tmp/task105-before-1821x1272.png`
- 実装後: `.codex_tmp/task105-final-approved-1821x1272.png`
- 全体比較: `.codex_tmp/task105-before-after-final-1821x1272.png`
- panel拡大比較: `.codex_tmp/task105-panels-before-after-final.png`
- 参照・実装とも同じCSS viewport`1821x1272`、DPR`1.5`。保存画像は同じbrowser content領域`1806x1261`で、再拡大せず比較した。

## 注釈への対応

- 開始・終了調整: panel余白、入力間隔、下部要約を圧縮し、見出しと説明を横並び可能にした。
- 冒頭への見せ場複製: 同じ密度へ揃え、入力、要約、追加ボタンまで初期表示内へ収めた。
- 字幕部分、動画、左clip一覧、右文字起こし、配置順は維持した。
- 見せ場複製の圧縮は切り抜き予定画面の`compact`表示だけに限定し、字幕画面の既定表示は変えていない。

## 寸法比較

- 開始・終了調整: `289.3px -> 217.3px`、`72.0px`削減。
- 見せ場複製: `325.3px -> 234.7px`、`90.7px`削減。
- 両panel合計: `614.7px -> 452.0px`、`162.7px`削減。
- 最終下端: 見せ場複製`1256.0px`、追加ボタン`1227.3px`。viewport下端まで`16.0px`。
- 横overflow: `0`。

## 確認結果

- 全体比較: 注釈前は見せ場複製の入力・追加ボタンがfold下、実装後はpanel全体が初期表示内。
- panel比較: 入力値・ボタン・補助文を削除せず、縦余白と改行だけを削減。
- タイポグラフィ: 文字サイズとweightは維持。説明・要約のline-heightだけ圧縮。
- 操作サイズ: 微調整ボタンは最小`32px`、入力と主要操作は`36px`を維持。
- 色・罫線・動画: 既存tokenと構成を維持。比較時の動画フレーム差はmedia decode状態によるもので、layout寸法は同じ。
- 操作: `前に+5秒 -> 自動選定の範囲へ戻す`、`ここから3秒 -> ここから2秒`でstate更新と復帰を確認。保存は実行していない。
- `1280x720`: 両panelと追加ボタンをDOM確認。document横overflow`0`。
- Browser console: error`0`、warning`0`。Next.js error overlayなし。

## 比較履歴

1. 注釈前: panel合計`614.7px`、見せ場複製下端`1418.6px`で初期表示から約`147px`超過。
2. 圧縮案: 見出し・説明、入力、要約の密度を調整し、共有componentは切り抜き予定画面だけ圧縮。
3. 最終確認: panel合計`162.7px`削減、見せ場複製全体と追加ボタンを初期表示内で確認。

## 未確定

- 上限超過警告・入力エラーなど、通常初期状態にない追加文言の表示時は縦スクロールが発生し得る。
- ユーザー受入は未確認。

final result: passed
