# AutoClipper × Clip Intelligence 構想 v0.1 既存仕様比較評価

評価日: 2026-09-21 JST

評価対象: `AutoClipper_ClipIntelligence_plan_v0.1 (1).md`（ユーザー提供ファイル）

対象 SHA-256: `3DB39E043A87963A924C67597A00AF389155FC91288DC7E3ADE74C2DDF8AD26C`

## 1. この文書の位置づけ

- 添付文書は実装指示ではなく、同文書自身が示す「v0.1／検討用まとめ」として評価した。
- 本評価ではコード、設定、DB、実行環境を変更していない。
- 2026-09-21のユーザー補足により、構想の最終目標は明確になった。**現行AutoClipperとClip Intelligenceを利用者から見て1つのツールへ統合し、動画アップロード後は人の通常操作なしで完成動画まで作り、完成物とその後の実績を蓄積して次回制作へ反映する**ことが目標である。
- したがって本評価は、2つの既存ツールを単に接続する案ではなく、AutoClipperを自律制作エンジン、Clip Intelligenceを分析・学習エンジンとして統合する製品構想の評価である。内部の責務境界は残しても、別々の利用フローを利用者へ要求しない。
- この目標は製品方向として本評価へ反映するが、添付構想をそのまま実装可能な詳細仕様へ昇格したわけではない。既存仕様との差、再利用できる現行機能、実装時に確定すべき契約を整理した。
- AutoClipper Web の仕様根拠は [AGENTS.md](../AGENTS.md)、[README.md](../README.md)、現行コードを優先した。[STATUS.md](../STATUS.md) は実施記録として使い、仕様正本や現在の実行成功の代わりにはしていない。
- Clip Intelligence は別 workspace の現行文書・コードを読み取り専用で確認した。変更は行っていない。

### 評価スナップショット

| 対象 | 確認状態 |
|---|---|
| AutoClipper Web | branch `codex/task-141-prompt-trial`、HEAD `bcb2d88d0b074e52f850bb72199ec7fb19b865e8` |
| AutoClipper Web working tree | 評価開始前から既存の未コミット変更・未追跡ファイルあり。本評価はそれらを変更・整理していない |
| Clip Intelligence | `C:\BOT\ClipIntelligence`、branch `main`、HEAD `e433f03dd9009e1ac6064c1f46ac4b04f5ddf405` |
| Clip Intelligence working tree | 既存の `STATUS.md` 変更とアイコン未追跡あり。本評価は変更していない |

## 2. 結論

**統合後の製品目標は妥当であり、AutoClipperの次段階の方向として採用を推奨する。ただし、現状の構想文だけを既存 v1 へ直接実装できる詳細仕様とは扱わない。**

判定は次のとおり。

| 判定対象 | 結果 |
|---|---|
| 統合製品の長期ビジョン | 採用を推奨 |
| 利用者から見た製品形態 | 1つのツール、1回のupload、1つのjob導線とする |
| 正常系の自動化目標 | 場面選定から完成物検査・保存まで人の操作なし |
| AutoClipper v1 への直接追加 | 現行v1の範囲を大きく超えるため、v2として段階導入する |
| 現行機能の再利用可能性 | 高い。制作工程の多くは既に存在する |
| AutoClipper と Clip Intelligence の内部接続仕様 | 実装設計としては未定義 |
| 映像・原音を含む素材理解 | 中核要件だが未達 |
| 完成物の独立した意味検査 | 未達 |
| 制作履歴からの自己改善 | 記録・比較の一部だけ存在。自動更新は未達 |
| OpenAI Pro中心の実装・運用 | 条件付きで可能。現行の直接API経路は別課金のため置換または無効化が必要 |
| この依頼での実装 | 行わない。評価と次段階の境界整理まで |

目標とする正常系は次の一続きの処理である。

1. 動画を1回アップロードする。
2. 映像、原音、文字起こし、場面変化を合わせて、通常切り抜きとshortの区間・構成を選ぶ。
3. 字幕を修正し、動画ごとにフォント、色、サイズ、位置、画角、タイトル、フック、サムネ文言を選び直す。
4. 決定的なrender処理で完成動画を作る。
5. 完成したpixel、音声、字幕、タイトル／フックの整合を別工程で再検査し、必要な工程だけ自動再実行する。
6. 合格した完成物と、使った判断・版・検査結果を永続化する。
7. 投稿後の実績が得られた場合はClip Intelligenceの公式統計と結び、次回の候補選定・構成・表現の提案または版付きルールへ反映する。

これは新規システムを一から作る計画ではない。既存AutoClipperの制作基盤を中核にして、次の3能力を追加する **v2級の統合ビジョン** と扱うのが適切である。

1. 字幕中心ではない映像・原音理解と編集判断。
2. 完成した映像・音声を対象とする独立した意味検査。
3. 制作判断・完成物・投稿実績を結ぶ永続履歴と、安全に次回へ反映する学習ループ。

利用者に2つのアプリを往復させる必要はない。一方、内部では「制作」「完成物検査」「履歴・分析」を分離し、1つのオーケストレーターと共通Production Recordで結ぶ方が、失敗時の再実行、版管理、rollbackを安全に行える。

## 3. 既存仕様の基準

### AutoClipper Web

[AGENTS.md](../AGENTS.md) の v1 目的は、動画アップロード、設定、バックグラウンド処理、進捗、通常切り抜きとショート、字幕焼き込み MP4、ZIP 出力である（16–24行）。認証、課金、SNS自動投稿等は対象外である（26–34行）。

[README.md](../README.md) も、長尺動画から文字起こし・候補選定・通常／ショート生成・MP4／ZIP返却を基本導線とする（9–20行）。一方、現行コードと [STATUS.md](../STATUS.md) には、初期仕様より後に追加された次の機能がある。

- `manual / shadow / guarded / auto` の自動化モード。
- clip plan、字幕確認、完成clip再編集。
- 公開タイトル、動画内タイトル、フック、説明欄、hashtags、tags、通常サムネ。
- selection／content／post-render の品質ゲート。
- staging、rollback、publication marker による不完全出力の非公開化。
- 元YouTube動画の完成済み区間を再利用しない永続台帳。

したがって、初期 v1 文書だけを現在の機能境界とみなすことも、最近の実装記録だけを将来仕様とみなすこともできない。**規範文書と現行実装の範囲がずれている**こと自体が、統合構想を採用する前の整理対象である。

### Clip Intelligence

現行 Clip Intelligence は、自チャンネルのYouTube公式統計を取得し、形式別・期間別・動画別の根拠から分析と次の検証案を保存する別アプリである。現行 README は「映像本編の解析は未接続」と明記している。

既存 Data Contract は、公開スナップショット、内部日次、欠損理由、`observed_at`、指標定義版、保持期限を分ける。改善記録は、変更点・比較元・次動画・主要指標を人が記録し、初期7日を比較する。因果効果は自動で断定しない。

一方、AutoClipper から制作判断や修正履歴を受け取る API、安定した制作版ID、外部投稿との接続 adapter は存在しない。`clips / clip_versions` は予約されているが、AutoClipper の job／export／artifact と結ぶ契約はない。

## 4. 構想と現行の対応表

| 構想の要求 | AutoClipper Web の現状 | Clip Intelligence の現状 | 評価 |
|---|---|---|---|
| 長尺投入、background job、通常／short出力 | 実装済み | 対象外 | 再利用する |
| 通常最長約10分 | `normalMaxDuration=600` を既に持つ | 対象外 | 整合 |
| 通常とshortを別構成で選ぶ | 別候補・別設定・別render・short画角を持つ | 形式別分析を持つ | 概ね整合 |
| 映像・原音を含む全体把握 | scene／audio特徴はあるが、Codex初期選定は transcript＋heatmap、`images=[]`。タイトル等は代表4frameと字幕で、原音は渡さない | 映像本編未接続 | 中核ギャップ |
| カット、間、字幕、画角、タイトル、フック、サムネ | 多くを編集・保存・render可能 | 次動画案は作るがrenderしない | AutoClipperを再利用 |
| AI意図を実行可能な編集データへ変換 | clip plan、subtitle review、selected clips、render metadata 等へ分散 | 制作データ契約なし | 単一の共通契約は未達 |
| 問題工程だけ再実行 | preview、字幕再render、サムネ再生成等は部分対応 | 保存済み統計から再分析可能 | 依存関係全体の再実行契約は未達 |
| 技術検査 | stream、尺、本数、ASS配置、geometry、artifact hash 等を検査 | データ整合・provenanceを検証 | 強い再利用候補 |
| 完成映像・原音の意味検査 | 独立したpixel／音声再検出は未接続。現行autoはASR confidence、Codex根拠、renderer geometry等の間接証拠 | 映像本編未接続 | 未達 |
| 不合格を完成扱いしない | fail／unknownを人へ戻し、不完全再renderを非公開にする仕組みあり | 部分失敗・欠損を0にしない | 方針は整合 |
| タイトル・フック・サムネ整合 | 生成・手修正・revision hash・字幕根拠ID・ZIP投稿artifactあり | 投稿後の数値分析あり | 接続IDがない |
| 人間の修正履歴 | 現在状態のartifactは保存するが、自己改善用の不変な変更event列はない | 改善案の採用と試行記録あり | 粒度とIDが不一致 |
| 投稿実績 | 投稿準備のみ。YouTube送信・投稿後metrics取得なし | Data/Analytics API、初期7日、流入元、維持率、改善追跡あり | Clip Intelligence側を正とする |
| 自己改善 | jobをまたぐ編集方針更新なし | 人の採用・比較はあるが、自動ルール更新はしない | 後段機能として妥当 |
| 利用量・費用管理 | 一部OpenAI経路はtokenを記録。Codex、GPU、再renderを含む完成品単位の総額／上限はない | Codex実行指定は保存するが制作費用管理ではない | 未達 |
| 外部公開権限の分離 | SNS自動投稿は対象外。投稿用copyとfile出力のみ | readonly YouTube接続 | 整合 |

## 5. そのまま再利用すべきもの

添付構想のために次を並行実装し直すべきではない。

1. upload、FastAPI job、RQ／Redis worker、進捗、MP4／ZIP返却。
2. transcript、scene、silence、audio feature、candidate、score、boundary refinement。
3. 通常／short別のrender、subtitle ASS、画角、帯、タイトル、フック。
4. clip plan と subtitle review のpreview、確認、再編集。
5. タイトル・説明欄・hashtags・tags・サムネ文言と投稿artifact。
6. automation manifest、3段階quality gate、staging／rollback／publication marker。
7. source time range の重複防止台帳。
8. Clip Intelligence のYouTube公式データ取得、欠損・出所・保持期限、初期7日比較、改善試行。

構想を採用する場合は、これらを「既にあるもの」として固定し、不足契約だけを追加する必要がある。

## 6. 主要な不一致と不足

### P0-1. 統合後の目標を仕様正本へ反映する必要がある

ユーザー補足により、「AutoClipperとClip Intelligenceを統合し、uploadから完成・蓄積・次回改善までを1つのツールで行う」という上位目標は確定した。一方、AutoClipper の AGENTS／README は初期 v1 の範囲を示し、現行実装はmanual review、auto mode、投稿artifactまで広がっている。実装へ進む際は、現行を壊さず統合目標へ移行できるよう、次の版関係を正本へ明示する必要がある。

具体例として、README のheatmap説明はJSON区間を候補seedにする記述を残す一方、2026-09-03の実施記録と現行のCodex選定は、JSONを人気度の参考に限定し、文字起こしと会話内容から区間を決める。今回の比較でも、READMEだけから現在動作を推定してはいけない状態を確認した。

- 現行を v1.x baseline として規範文書へ反映する。
- 統合後の自律制作・学習ループを v2 Vision とする。
- v2へ段階移行する間も、動作確認済みのv1契約を維持する。
- 一部機能を実験扱いとして正本から分離する。

本評価では、**添付構想を非規範の v2 Vision／RFC draft とする**案を推奨する。

### P0-2. 1製品として動かすための内部統合契約がない

これは製品目標が曖昧という意味ではない。利用者に見せるのは1つのupload／job／result導線でよい。ただし内部で、最低でも次の識別子と版を定義しないと、修正前後、完成物、投稿先、実績を安全に結べない。

- source asset ID と source time range。
- production job ID。
- clip ID。
- edit revision ID と親revision。
- render revision ID と完成artifact hash。
- publication record ID と外部YouTube video ID。
- 作成時刻、観測時刻、適用したmodel／prompt／rule／styleの版。

AutoClipper の `youtubeSourceUrl` は元配信を指し、生成した切り抜きの公開IDではないため代用できない。

### P0-3. 共通編集データが分散している

現行は `clip_plan.json`、`subtitle_review.json`、`selected_clips.json`、`automation_manifest.json`、render metadata、投稿package等がそれぞれ現在状態を保持する。これは現行UIと再renderには使えるが、添付構想が求める次の用途には不足する。

- 判断根拠から完成artifactまでの一貫したrevision追跡。
- 人間が何を、どの値からどの値へ、なぜ変更したかの履歴。
- 変更の影響工程だけを再実行する依存関係。
- Clip Intelligenceへ渡す安定したexport contract。

既存artifactを廃止する必要はない。上位の manifest／event 契約から既存artifactを参照する形が安全である。

### P0-4. 現行の保存期限では自己改善用履歴が消える

AutoClipper の terminal job は既定7日でcleanup対象となり、job、export、出力artifactが削除される。cleanup後も残す現行台帳は、元動画識別子と使用済み区間を中心とする `source_clip_usage` だけである。

投稿後7日以上の実績と編集revisionを比較するには、cleanup前に必要最小データを独立保存またはClip Intelligenceへ冪等に引き渡す必要がある。単にAutoClipperの保存期限を無制限に延ばす案は、容量・削除・YouTubeデータ保持条件を解決しない。

### P0-5. 映像・原音理解の入力契約と評価基準がない

添付構想の最大の差分は、字幕だけでは捉えられない無言場面、笑い、間、効果音、一瞬の出来事を選定・編集・検査へ使う点である。しかし、次が未定である。

- 全編を渡すのか、低負荷探索後の区間だけを渡すのか。
- frame rate、音声区間、timecode、最大長、再確認条件。
- 外部送信可能な素材、保存条件、権利、個人情報。
- 見逃し率、事実誤認率、カット境界誤差、必要な人修正量。
- 同じ生成modelで自己検査する場合の共通誤り対策。

モデル名を先に固定せず、共通の入出力contractと比較素材を先に決めるという添付方針は正しい。

### P0-6. 動画ごとのstyle選定は未実装

現行AutoClipperは、フォント、色、サイズ、位置、画角、帯などを設定・preset・renderへ反映できる。しかし、映像の配色、話者数、内容の調子、通常／shortの構成、字幕量を見て、動画ごとにstyleをAIが選び直す工程はない。

統合後は `Style Plan` を版付きの制作判断として持ち、少なくとも次を自動選定・検査対象にする必要がある。

- フォント、weight、文字サイズ、行数、位置。
- 文字色、縁取り、背景帯、映像とのcontrast。
- 通常／short別の画角、被写体位置、タイトル／フック配置。
- 人物・番組の固定brand条件と、動画ごとに変えてよい条件。
- 完成frameでの欠け、重なり、読みにくさ、内容とのtone不一致。

自由生成したCSS値をそのままrenderへ渡すのではなく、検証済みのstyle token群からAIが選び、完成frame検査で不合格なら別tokenへ再選定する形が安全である。

### P0-7. 投稿実績を自動ルールへ変える安全契約がない

Clip Intelligence は、公式値、欠損、観測時刻、指標版、比較条件を分け、改善効果を自動で因果断定しない。添付構想の「次回へ反映」は、この既存制約を弱めてはならない。

最低限、次を分離する必要がある。

- ユーザーが好んだ編集。
- 視聴者指標と関連した編集。
- 採用した仮説。
- 未使用素材または後続投稿で再検証済みの方針。
- 自動更新不可の固定条件。

学習対象は2層に分ける必要がある。

- **完成直後の制作学習**: 完成映像、原音、字幕、タイトル、フック、技術／意味検査、再試行履歴から、どの判断で品質が通ったかを次回へ引き継ぐ。
- **投稿後の成果学習**: Clip Intelligenceの公式統計を結び、どの変更と視聴者指標が関連したかを比較する。

自己改善の初期段階は、固定条件を勝手に書き換えるのではなく「記録→提案→版付き方針→比較→rollback」の順に進めるべきである。十分な比較根拠がある範囲だけを自動昇格し、低確度の相関を因果として扱わない。

### P1. Pro中心で運用するためのprovider方針が必要

ユーザーの希望は「なるべくOpenAI Proプランだけで実装・実行する」である。これは、現行AutoClipperのCodex host bridgeをproduction inference経路として使う方針と整合する。現行host bridgeは、保存済みのCodexログインを使う `codex exec` を、初期選定とタイトル／フック生成に利用している。

一方、字幕修正、OpenAI候補scoring、任意のOpenAIタイトル／フックproviderは `OPENAI_API_KEY` を使う直接API経路であり、ChatGPT Proの料金には含まれない。厳密なProのみ運用にするなら、これらをCodex host bridgeまたはローカル処理へ移すか、既定で無効にする必要がある。

また、Codex利用枠は無制限ではない。認証切れ、共有利用枠、週次上限、長時間動画の入力制限を前提に、jobの一時停止／再開、利用枠待ち、ローカルfallback、同じ依頼の冪等再送を設計する必要がある。ユーザーが毎回Codex UIを操作しなくても正常系を完走できることと、無制限・無条件に無人稼働できることは分けて評価する。

### P1. 現行DBの変更方式では大規模履歴追加に弱い

AutoClipper のDB初期化はSQLAlchemy `create_all` が中心で、Clip Intelligenceのような番号付きmigration契約を持たない。制作revision、event、publication連携をAutoClipper DBへ追加するなら、schema version、migration、rollback、既存job互換を先に決める必要がある。

## 7. OpenAI Pro中心で実装・実行できるか

### 評価

**「Pro-first、Platform APIは任意」という構成なら現実的である。ただし、現行のまま厳密にPro料金だけで全工程を実行できるとは評価できない。**

OpenAI公式文書では、CodexはChatGPTの各対象プランに含まれ、ローカルとクラウドのCodex利用は同じ利用枠を共有する。また、`codex exec` は対話UIを開かずscriptから実行でき、保存済みのChatGPTログインを再利用できる。一方、`OPENAI_API_KEY` によるOpenAI Platform API利用はChatGPTプランではなく、API料金として別に課金される。

参照:

- [Codex pricing](https://learn.chatgpt.com/docs/pricing)
- [Codex authentication](https://learn.chatgpt.com/docs/auth)
- [Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode)

現行AutoClipperを分類すると次のとおりである。

| 工程 | 現行経路 | Pro中心運用での扱い |
|---|---|---|
| 実装・保守 | Codex desktop／CLIで開発可能 | Proで進められる |
| ffprobe、FFmpeg、scene／audio特徴、render | ローカルCPU／GPU | OpenAI課金なしで維持する |
| 文字起こし | faster-whisper中心 | ローカルGPUを既定にする |
| 初期場面選定 | [Codex host bridge](../launcher/codex_bridge.py) の `codex exec`。現状は字幕＋heatmapで、画像入力は0件 | 保存済みChatGPT認証と利用枠で実行可能だが、映像込み選定への拡張が必要 |
| タイトル／フック／サムネ文言 | Codex host bridgeが既定。タイトル／フックは選定後の字幕＋代表4frame、原音・動画本体なし | Codex経路を既定に固定し、入力の妥当性を完成物検査で確認する |
| 字幕修正 | [OpenAITranscriptCorrector](../backend/app/audio/openai_transcript_correction.py) | 現状は別課金API。Codex経路またはローカル処理への移行が必要 |
| 候補AI scoring | [OpenAICandidateScorer](../backend/app/scoring/openai_score.py) | 現状は別課金API。Codex選定またはrule／local modelへ統合する |
| 完成物の映像・音声意味検査 | 未実装。現行bridgeは画像を渡せるが、音声file入力経路はない | 全編を直接渡せると仮定せず、連続frame、字幕、timecode、ローカル音声特徴を束ねた試作で能力と利用量を確認する |
| 投稿実績取得 | YouTube Data／Analytics API | OpenAI費用ではないが、Google側のproject、OAuth、quotaは別途必要 |

現行の通常設定は、Codex初期選定、OpenAI候補scoring OFF、AI字幕修正 OFFであり、大部分は既にPro＋ローカル処理で動かせる。ただし、それはユーザーが求める「意味を見た字幕修正まで自動」の完成形ではない。候補scoringとOpenAI版タイトル／フックは無効のままでよいが、字幕修正は新しいCodex bridge taskまたは採用品質を満たすローカル経路が必要になる。

### 推奨する料金・実行方針

1. 既定を **Pro-first** とし、Platform APIの利用を既定OFFにする。
2. AI判断は、まずローカルで候補を絞り、必要な連続frame、字幕、timecode、ローカルで抽出した発話・笑い・無音・効果音等の特徴をCodexへ渡す。現在のbridgeに存在しない音声file入力を、利用可能と仮定しない。
3. Codex利用枠不足時は、別課金APIへ黙って切り替えない。jobを安全に待機し、再開可能にする。
4. Platform APIを使う場合だけ、ユーザーが明示的に有効化し、完成1本単位の上限と利用記録を持つ。
5. 同じ入力・prompt版・revisionの再試行は冪等にし、利用枠を無駄に消費しない。

この方針なら、通常運用のOpenAI費用をPro枠内へ寄せつつ、映像理解の品質または処理量がPro経路だけで足りない場合だけ、後から任意のAPI経路を追加できる。逆に「Proなら無制限」「ChatGPT ProにAPI料金も含まれる」「長尺動画と原音をそのままCodexへ渡せば全て解決する」とは扱わない。

## 8. 現行の自動化を過大評価しないための注意

[STATUS.md](../STATUS.md) には、68分実動画で通常2本・short3本を作り、5clip中1件の人確認後に完成した受入記録がある（8360–8399行）。これは大きな再利用根拠だが、添付構想の完成を意味しない。

- 初期selectionは人のclip plan承認を必要とした。
- 1clipはASR confidenceを理由に人の確認を必要とした。
- タイトル／フック意味品質は字幕segment provenanceによる間接証拠だった。
- 人物追従はrenderer geometryによる間接証拠だった。
- 完成pixelと原音を別系統で再検査していない。
- 1本の受入から一般的な無人成功率、費用、品質を推定できない。

また、2026-09-21の画角関連変更は回帰testと実画面確認まで記録されているが、変更後設定による最終書き出し映像比較は未実施である。現行working tree全体を「実動画で受入済み」とは扱わない。

統合後の正常系では、これらの確認を人に求めないことを完了条件にする。ただし、低確度や検査不能を黙って完成扱いするのではなく、自動再選定・再修正・再renderを規定回数行い、それでも解消しなければ `needs_attention` または `incomplete` として停止する。人手は通常工程ではなく、例外時の回復手段とする。

## 9. 実装計画で先に固定する成果物

全機能を一括設計してから着手する必要はないが、データを後から結べない状態で制作機能だけを増やさないよう、最初の実装sliceで次の成果物を固定する必要がある。

1. **仕様階層表**

   v1正本、現行拡張、v2 Vision、実験機能を分ける。

2. **単一job導線と内部役割・入出力対応表**

   利用者からは1つのjobとして見せながら、AutoClipper制作、完成物検査、Clip Intelligence学習、AI provider、workerの所有工程と失敗責任を定める。第三の進行管理scriptを別の状態正本にしない。

3. **Production Record Contract v1**

   source、clip、edit revision、render revision、artifact、検査、人間修正、publicationを版付きで結ぶ。

4. **Clip Intelligence ingestion contract**

   冪等キー、受領確認、再送、削除、期限、欠損、外部YouTube IDの後付けを定める。

5. **映像・原音model比較仕様**

   静かな会話、一瞬のゲーム出来事、無言、複数話者、固有名詞を含む固定素材と、人の正解・許容差を用意する。

6. **品質ゲート仕様**

   技術検査と意味検査を分け、`pass / fail / unknown`、自動修復、再試行上限、例外停止、任意の人手復旧条件を定める。

7. **利用量・保持・権利表**

   工程別provider、送信データ、token／media費用、GPU時間、再試行上限、保存先、削除条件、ライセンスを定める。

## 10. 推奨する段階補正

添付文書の5段階は妥当だが、現行機能を踏まえて次のように読み替える。

| 段階 | 評価上の扱い |
|---|---|
| 0. 統合jobとProduction Record | 1回のuploadから全工程を追えるID、revision、artifact、検査結果を固定する |
| 1. 選定済み素材から無人完成 | 現行render／字幕／タイトル／フック／styleを統合し、完成物の独立検査と部分再実行まで通す |
| 2. 映像・原音を含む自動選定 | 既存selectionとshadow比較し、通常／shortそれぞれの場面・構成選定を置換する |
| 3. 長尺uploadから正常系を無人完走 | 通常経路からclip plan承認・字幕承認を外し、例外だけ安全に未完了停止する |
| 4. 完成直後の制作学習 | 判断、修正、検査、再試行、完成artifactを次回候補・style選定へ版付きで反映する |
| 5. Clip Intelligence成果学習 | publicationと公式metricsを結び、提案→比較→rollback可能な方針更新へ進める |

## 11. 最終評価

添付構想は、現行AutoClipperが目指してきた自動制作の方向と整合し、特に次の判断は妥当である。

- 字幕だけで映像内容を代表させない。
- AIの判断と決定的なrender処理を分ける。
- 全編再処理ではなく、影響工程だけを再実行する。
- 正常系は人の操作なしで完走させ、不明を成功扱いせず自動回復または例外停止する。
- ユーザー嗜好と視聴者実績を分ける。
- 先に品質を作り、その後に長尺自動化・無人化・自己改善へ進む。

ただし、現行の制作機能は想定より進んでおり、逆に構想の核心である映像・原音理解、独立した完成物検査、永続的な制作revision、投稿実績との安全な接続は未整備である。

よって、**本案を「AutoClipper × Clip Intelligence v2 Vision v0.1」として製品方向に採用し、利用者から見て1つの自律制作ツールとして具体化する**ことを推奨する。内部では制作・完成物検査・学習を分け、共通Production Recordで結ぶ。

本評価依頼では実装しない。次に実装へ進む場合は、最初から自己改善全体を作るのではなく、段階0の共通記録と段階1の「選定済み素材から無人で合格完成品まで」を最初の実装単位にする。Pro中心運用は実現可能性が高いが、直接API経路の置換、Codex利用枠待ち、映像・原音入力の実素材検証を完了条件に含める。
