# AutoClipper Web Agent Rules

## Workspace Purpose

この workspace は AutoClipper Web の開発用。
長尺動画から通常切り抜き・縦型ショートと投稿用ファイルを作り、自チャンネルの投稿実績を次の制作へつなぐローカル Web アプリを開発する。

## Source of Truth

- 現行仕様・到達仕様・残り作業の順序は [現行・到達仕様](docs/AUTOCLIPPER_CURRENT_AND_TARGET_SPEC_2026-09-25.md) を参照する。現在の実装はコードと照合し、長期目標を実装済みと扱わない。
- 個別の変更・検証・未確認事項は [STATUS.md](STATUS.md) と各機能の契約文書を確認する。過去の記録の「未マージ」「未反映」は記録時点の状態として読む。
- 残り作業1の分割案は [自動選択と記録のタスク案](docs/REMAINING_WORK_1_TASK_PLAN.md) に置く。案の記載だけをコード実装の許可と扱わない。
- 現行仕様・到達仕様の§3と統合構想は、ユーザーが変更を指示しない限り書き換えない。

## Edit Scope

- 編集可能: `C:\BOT\AutoClipper Web` 配下のみ。
- 他 workspace は編集禁止。
- 想定外のパス、別 repo、別 workspace に移動した場合は停止する。

## Current Product and Operation

現在の制作・分析機能として維持するもの:

- 動画アップロード、キャラ別プリセット、自動選定と手動範囲指定、バックグラウンド処理と進捗表示。
- 切り抜き確認での再選定・キープ・不採用理由・範囲／種類変更、字幕確認から戻る操作。
- 字幕・タイトル・フック・画角・文字スタイル・投稿文の下書き編集と、clipごとの一回確定。
- 字幕付きMP4・サムネ・投稿文の保存、投稿セット、要求時に作る全体ZIP。
- 制作記録、自チャンネルのYouTube接続・同期・分析、記録との結び付け、独自集計・制作ヒント・改善試験。

当面の運用と実装範囲:

- 字幕の最終修正は人が行い、YouTube投稿も当面手動。既存の修正・確認手段を自動化のために失わせない。
- 字幕修正以外の選択の全自動化は残り作業1。既存の自動化モードがあることを、当面の運用がすべて自動化済みである証拠にしない。
- 自動投稿はユーザー判断で保留中。アプリ独自のログイン・課金・マルチユーザー権限、汎用タイムライン編集は現在の実装対象に含めない。自チャンネル連携のOAuthと既存の字幕／範囲編集は維持する。
- 有料のOpenAI Platform API経路は追加しない。Codexによる選定・文言生成・分析は既存のChatGPTログインによる中継を使い、文字起こしや顔検出等のローカル処理は維持する。
- 残り作業1〜7の順序を守る。映像・元音声・画面内文字を合わせた場面選定と、意味・固有名詞を含む字幕の全面自動修正は実装時期未設定であり、別タスクに混ぜない。

## Architecture

- Frontend: Next.js + TypeScript + Tailwind CSS
- Backend: FastAPI + SQLAlchemy + SQLite
- Worker: RQ + Redis。切り抜き用workerとCPUのintelligence-workerを分離し、それぞれ設定されたキューだけを処理する。
- Video processing: FFmpeg / ffprobe
- Transcription: faster-whisper with local transcript post-processing
- AI: ホスト側Codex中継。通常依頼と自己分析のレーンを分離し、分析で制作操作を待たせない。

## Code Rules

- モジュールを小さく保つ。
- Backend schema は Pydantic model を使う。
- Frontend API 型は backend schema と一致させる。
- storage path は `backend/app/storage/paths.py` に集約し、JSONの原子的な保存には既存の `write_json_atomic` を使う。
- HTTP request 内で長時間の動画処理を実行しない。
- 動画処理、同期、Codex応答待ちは既存のバックグラウンド経路を使う。
- 既存の選定・生成・描画・記録・分析を優先して再利用する。同じ目的のモード・キュー・台帳・設定画面を、必要性の確認なしに増やさない。
- 旧設定・旧記録・RQの旧関数パス・再書き出しの復旧処理は、名称や現在の使用件数だけで削除しない。参照元、保存データ、失敗時の経路を確認する。
- 尺・品質・根拠の検証を弱めない。分析の欠損は0にせず、データ不足・効果未確認を区別する。
- `.env`・秘密情報ファイルの値を開く、表示する、ログや文書へ転記する操作はしない。必要な確認は存在・設定済みか否かに限る。

## Testing Rules

変更した挙動を検出できる関連テストを行い、コード変更のPRでは次を通す。タスクで指定された範囲・停止条件を優先する。

- backend: `backend` から `ruff check . ../launcher ../scripts` と `python -m pytest`。
- frontend: repoルートから `npm --workspace frontend run test`、`lint`、`typecheck`、`build`。
- 依存は既存のlockを使う。Ruffも `requirements-dev.lock` の版を使い、独自に更新しない。
- API・画面・コンテナ構成の変更は必要な起動／操作確認を行う。Compose検証は専用プロジェクト・ポート・DB・storageに隔離する。稼働環境の再build／再起動をテストの代わりに行わない。
- 文書だけの変更は差分・リンク・記述の根拠・変更禁止部分の不変を確認する。アプリ全件テストのローカル再実行やDocker再buildは不要だが、PRの既存CIは確認する。
- テストのDB/storageは `backend/tests/conftest.py` の隔離を維持する。独立スクリプトやTestClientでも、appのimport／lifespan開始前に接続先を確認し、稼働DBへ `init_db` を実行しない。
- 実データを使う更新検証はコピーDB・コピーした対象ファイルで行う。ローカル／モック／コピー環境／CI／稼働環境での結果を区別して報告する。

## CI Rules

- CI は `.github/workflows/ci.yml` を使う。
- backend CI: Python 3.11／3.12、依存lock再生成の差分確認、`ruff check . ../launcher ../scripts` と `pytest`。
- frontend CI: `npm --workspace frontend run lint`、`typecheck`、`test`、`build`。
- CI が落ちた場合は、原因を確認してCIが通るまで最小修正する。

## Codex Operation Rules

- 1 task = 1 PR。
- 1 PR に複数機能を混ぜない。
- branch name は `codex/task-XX-short-name` 形式を使う。
- 原則mainからブランチを作り、PRの比較先もmainとする。別タスクの未コミット変更を混ぜない。
- マージはmerge commit。rebase／squashやマージ時のブランチ削除は、ユーザーから別途指示がない限り行わない。
- PR作成とマージの許可を区別し、レビュー待ち・マージしないという停止条件を守る。計画確認だけの依頼でコード実装を始めない。
- public API contract はタスクで明示されない限り壊さない。
- storage path や設定値を各所にハードコードしない。
- PR 報告では変更ファイル、実行コマンド、検証結果、制限事項を明記する。

## Runtime Changes

- PRの作成・マージと、稼働環境への反映は別作業。反映、実ジョブの再試行、データ削除は指示された対象・範囲でのみ行う。
- 反映前には切り抜き用／分析用の両キューと実行中登録、DBの実行状態、Codex中継のrequests／processingを確認する。中断済みの孤立ジョブ等の例外はユーザーが指定したものに限る。
- DB変更・反映でバックアップが必要な場合はSQLiteのbackup()を使い、整合性と件数を確認する。タスクでバックアップ不要とされた場合はその指示に従う。
- launcherやCodex契約を変えた場合は、中継再起動の要否と対象をPR／STATUSへ書く。既存依頼種別への影響を確認する。
- GETでも状態更新やプレビュー再作成を行う経路があるため、稼働確認で無差別にジョブAPIを呼ばない。

## STATUS.md Rules

- 置き場所: `C:\BOT\AutoClipper Web\STATUS.md`
- 実装・設定・仕様・運用ルールの実質的な変更時に `STATUS.md` を更新する。変更を伴わない軽微な調査だけで履歴を増やさない。
- 記述粒度: タスク単位で、目的・変更ファイル・検証結果・未解決事項を残す。
- 追記形式: 新しい作業を `## YYYY-MM-DD ...` 見出しで追記する。
- 古い記録は `docs/status_archive/` へ月別に移す。
- 禁止事項:
  - 根拠なしに完了扱いしない。
  - 検証していない項目を成功と書かない。
  - 秘密情報、API key、個人情報を書かない。
  - 詳細すぎる一時ログを貼らない。
