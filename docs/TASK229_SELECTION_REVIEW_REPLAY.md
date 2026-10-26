# task-229: 選定品質の記録と字幕確認への注意の引き継ぎ

## 原因と変更

- `codex_initial_selection.convert_codex_initial_selection_response` は提案の契約・範囲・尺を検証した候補プールを作る。音声条件を使う最終選定は `clip_plan_runner._codex_selection_with_diverse_refined_shorts`（初期選定と再選定で共有）が担当する。
- この最終選定では、通常候補だけが `select_candidates` の `evaluate_hard_gate` を通り、ショートは境界補正後に直接 `select_diverse_shorts` へ進んでいた。そのためショートの `hard_gate_passed` が None のまま保存された。
- 境界補正後、多様性検査・本数割り当て前に、両形式の候補へ既存の必須条件検査を実行する。音声条件・文章の途切れ・モデル拒否などの規則は変えず、合否と測定値・理由を `hard_gate_evidence` に保存する。検査に落ちた新しい候補は採用せず、rejectedCandidates に理由を残す。実行不能も `hard_gate_evaluation_failed` と例外の型だけを記録し、合格扱いにしない。
- 本数割り当ては合格候補の検査記録を保持する。再選定のキープ候補も、古い未記録や変更前の判定を使わず、現在の範囲を再検査する。キープの内容自体は消さず、不合格なら品質チェックに残す。
- `auto-subtitle-only-v2` に限り、字幕・事実の注意だけが残った選定は `outcome=unknown` のまま `route=subtitle_review` とする。`reviewPolicy` と検査結果から保存時・読込時にも経路を検証する。
- 認識する注意は明示的な許可リスト: `historical_claims_require_review`、`proper_noun_caption_review`、`factual_claims_require_review`、`transcript_accuracy_review`、`subtitle_accuracy_review`。未知の印・範囲や場面選定の印を文字列の部分一致で通さない。混在時・尺/範囲/重複の不合格は従来の切り抜き確認で止まる。
- 必須条件検査が未記録のまま残る、品質判定が実行できない、判定を保存できない場合、新autoは `unknown/failed` として処理を止める。人に検査の代行を求めない。旧auto/guarded/shadowの経路は維持する。

## コピーした保存データでの再判定

対象: `job_e4b373773ab04ed48da1f67479faf486`。元動画長 6189.066667秒、選定済み5本（通常4・ショート1）。

| 確認 | 変更前の保存記録 | 修正後のコピー検証 |
|---|---|---|
| ショート `cand_short_1489420_1523480_8c1944638e` の必須条件 | 未記録 | 実検査で合格、測定値を記録 |
| 選定済み候補の必須条件 | 通常4本のみ合格記録 | 5本とも合格 |
| 品質判定 | unknown / clip_review | unknown / subtitle_review |
| 注意の件数 | 歴史2・固有名詞1 | 同じ3件を保持 |
| ワーカーの遷移 | awaiting_clip_review で停止 | selecting_clips → preparing_subtitle_review → awaiting_subtitle_review |
| 字幕確認API | 本番では未作成 | 隔離したAPIで200、5本中3本にselectionWarnings |

注意の対象（元動画内の秒）:

| clip | 範囲 | 注意 |
|---|---|---|
| cand_normal_1613200_1727040_d8e01d2849 | 1611.04–1727.04 | 歴史上の事実・年代と音声/字幕の確認 |
| cand_normal_4871000_5068680_34b8fb0325 | 4871.00–5068.68 | 人名・地名・作品名などの表記と音声の確認 |
| cand_normal_2592040_2771800_9d526b074d | 2592.04–2771.80 | 歴史上の事実・年代と音声/字幕の確認 |

選定AIの保存応答はclip単位の印のみで、印ごとの字幕行を特定していない。行との対応を推測せず、画面で「AIは注意が必要な字幕行を特定していません」と明記し、該当clip全体の範囲・具体的な確認内容を表示する。範囲のクリックは既存の字幕シークへつなぐ。新しい確認操作や確定の制限は加えない。

## 検証の範囲

- 稼働出力から選定・計画・文字起こし・無音区間等のJSON 7ファイルを `.codex_tmp/qa` へコピー。元ファイルのSHA-256が全7件、検証前後で一致。
- コピーの必須条件再検査と品質再判定を実行。加えて隔離DB/storageのワーカー統合テストで、保存済み候補/字幕/無音区間を入力に、実際の品質判定と字幕確認APIまで通した。元の選定範囲の再判定なので、境界の再補正は無効。Codex・動画の描画はテストの代替処理を使い、実動画の再処理は行っていない。
- フロントエンドは40本のテスト、lint/typecheck/build。表示はコピー由来の注意データを同じReact部品に渡した隔離ページでも確認。時刻・注意文の表示、注意がないclipの非表示、既存のシークへの接続をテスト。
- 稼働ジョブの状態・字幕・動画・DBは変更していない。Docker反映、実Codexの再実行、稼働画面でのユーザー受入は未実施。
- launcher/プロンプト/依存lockは変更していない。Codex中継の再起動は不要。
