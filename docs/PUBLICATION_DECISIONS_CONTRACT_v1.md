# 投稿可否の判定・見送り記録 v1（task-237）

確認日: 2026-10-31 JST。残り作業5／到達仕様§3.3-2のうち、既存の字幕・採点等による見送りだけを扱う。
新しい映像・音声の意味理解、自動投稿、投稿成績の因果判定は追加しない。実素材での受入と閾値の妥当性は未確認。

## 適用と基準

- ジョブ作成時に、サーバーが自動ワークフローのsettingsへ `_publicationPolicy` を固定する。
  外部からこの内部キーを指定して基準を迂回できない。手動ワークフローには付けない。
  既存ジョブの読み込み・retry・再選定で新たに付与しない。手動の時刻指定・キープ・人の範囲調整は自動見送りの対象外。
- 基準は [PublicationPolicy](../backend/app/publication/models.py) に集約する。
  `version=weak-material-v1`、`minScore=65`、`minCharactersPerSecond=0.5`、`validated=false`。
  **未検証の運用基準**であり、投稿成績から得た最適値ではない。自動の方針更新の許可リストには追加しない。
- 尺は本編の秒数。字幕をNFKC正規化した英数字・文字の数を尺で割る。
  意味の深さそのものを測った値ではなく、低密度を検出する補助値である。
  採点はfinal_score、ai_score、rule_scoreの順で既存の有限値を使い、欠損を0にしない。
- 既存の尺・範囲・重複・不採用理由・必須条件検査・配分の**後**に、選ばれた候補を1回判定する。
  弱い候補を外した後に再配分・補充はしない。候補プール全件を再採用する機能ではない。
  既存の点数だけによる除外で全件0になった場合は、要求本数以内の候補を見送りの根拠として記録できる。
  低確信度のCodex提案も、範囲・字幕根拠の検証を通ったものだけ内部に保持する。選定結果へは採用しない。

## 3つの結果

| decision | 意味と条件 |
|---|---|
| publish | 既存検査・必要な根拠があり、上の基準を満たす。後段の内容・完成検査も引き続き必要。 |
| skip | 根拠があり、点数・字幕密度が基準未満、または既存のモデル／品質点の判定で不採用。 |
| unknown | 点数・字幕・選定理由・検査記録が無い、検査不能、または尺・範囲などの条件に合わない。投稿とも見送りとも扱わない。 |

- `model_rejected` だけの検査結果は弱さの根拠としてskipにできるが、無音・発話不足・不完全な境界等も含む場合はunknown。
  失敗した必須条件を合格へ変更するものではない。
- 期限内の既存制作ヒントがあれば、分析ID・生成／失効日時だけを参考根拠に残す。
  ヒントで閾値や必須条件を上書きしない。未取得の30日成績やヒントを推定せず、期限切れは使わない。
- unknownを含む場合は切り抜き確認へ止め、理由を表示する。自動でpublish／skipに寄せない。
- 一部skipなら投稿予定分だけ進み、「素材が弱いためN本」と理由を表示する。最低本数も強制しない。
  固定本数の品質ゲートでは、今回実際に外した分だけ不足の内訳に記録する。他の検査・既存の不足は免除しない。
- 全件skipなら、既存のstatus=completedに `outcome=no_publication` を添えて「投稿なし（見送り）」として終了する。
  ExportItem・MP4・字幕確認・ZIPは作らない。候補自体が無い場合や、根拠の無い0件をこの状態に置き換えない。

## 記録と保存期間

[paths.py](../backend/app/storage/paths.py) の `publication_decisions(job_id)` から、
`storage/production_records/publication_decisions/<job_id>.json` に `write_json_atomic` で保存する。
完成物0本にはexport_idが存在しないため、動画ごとの制作記録とは別の小さなジョブ単位の記録を既存保存領域に置く。
`production_catalog` が読む直下の `<export_id>.json` と混同せず、偽の動画記録や台帳を作らない。

- schemaVersion=1、jobId、revision、createdAt／updatedAt、policy、outcome、selectedCount。
- decisions: candidateId、type、元動画内のstart/end、候補タイトル、decision、source、policyVersion、理由コード、evidence、originalDecision。
- evidence: 点数・採点元、選定理由、必須条件の結果・理由・ハッシュ、字幕の文字数・密度・ハッシュ、期限内ヒント参照。
  字幕全文、ファイルパス、秘密情報は含めない。
- 再選定・手動採用時はrevisionを増やし、previousDecisionsに以前のrevisionと判断・根拠を残す。
- choiceHistoryの `kind=publication_decision`／`stage=applied` に、結果・理由コード・根拠ハッシュ・元の結果と出所を残す。
  値は `publicationDecision / publicationReasons / publicationEvidenceHash / publicationOriginalDecision` とtype/start/end。
  実際の完成物の `kind=publication` と区別する。見送りから出版成績を作ったり、0再生として評価したりしない。
- 投稿予定の完成動画では、制作記録schemaVersion=1の任意項目 `publicationDecision` とchoiceHistoryへ転記する。
  candidateId・形式・範囲が一致する場合だけ転記し、後の変更に古い判断を流用しない。旧記録に推定で補わない。
- ジョブ出力・保存期限による掃除と明示的ジョブ削除では、この小さな永続記録を消さない。
  再選定／範囲更新の失敗時は、既存の復旧処理で前の記録と選定を保持する。

## 画面と人による採用

処理状況・切り抜き確認・結果画面でskip／unknownと理由を表示する。内部IDではなく候補タイトル・種類・時刻を表示する。
投稿なしでは空のZIPや完成動画へのリンクを出さず、見送り候補の確認へ移動できる。

既存の範囲更新APIとRQ仕事を再利用し、「キープして採用」は現在の範囲を保存する。
範囲を変更して保存しても採用へ戻せる。再選定でキープした候補も人の判断として扱う。
`source=manual`、`originalDecision=skip/unknown` と元の根拠を残す。
モデルの不採用票を人の採用票へ置き換えるが、尺・範囲・字幕・無音等の物理／内容の必須検査はやり直す。

採用へ戻す処理はHTTP中に動画を作らずRQへ送り、既存の軽量プレビューを作る。
キュー登録／workerが失敗した場合は未採用の選定・記録を保持する。
未採用の候補をapproveのkeptClipIdsだけに入れた要求は422とし、先に採用／範囲保存を案内する。
全件見送りの終了後も、採用へ戻す操作を残す。採用0本のまま字幕確認へは進めない。

## 検証範囲

閾値・欠損、配分後の無補充、全件見送り／判定不能、低確信度の実変換経路、人の復元と失敗復旧、
制作記録・過去の判断・削除後の保持を合成入力と隔離DBでテストする。
隔離API／Next.js画面で表示と採用導線を確認する。稼働DB・既存ジョブは変更しない。
新しいCodex依頼・プロンプト・スキーマ指紋・launcherは変更しないため、本タスクによる中継再起動は不要。
実素材での見送りの適切さと投稿成績への影響は未確認。マージ・Docker反映とは別に受入を行う。
