# Task 62 targeted rescue signal evaluation

## Goal

Recover high-value subtitle correction targets missed by the score threshold without lowering the global `0.40` threshold or broadly increasing API traffic.

## Selection policy

```text
selected =
  suspicion_score >= 0.40
  OR targeted rescue signal
```

Targeted rescue signals are limited to:

- known malformed ASR expressions;
- known glossary aliases or a configured glossary near-match;
- nearby spelling variants anchored to a known or configured glossary term.

Grammar-only rewrites do not qualify. Rescue selection only sends a segment to OpenAI; it never rewrites text locally.

## Fixed 23-case fixture

The fixture comes from the manually classified baseline changes in `TRANSCRIPT_SUSPICION_MISSED_CHANGES_2026-07-16.md`.

| Check | Result |
| --- | ---: |
| Useful missed corrections recovered | `17/19` |
| Unnecessary wording changes selected | `0/1` |
| Harmful corrections selected | `0/1` |
| Inconclusive cases selected | `0/2` |

The two useful cases intentionally left out are indices `1566` and `1594`. Their correction depends on grammar or semantic context rather than a narrow reusable signal.

## Full 58-minute offline comparison

Input transcript: `1695` segments from baseline job `job_0caea4d85baf4e9cbca9a84adaf0be80`.

| Metric | Before rescue | After rescue |
| --- | ---: | ---: |
| Selected targets | `1287` | `1304` |
| Selected ratio | `75.929%` | `76.932%` |
| Added targets | - | `17` |
| Context segments | `52` | `55` |
| Unique segments sent | `1339` | `1357` |
| Expected calls at batch size 100 | `13` | `14` |
| Baseline accepted-change coverage | `250/273` | `267/273` |
| Coverage rate | `91.6%` | `97.8%` |
| Target text character proxy | `13,824` | `14,006` |
| Target + context character proxy | `14,407` | `14,597` |

All-mode deterministic transcript length is `17,726` characters. The after-rescue target-plus-context text proxy remains about `17.7%` below all-mode, before accounting for repeated prompt/schema overhead.

## Rescue diagnostics

```json
{
  "score_threshold_selected_count": 1287,
  "rescue_selected_count": 17,
  "rescue_reason_counts": {
    "glossary_phonetic_match": 6,
    "known_asr_malformed_expression": 11,
    "nearby_spelling_inconsistency": 1
  }
}
```

Reason counts can overlap on one selected segment. Exactly `17` new targets were added. No unrelated nearby spelling variant was added after requiring a glossary anchor.

## Decision

- Offline acceptance criteria: pass.
- Global threshold: keep `0.40`.
- Default correction scope: keep `all` for compatibility.
- Correction mode: keep `off` by default.
- PR readiness: pass after the final real-API replay.

## Final real-API validation

Tested code commit: `aa67fd43e136b276925983c8a32065c34a2e3d01`.

Input SHA-256: `25DF7F71CAC8DBBDDC731D2C41A55F31A852E7981CC42DB5E2F9F29816D61890`.

Configuration:

- transcription: `small + ja`;
- correction model: `gpt-5.5`;
- batch size: `100`;
- context segments: `2`;
- minimum confidence: `0.9`;
- suspicion threshold: `0.40`.

P2 E2E job: `job_ea301023a3cd431f8a5700ea4f4e4ca1`.

| Metric | All mode | Suspicious P2 | Reduction |
| --- | ---: | ---: | ---: |
| API calls | `17` | `14` | `17.647%` |
| Input tokens | `67,053` | `52,247` | `22.081%` |
| Output tokens | `134,638` | `100,698` | `25.208%` |
| Total tokens | `201,691` | `152,945` | `24.169%` |
| Correction time | `1469.749s` | `1087.679s` | `25.996%` |

P2 acceptance results:

- successful batches: `14/14`;
- retries: `0`;
- failed batches: `0`;
- schema validation failures: `0`;
- fallback: `false`;
- deterministic/corrected/final segment counts: `1695/1695/1695`;
- order or timestamp mismatches: `0`;
- normal outputs: `1/1`, `1280x720`;
- short outputs: `2/2`, both `1080x1920`;
- render failures: `0`;
- subtitle sidecar autoload risk: `0`;
- ZIP: `73,335,336 bytes`.

The all-mode token baseline used the same deterministic transcript and correction settings through the same correction implementation. It skipped transcription, candidate generation, and rendering because those stages do not affect subtitle-correction token usage.
