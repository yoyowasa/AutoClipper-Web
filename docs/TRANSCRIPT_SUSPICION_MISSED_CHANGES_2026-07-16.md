# Task 62 missed-change classification

## Scope

- Baseline all-mode job: `job_0caea4d85baf4e9cbca9a84adaf0be80`
- Suspicion-filter job: `job_3ec9083055224a9fbd1c8a4b8f904d5b`
- Input SHA-256: `25DF7F71CAC8DBBDDC731D2C41A55F31A852E7981CC42DB5E2F9F29816D61890`
- Baseline accepted changes: `273`
- Filter targets: `1287/1695`
- Baseline changes outside the filter: `23`

No OpenAI API was used for this classification. Each excluded segment was checked against its transcript context and local `medium+ja` and `large-v3+ja` transcriptions of the source audio with two seconds of leading and trailing context.

## Aggregate result

| Classification | Count |
| --- | ---: |
| Useful correction missed | 19 |
| Unnecessary wording change | 1 |
| Harmful correction | 1 |
| Inconclusive | 2 |

`19/23 = 82.6%` of the excluded baseline changes were judged useful. The current filter therefore needs targeted recall improvements before Task 62 is ready. This does not justify lowering the global threshold because that would increase API volume for every video.

## Classification

| Index | Time | Original | OpenAI correction | Classification | Evidence |
| ---: | ---: | --- | --- | --- | --- |
| 64 | 167.70 | 人に見えて | 目に見えて | Inconclusive | Context supports `目に見えて`, but both local models transcribed `人に見えて`. Human listening is required. |
| 110 | 267.20 | でかいなっていう感じでは | でかいなっていう感じで | Unnecessary wording change | Both local models retained `では`; the correction mainly rewrites spoken style. |
| 157 | 369.34 | 一番注目しなきゃらないことは | 一番注目しなきゃならないことは | Useful correction missed | `large-v3` and grammar support the correction. |
| 164 | 380.74 | これがめちゃくちゃのマネになってるわけで | これがめちゃくちゃなマネーになってるわけで | Inconclusive | `large-v3` supports `マネー` but retained the original particle `の`; the OpenAI result mixes a useful spelling fix with a possible overcorrection. |
| 285 | 650.86 | ボカで | 簿価で | Useful correction missed | Finance context identifies the homophone as `簿価`. |
| 306 | 684.96 | 安態なわけですよ | 安泰なわけですよ | Useful correction missed | `medium` and `large-v3` support `安泰`. |
| 446 | 962.20 | 遅いかかってくるわけですよ | 襲いかかってくるわけですよ | Useful correction missed | Both local models support `襲いかかって`. |
| 447 | 963.72 | そのぶっかだかっていう形で | その物価高っていう形で | Useful correction missed | Adjacent context and `large-v3` identify `物価高`. |
| 496 | 1071.64 | この辺だったら1000円買えないですけどね | この辺だったら1000円で買えないですけどね | Useful correction missed | Lunch-price context requires the missing particle `で`. |
| 519 | 1136.62 | 劇的に変わるザロンを得ない | 劇的に変わらざるを得ない | Useful correction missed | The original is a broken fixed expression; context supports the correction. |
| 756 | 1682.46 | 例えばソンさんが | 例えば孫さんが | Useful correction missed | `large-v3` and the proper-name context support `孫さん`. |
| 885 | 1906.82 | ナイデッグのような | ニデックのような | Useful correction missed | Company and founder context supports `ニデック`. |
| 914 | 1950.32 | 株の高熱株 | 株の高値掴み | Useful correction missed | Both local models support a form of `高値掴み`. |
| 919 | 1959.34 | みんながコンセンサー | みんながコンセンサス | Useful correction missed | `large-v3` and standard terminology support `コンセンサス`. |
| 971 | 2056.38 | どかの大学で | どこかの大学で | Useful correction missed | Both local models restore the missing mora as `どこか` or `どっか`. |
| 1059 | 2220.26 | 他のテレビ国とも | 他のテレビ局とも | Useful correction missed | `large-v3` and context support `テレビ局`. |
| 1256 | 2613.34 | 考え方で持って | 考え方を持って | Harmful correction | `large-v3` retained `で持って`; the wider phrase is consistent with spoken `考え方でもって`. |
| 1334 | 2763.32 | 氷関係にしても | 小売関係にしても | Useful correction missed | `large-v3` and the industry-list context support `小売関係`. |
| 1360 | 2814.00 | 追いつかないだろうかな | 追いつかないだろうから | Useful correction missed | `large-v3` supports `だろうから`. |
| 1490 | 3077.44 | 株式投資に通することだ | 株式投資に通じることだ | Useful correction missed | `medium`, `large-v3`, and grammar support `通じる`. |
| 1561 | 3213.28 | だからナブが毎年 | だからNAVが毎年 | Useful correction missed | Valuation context identifies the term as `NAV`. |
| 1566 | 3222.22 | 売らないといけない人たち用ですよね | 売らないといけない人たちですよね | Useful correction missed | `large-v3` supports the correction and the following sentence confirms the referent is people, not a product for them. |
| 1594 | 3277.46 | 進むだろうけど | 済むだろうけど | Useful correction missed | `large-v3` and the transaction-size context support `済む`. |

## Filter decision

Adjustment is required, but the global suspicion threshold should remain `0.40` until a new benchmark proves otherwise.

Recommended targeted signals:

1. Reusable malformed-expression patterns for obvious ASR fragments such as `しなきゃらない`, `変わるザロンを得ない`, and `通する`.
2. Configurable domain glossary matching for finance and company terms such as `簿価`, `物価高`, `ニデック`, `コンセンサス`, and `NAV`.
3. Stronger inconsistent-spelling checks across nearby segments, including kana/kanji and acronym forms.
4. Keep grammar-only rewrites out of the target pool unless another signal exists; indices 110 and 1256 demonstrate overcorrection risk.
5. Human-listening review remains required for indices 64 and 164.

The next implementation should add narrowly targeted signals and rerun the offline coverage/cost calculation before another real-API replay.
