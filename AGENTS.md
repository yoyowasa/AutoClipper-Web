# AutoClipper Web Agent Rules

## Workspace Purpose

この workspace は AutoClipper Web の開発用。
長尺動画から通常切り抜きと縦型ショートを自動生成し、字幕焼き込み済み MP4 と ZIP を出力する Web アプリを作る。

## Edit Scope

- 編集可能: `C:\BOT\AutoClipper Web` 配下のみ。
- 他 workspace は編集禁止。
- 想定外のパス、別 repo、別 workspace に移動した場合は停止する。

## Product Goal

v1 で実現すること:

- ブラウザから動画をアップロードする。
- 設定を選ぶ。
- バックグラウンドジョブで処理する。
- ジョブ進捗を見られる。
- 通常切り抜きとショートを複数本生成する。
- 字幕焼き込み済み MP4 を確認できる。
- ZIP で一括ダウンロードできる。

## Out of Scope for v1

- 手動トリミング
- タイムラインエディタ
- approve/reject ワークフロー
- 認証
- 課金
- SNS 自動投稿
- マルチユーザー権限

## Architecture

- Frontend: Next.js + TypeScript + Tailwind CSS
- Backend: FastAPI + SQLite
- Worker: RQ + Redis
- Video processing: FFmpeg / ffprobe
- Transcription: faster-whisper first, OpenAI transcription optional
- AI scoring: OpenAI API Structured Outputs

## Code Rules

- モジュールを小さく保つ。
- Backend schema は Pydantic model を使う。
- Frontend API 型は backend schema と一致させる。
- storage path を散在させない。
- HTTP request 内で長時間の動画処理を実行しない。
- 動画処理は background job に限定する。
- 実動画処理を追加する前に、ダミージョブの E2E 導線を完成させる。

## Testing Rules

変更時は関連する最小検証を行う。
PR 単位では次を通す:

- backend tests
- backend ruff
- frontend typecheck
- frontend lint
- frontend build
- docker compose 起動確認

## CI Rules

- CI は `.github/workflows/ci.yml` を使う。
- backend CI: `ruff check .` と `pytest`。
- frontend CI: `npm run lint`、`npm run typecheck`、`npm run build`。
- CI が落ちた場合は、原因を確認してCIが通るまで最小修正する。

## Codex Operation Rules

- 1 task = 1 PR。
- 1 PR に複数機能を混ぜない。
- branch name は `codex/task-XX-short-name` 形式を使う。
- public API contract はタスクで明示されない限り壊さない。
- manual review、timeline editor、approve/reject workflow は v1 に入れない。
- storage path や設定値を各所にハードコードしない。
- PR 報告では変更ファイル、実行コマンド、検証結果、制限事項を明記する。

## STATUS.md Rules

- 置き場所: `C:\BOT\AutoClipper Web\STATUS.md`
- 変更時は必ず `STATUS.md` を更新する。
- 記述粒度: タスク単位で、目的・変更ファイル・検証結果・未解決事項を残す。
- 追記形式: 新しい作業を `## YYYY-MM-DD ...` 見出しで追記する。
- 禁止事項:
  - 根拠なしに完了扱いしない。
  - 検証していない項目を成功と書かない。
  - 秘密情報、API key、個人情報を書かない。
  - 詳細すぎる一時ログを貼らない。
