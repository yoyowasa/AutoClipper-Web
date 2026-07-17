# Transcription Benchmark 2026-07-10

## Scope

Task 59 compared raw faster-whisper output before dictionary replacement or OpenAI correction.
The benchmark used one reproducible Japanese TTS reference and one real 58-minute spoken-video E2E.
Source audio, reference text, raw transcripts, and generated media remain local-only.

## Environment

- Tested commit: `7edd6f9`
- Docker image: `sha256:cb4ed9f559806cee35f6317d0dde311af2cc8dc592b8c18653cce0bf4698072c`
- Device: `cpu`
- Compute type: `int8`
- Beam size: `5`
- CPU: `Intel Core Ultra 7 265K` (`20` cores / `20` threads)
- Host RAM: `31.5 GB`
- Installed GPU: `NVIDIA GeForce RTX 5070 Ti` (not used by this benchmark)
- Python: `3.12.13`
- faster-whisper: `1.2.1`
- CTranslate2: `4.8.1`

## Controlled Japanese Reference

- Source: Windows `Microsoft Haruka Desktop` Japanese TTS
- Duration: `119.628625s`
- Audio SHA-256: `B8D81663971E9034C26D46DD62545AA9D6915605A51D1EDB7A2E0AC29D91FCF6`
- Reference SHA-256: `48CF27F60468158E66F33EC90625A3EE845D5E8FE487E8FDD8C9C0D731CA62B0`
- CER normalization: NFKC, lowercase, whitespace and punctuation removed
- Runtime values below are from the second run after model downloads were cached.

| Model | Language | CER | Terms | Wall | RTF | Peak RAM | Segments | Timestamp errors |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| base | auto | 0.2345 | 2/6 | 6.023s | 0.0503 | 415.7 MB | 18 | 0 |
| base | ja | 0.2345 | 2/6 | 5.536s | 0.0463 | 416.2 MB | 18 | 0 |
| small | ja | 0.1623 | 2/6 | 14.492s | 0.1211 | 911.0 MB | 19 | 0 |
| medium | ja | 0.1463 | 3/6 | 35.213s | 0.2944 | 2495.0 MB | 12 | 0 |
| large-v3 | ja | 0.2846 | 3/6 | 62.187s | 0.5198 | 4571.4 MB | 22 | 0 |

`small + ja` reduced CER by `30.8%` relative to `base + auto`, with `2.41x` wall time and about `2.19x` peak process RAM.
`medium + ja` improved CER by only `9.9%` relative to `small + ja`, while requiring `2.43x` wall time and `2.74x` RAM.
`large-v3 + ja` was slower and less accurate on this controlled TTS sample.

## Real Spoken-Video E2E

- Job: `job_426ce190bb02459cb3dec1829e662f98`
- Source duration: `3495.8924s`
- Source SHA-256: `25DF7F71CAC8DBBDDC731D2C41A55F31A852E7981CC42DB5E2F9F29816D61890`
- Profile: `small + ja`, CPU/int8
- Transcription: `445.313s` (`RTF 0.1274`)
- Transcript: `1695` segments, `19420` characters, average confidence `0.804132`
- Peak observed worker memory during transcription: approximately `6.13 GiB`
- Pipeline total: `652.406s`
- Selected: normal `1/1`, short `2/2`
- Render failures: `0`
- Shorts: both `1080x1920`
- Candidate memory guard: `false`
- Subtitle sidecar autoload risk: `0`

The real-video E2E validates runtime stability and output compatibility. It does not provide human-speech CER because no manually verified reference transcript exists for that source.

## Decision

- Production default remains `base + auto` for backward compatibility and non-Japanese inputs.
- `small + ja` is the recommended high-accuracy Japanese option.
- `medium + ja` remains optional when the additional runtime and memory are acceptable.
- `large-v3 + ja` is not recommended from this benchmark.
- A future default change requires a manually verified human-speech reference corpus, not TTS alone.
- OpenAI subtitle correction remains separate Task 60 work.
