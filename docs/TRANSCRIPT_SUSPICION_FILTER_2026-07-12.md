# Transcript Suspicion Filter Validation 2026-07-12

## Scope

Task 62 adds an opt-in local suspicion filter before OpenAI subtitle correction. The compatibility default remains `subtitleCorrectionScope=all`. Local media, transcripts, and generated reports remain ignored under `storage/`.

## Behavior

- `all`: send every deterministic transcript segment.
- `suspicious`: score locally, send only target indices, and include at most four read-only context segments per API batch.
- Non-target segments cannot be changed.
- Zero targets produce zero API calls.
- Filter failure never switches silently to `all`; it retains the deterministic transcript.
- API summaries record actual input, output, and cached token usage when returned by Responses API.

## Controlled Japanese TTS

Input: 19 `small + ja` segments with a local reference transcript.

| Metric | All | Suspicious |
| --- | ---: | ---: |
| Targets | 19 | 8 |
| API calls | 1 | 1 |
| Accepted corrections | 7 | 7 |
| Accepted correction recall | 100% | 100% |
| Input tokens | 1200 | 1085 |
| Output tokens | 1806 | 1316 |
| Total tokens | 3006 | 2401 |

Surface CER remains unsuitable for proper-name style changes such as `オートクリッパー` to `AutoClipper`. Canonical alias-normalized comparison is retained for quality review.

## 124-second Real Spoken Sample

| Metric | All | Suspicious |
| --- | ---: | ---: |
| Segments | 48 | 48 |
| Targets | 48 | 36 |
| API calls | 2 | 1 |
| Input tokens | 2673 | 1942 |
| Output tokens | 11451 | 5787 |
| Total tokens | 14124 | 7729 |
| Correction time | 157.3s | 61.0s |

The optimized suspicious run reduced total tokens by 45.3%, halved calls, preserved timestamps/count, and completed normal pipeline rendering with a valid 1080x1920 short.

## 58-minute Real Spoken Sample

Baseline all-segment Task 60 job:

- segments: 1695
- calls: 17
- accepted corrections: 273
- correction time: 1582.6s

Task 62 full E2E before the final long-transcript consistency signal:

- job: `job_31b475f0328f4a6fa0239316100b34a0`
- targets: 977 / 1695
- calls: 10
- accepted corrections: 205
- input/output tokens: 38545 / 76838
- correction time: 706.5s
- proxy input text reduction: 42.3%
- proxy output text reduction: 43.1%
- normal: 1/1
- shorts: 2/2, both 1080x1920
- render failures: 0
- sidecar risk: 0

The first filter covered only 208/273 baseline accepted-change indices (76.2%). A long-transcript-only repeated CJK compound signal was therefore added. Final offline evaluation:

- targets: 1287 / 1695
- estimated calls at batch 100: 13 / 17
- covered baseline accepted-change indices: 250 / 273 (91.6%)

The final API replay completed 7/13 batches without retry or schema failure, then stopped on `429 insufficient_quota`. A complete final-signal 58-minute API replay remains pending. Production jobs use the existing full-transcript fallback instead of retaining partial corrections.

## Decision

- Keep correction default `off`.
- Keep correction scope default `all`.
- Keep `suspicious` opt-in with threshold `0.40`.
- Prioritize correction recall over maximum token reduction.
- Do not claim 40% actual input-token reduction for every input. Savings depend on transcript length, confidence distribution, and context density.
