# 制作記録とYouTube動画の結び付け（task-207）

設定画面の「YouTube連携」の下に「制作記録の結び付け」を表示する。
再生数・分析はここでは表示しない。Clip Intelligence側のコード・DBは変更せず、移行も行わない。

## 記録と照合

- `StoragePaths.production_records`にある既存のv1記録を読み、ファイル形式は変えない。
  ExportItemやJobの存在は必要ない。
- previousRecordIdをたどった最初のrecordIdをファミリーIDとし、その最初のcreatedAtを公開日時の比較に使う。
  同じファミリーの最新のrevisionへrecord_idを追従させる。
- タイトルはNFKC・前後空白の除去・連続空白の1個化だけを行う。曖昧検索や句読点の除去はしない。
- 自チャンネルの取得済み公開動画で、タイトルが一致し、published_atが最初のcreatedAt以降であり、
  ファミリー側・動画側のどちらも候補が1つの場合だけ自動で結ぶ。
- 記録の破損・祖先の欠落・循環・別jobへの参照・revisionの逆転・枝分かれは自動で選ばず、一覧に注意を出す。
  枝分かれしたファミリーの同名候補も他のファミリーとの曖昧性判定に含める。
- 再照合で自動の結び付きに複数候補や不一致が生じた場合は外す。
  manualとmanual_unlinkedの動画選択・モードは変更しない。最新のrecord_idへの追従だけは行う。

## DBと実行時点

`production_links`をcreate_allで追加する。record_family_idは主キー、youtube_video_idはnullableの一意制約と
youtube_videosへの外部キーを持つ。record_id、mode、linked_at、updated_atも保存する。
modeはauto/manual/manual_unlinked。解除は行を消さず、動画IDをNULL・modeをmanual_unlinkedにして残す。
ExportItem/Jobへの外部キーは無く、ジョブ削除・出力の掃除でも記録と結び付きを消さない。

同期のsuccess/partialのcommit後、制作記録の保存処理の後、実行したbackfillの後に照合する。
照合は独立したDBセッションとstorage_mutation_lock内でcommitする。
失敗時は例外の種類だけを警告し、同期成功・完成動画・保存済み記録を失敗へ戻さない。
手動操作も同じロックとDBの一意制約で保護し、他の記録に結び付いた動画の横取りは409にする。

## APIと操作

- GET `/api/intelligence/production-links`: 結び付き、未結び付けの記録/動画、件数、読込の問題。
  記録は必要な要約だけ返す。GETでは照合・保存しない。
- PUT `/api/intelligence/production-links/{record_family_id}`:
  `{"youtubeVideoId":"動画ID"}`で手動結合、`{"youtubeVideoId":null}`で手動解除。
  手動結合はタイトル・日時の自動条件を満たさなくても選べる。
- POST `/api/intelligence/production-links/reconcile`: 照合し直す。
- PUT/POSTのOrigin確認はtask-205と同じ。外部Originを拒否する。

YouTube側でタイトルを変えている場合は、未結び付けの記録から該当動画を選び「結ぶ」。
間違いは「結び付きを外す」で解除する。解除後は自動では戻らず、手動で結び直せる。
同期後に表示を更新する場合は「一覧を更新」。
