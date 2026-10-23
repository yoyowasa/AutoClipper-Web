# 残り作業1-E：自動選択から投稿セットまでの受入記録

実施日: 2026-10-23 JST / task-225。基準: main `29e4a67`（1-D／PR #158のmerge commit）。

## 判定

**隔離した結合テストと画面操作を確認。実動画の完成MP4を人が見る受入は未完了。**
既存のAPI・描画・記録・保存を接続して照合し、今回アプリ本体の修正が必要な不一致は見つからなかった。
新しい画面・生成器・キュー・台帳は追加していない。確認用テストと本記録を追加する。

追加の動的演出は承認済みの範囲に従い「なし」と記録する。動的演出の選択、残り作業4の自動検査・修復、
実動画の品質、投稿成績の改善を完了扱いにはしない。残り作業1全体の完全完了も宣言しない。

## 検証環境と限界

- Python 3.11、lock版Ruff 0.16.10、pytestの専用DB/storage。稼働DBや既存ジョブは変更しない。
- 新しい結合テストでは、通常とショートをそれぞれアップロードAPIから作成。選定範囲はテストで明示し、
  自動推薦の生成応答・文字起こし・FFmpeg実行・RQ登録をテストダブルにする。
  API、状態遷移、字幕ASS生成、PILサムネ描画、制作記録、投稿文、ダウンロード、ZIPは実装をそのまま使用する。
  選定ゲートと実MP4を対象とする出力後ゲートはモック。確定時の内容・尺・プレビュー準備完了の検証は実処理。
- Codex選定成功／失敗の接続、品質ゲートのfail／unknownは既存の別テストで確認する。
  上の一本の結合テストを、実Codexによる場面選定や実MP4の画質検証とは扱わない。
- 画面: backend `127.0.0.1:18225`、Next.js `127.0.0.1:13225`、専用Redis接続先（実際のenqueueはテスト用実装）。
  DB/storageは `.codex_tmp/task225/ui/`。モデル応答・動画・フレームは試験用で、実サービスのCodex/Google/GPUは使わない。
  APIの接続先と、メディアプロキシの `BACKEND_INTERNAL_URL` の**両方**を隔離backendへ向ける。
- Dockerエンジンが停止中で、ローカルPATHと確認した既存配置にFFmpegが無いため、実エンコードは未確認。
  Dockerの起動・build・反映はしていない。稼働DBは検証前後とも3,289,088 bytes、
  更新時刻UTC `2026-10-22T03:06:46.5233849Z`で不変だった。

検証コマンド: backendからlock版`ruff check . ../launcher ../scripts`と`python -m pytest -q`、
repoルートから`npm --workspace frontend run test`／`lint`／`typecheck`／`build`。
結果: Ruff成功、Python 3.11は2178 passed／2 skipped／7 warnings、frontendは37テストファイルとlint・typecheck・build成功。
CIのPython 3.11／3.12・frontend結果はPRに記録する。

## 一本の流れで照合した内容

追加テスト: [test_auto_review_acceptance.py](../backend/tests/test_auto_review_acceptance.py)

| 段階 | 確認内容 |
| --- | --- |
| 自動推薦の適用 | 新規autoが推薦案を採用し、未確定の字幕確認で停止。入場だけでは正式プレビューも完成動画もenqueueしない |
| 人の修正 | 字幕、公開タイトル、動画内タイトル、投稿文、書式、ショートのフック区間・画角を1回のapplyにまとめる |
| 正式プレビュー | applyで1件だけenqueue。未完成のfinalizeは409で、重複enqueueしない。preview worker後はready |
| 明示的な最終確定 | finalize 202、render worker後completed。生成済みタイトル案の呼び直しはない |
| 完成物と記録 | 公開名・overlay・フック・本編尺／完成尺・実効文字スタイルと自動／手動の履歴を照合。通常は専用サムネ推薦copy_2と修正字幕由来の文言を記録 |
| 保存 | resultsの保存名と制作記録のpublicationTitleが一致。MP4・サムネ・投稿文の個別応答とContent-Dispositionを確認。サムネはPILで読み直せる |
| 投稿セット | manifestの3ファイルとZIP内の全ファイルをバイト単位で照合。一時ZIPが残らず、完成時のdownload.zipも作らない |

既存の通常タイトル末尾の規則も維持する。試験入力 `投稿用？:受入確認` は通常ではキャラ／所属末尾が付き、
ショートには付かない。ファイル名・制作記録では `:` が `：` になり、投稿文のタイトルは表示用の表記を保つ。
フック区間はAPIでは元動画時刻、制作記録ではclip内時刻。本編に2秒のフックを足した完成尺も照合した。

## 選択・記録・完成物の対応表

契約: [PRODUCTION_RECORD_CONTRACT_v1.md](PRODUCTION_RECORD_CONTRACT_v1.md)。
`choiceHistory` の `source/stage/inputRevision/policyVersion/reason` と候補・採用IDを利用し、別の台帳は作らない。

| 項目 | 候補・採用／不採用・手動変更の根拠 | 完成物との対応／取得できないもの |
| --- | --- | --- |
| 範囲 | `selected_clips`のselected/rejectedと理由、clip planのrange履歴。範囲変更・削除も既存保存時に記録 | source start/end、bodyDuration。選定器が出していない全探索候補・理由・判断主体は復元しない |
| タイトル・フック文言／映像 | 提案3案、推薦ID、適用ID、生成理由、手動applyの変更。新しい手書きタイトルに古い採用IDを付けない | publicationTitle、overlayTitle、hookText、clip内hookSceneStart/End、完成尺。履歴のtimeBasisを区別 |
| 投稿文 | 自動適用と手動変更、postMetadataSource、description/tags/hashtagsのハッシュ | metadata・投稿文ダウンロードと照合。制作記録へ全文を増やさず、全文が必要な投稿用ファイルは既存の保存経路 |
| サムネ | 3案・推薦／採用、手動文言、画像のvideo/asset/legacyと代替理由、テンプレ・文字書式・配置 | 完成JPEGとmetadata、thumbnail・choiceHistory。手動編集後の更新、失敗時の初期文言保持と警告も既存テストで確認 |
| 画角 | 要求layout、解決layout、実際のcrop情報、設定の層、手動値・fallback理由 | 1080×1920等の出力寸法、帯内の映像枠、offset/zoom。人物を検出した実映像の妥当性は今回未確認 |
| 文字スタイル | 人の指定を保持し、ASS生成時の実効fontSize・fit・位置・色・文字幅等を集約 | ブラウザの簡易計算・正式プレビューASS・完成ASS・記録を既存goldenで照合。実映像上の可読性は未確認 |
| 演出 | `effects / default / additional_effects_disabled_by_policy` | `additionalEffects=none`。追加の動的演出は作らず、実装済みと数えない |
| 公開／再書き出し | publishedの最終値、revision、previousRecordId | 投稿セットの名前と一致。再書き出しの連鎖・ジョブ削除後の履歴残存は既存テストで確認 |

全項目に架空の候補を補わない。候補集合が存在する文言／サムネ提案と、決定的な文字fit／画角の値を区別する。
旧記録にない理由・候補・方針版は `null`／空／`unrecorded` のまま。候補が残っているだけで、不採用理由が記録済みとはしない。

## 維持する経路の確認先

すべて今回の全件pytest／frontend testの対象。

| 条件 | 主な回帰テスト |
| --- | --- |
| auto通常／ショート、人の確認で停止、Codex選定の代替、失敗・不足 | `test_auto_human_review.py` |
| 手動ワークフロー、旧auto、retry・再実行で手動修正維持 | `test_manual_workflow.py`、`test_auto_human_review.py`、`test_guarded_quality_gate_integration.py` |
| 字幕の構成変更・一回確定・プレビュー待ち、戻る際の世代保護 | `test_single_confirm_review.py`、`test_return_to_clip_plan.py` |
| サムネの失敗／再試行・手動優先・旧ジョブ不変・予備素材 | `test_automatic_thumbnail_copy.py`、`test_thumbnail_character_assets.py` |
| らでん／宙科、文字fit、画角fallback | `test_render_decisions.py`、`renderTextDecisions.test.ts` |
| 履歴・旧データ・再書き出し・削除後の記録残存 | `test_production_choices.py`、`test_production_records.py` |
| downstreamの結び付け・独自集計・分析 | `test_production_links.py`、`test_production_performance.py`、`test_channel_analysis.py` |
| フロントの一括apply・422・下書き・他clip保持 | `subtitleReviewActions.test.ts`、`subtitleReviewDraftStorage.test.ts` |
| フォルダ保存・ZIP代替・同名上書き確認・旧ZIP | `postingSetSave.test.ts`、`test_upload_ready_downloads.py` |

## 画面操作の観測

隔離したショート1本で、公開タイトルと字幕を編集 → 再読み込み → 下書き復元 →「このショートを確定」
→「未保存0件」「確認済み」「正式プレビュー作成中」→ ready →「字幕を確定してレンダリング」→ completed
→ Resultsへ進んだ。結果には修正した公開タイトル、サムネ、投稿セット／個別保存、再編集の操作が残る。
記録したHTTPはapply 200が1回、finalize 202が1回、results 200。

タイトル案・推薦・選定理由・手動の表示は既存画面で確認できる。失敗／代替理由は
`TitleHookSuggestionPanel`、`ResultVideoCard`の既存エラー・warning／人物理由表示を利用するため、表示欄は追加しない。
自動文言の正しさ自体はモックでは受入できない。

「投稿セットを保存」のフォルダ選択待ちは、操作環境からネイティブダイアログを扱えず、実保存は未確認。
再読み込みで待機を終了した。フォルダ／ZIP分岐のコードテストとAPIの3ファイル保存は成功しても、
ブラウザで3ファイルを実際に保存したとは扱わない。

ローカル証跡（Git対象外）: `.codex_tmp/task225/ui/calls.json`、`results-ui.png`、各検証ログ。
試験用メディアのため、この画面キャプチャを完成動画の見た目の品質証拠には使わない。

## 未完了の受入と再開手順

1. ユーザーが指定した隔離実動画で、通常／ショート、らでん／宙科の人修正後の正式プレビューと完成MP4を確認する。
   人物・字幕の欠け、フックの継ぎ目、音声、サムネの文言・構図、再書き出しを含む。実Codexを使う場合は別途許可を得る。
2. 実ブラウザでフォルダを選び、3ファイルの保存・同名時の確認、ZIP代替を操作し、ファイルと制作記録を照合する。
3. 上記結果を見て1-Eの受入を判断する。現段階では1-Eは「隔離・モック確認済み／実動画のユーザー受入待ち」。

Docker反映、実ジョブの再試行・再適用、動的演出の追加は今回の対象外。
