# Subtitle Correction Model Benchmark

## Purpose

Compare subtitle correction model and reasoning settings without retranscribing audio or sending
media to OpenAI. The input is a fixed deterministic transcript and an optional fixed target-index
artifact.

Production defaults remain unchanged until the comparison is complete:

```text
subtitleCorrectionMode=off
subtitleCorrectionModel=gpt-5.5
subtitleCorrectionReasoningEffort=default
```

`default` omits the Responses API `reasoning` parameter. It is not an alias for a specific effort.

## Profiles

The default benchmark profiles are:

```text
gpt-5.5:default
gpt-5.5:none
gpt-5.4-mini:none
gpt-5-mini:lowest
gpt-5.6-luna:none
```

`gpt-5-mini:lowest` must first be resolved by the one-segment probe. The benchmark phase reads that
resolution from `subtitle_correction_probe_report.json`.

## Probe

```powershell
python scripts/benchmark_subtitle_correction_models.py `
  --phase probe `
  --segments storage/outputs/JOB_ID/deterministic_transcript_segments.json `
  --targets-file storage/outputs/JOB_ID/subtitle_correction_targets.json `
  --probe-target-index 0 `
  --batch-size 100 `
  --context-segments 2 `
  --min-confidence 0.9 `
  --output-dir storage/temp/subtitle_correction_probe
```

The probe verifies:

- reasoning setting acceptance
- Structured Outputs schema success
- one-segment API connectivity
- input/output/reasoning/visible token usage

It may try multiple reasoning values only for a `lowest` profile and stops at the first accepted
value.

## Benchmark

```powershell
python scripts/benchmark_subtitle_correction_models.py `
  --phase benchmark `
  --segments storage/outputs/JOB_ID/deterministic_transcript_segments.json `
  --targets-file storage/outputs/JOB_ID/subtitle_correction_targets.json `
  --probe-report storage/temp/subtitle_correction_probe/subtitle_correction_probe_report.json `
  --profile gpt-5.5:default `
  --profile gpt-5.5:none `
  --profile gpt-5.4-mini:none `
  --profile gpt-5-mini:lowest `
  --profile gpt-5.6-luna:none `
  --batch-size 100 `
  --context-segments 2 `
  --min-confidence 0.9 `
  --output-dir storage/temp/subtitle_correction_benchmark
```

When `--targets-file` is omitted and `--scope suspicious` is used, the current local suspicion
filter derives target indices at `--suspicion-threshold 0.4`. Use a fixed targets artifact for
strict replay comparability.

Optional quality inputs:

```text
--reference-file PATH
--keyword TERM
--canonical-alias SOURCE=TARGET
--manual-review-file PATH
```

Manual review JSON format:

```json
{
  "profiles": {
    "gpt-5_5_none": {
      "useful_corrections": [2, 14],
      "missed_corrections": [8],
      "harmful_corrections": [],
      "unnecessary_style_changes": [12],
      "uncertain": []
    }
  }
}
```

Apply manual classifications without calling OpenAI again:

```powershell
python scripts/benchmark_subtitle_correction_models.py `
  --phase review `
  --existing-report storage/temp/subtitle_correction_benchmark/subtitle_correction_model_benchmark.json `
  --manual-review-file storage/temp/subtitle_correction_benchmark/manual_review.json `
  --output-dir storage/temp/subtitle_correction_benchmark
```

## Outputs

```text
subtitle_correction_probe_report.json
subtitle_correction_probe_report.md
subtitle_correction_model_benchmark.json
subtitle_correction_model_benchmark.md
{profile}_corrected_transcript_segments.json
{profile}_changes.json
```

The report records:

- actual `input_tokens`
- actual `output_tokens`
- `reasoning_tokens`
- `visible_output_tokens`
- API calls, retries, schema failures, and fallback
- processing seconds
- segment count/order/timestamp preservation
- CER and proper-noun matches when reference inputs are supplied
- manual useful/missed/harmful/style classifications when supplied
- usage-based USD estimate
- first profileを基準とした変更indexの共通数と差分数
- first profile比のoutput/total token、費用、処理時間の削減率

The cost value is an estimate, not an invoice amount. It uses actual token usage and a pricing
snapshot dated `2026-07-18`, including cached-input pricing when `cached_tokens` is returned.
