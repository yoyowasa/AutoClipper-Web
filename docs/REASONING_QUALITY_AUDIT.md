# GPT-5.5 Default vs None Quality Audit

## Purpose

Review the long-video correction differences from Task 64 without making additional OpenAI API
calls. The audit compares existing `gpt-5.5:default` and `gpt-5.5:none` change artifacts and keeps
four groups separate:

```text
default_only
none_only
shared_same_text
shared_different_text
```

The script does not decide correctness. A reviewer must listen to the extracted audio before adding
labels.

## Prepare review package

```powershell
python scripts/audit_reasoning_quality.py prepare `
  --segments storage/outputs/JOB_ID/deterministic_transcript_segments.json `
  --default-changes storage/temp/BENCHMARK/gpt-5_5_default_changes.json `
  --none-changes storage/temp/BENCHMARK/gpt-5_5_none_changes.json `
  --video storage/uploads/VIDEO_ID.mp4 `
  --output-dir storage/temp/reasoning_quality_audit `
  --context-segments 1 `
  --audio-padding-seconds 0.35 `
  --extract-audio `
  --docker-service worker `
  --storage-root storage
```

This only uses local files and FFmpeg. It does not call OpenAI.

## Outputs

```text
reasoning_quality_review.json
reasoning_quality_review.csv
reasoning_quality_audit_summary.json
reasoning_quality_audit.md
audio/*.wav
```

The CSV is UTF-8 with BOM for Excel compatibility. Each row contains:

- source transcript and one neighboring segment on each side
- default and none output text
- comparison group
- relative audio path
- empty review fields

Generated review files and audio belong under ignored `storage/temp/`. Do not commit source media,
audio snippets, or completed review files containing case-specific transcript text.

## Review labels

Fill both `default_label` and `none_label`:

```text
useful_correction
harmful_correction
unnecessary_style_change
equivalent_alternative
missed_correction
uncertain
```

Use `term_types` as a semicolon-separated list when relevant:

```text
proper_noun;numeric;technical_term
```

`equivalent_alternative` is not a quality loss. Use `missed_correction` only when the audio clearly
supports a correction that the model output omitted.

## Summarize completed labels

```powershell
python scripts/audit_reasoning_quality.py summarize `
  --review storage/temp/reasoning_quality_audit/reasoning_quality_review.json `
  --labels-csv storage/temp/reasoning_quality_audit/reasoning_quality_review.csv `
  --output-dir storage/temp/reasoning_quality_audit
```

The summary reports:

- review completion
- label counts by model
- none useful recall relative to useful default corrections
- harmful correction rate by model
- missed proper nouns, numbers, and technical terms

Partial reviews remain `status=partial`. Missing labels are not treated as successful, harmful, or
missed corrections.

## Decision gate

Do not recommend `gpt-5.5:none` as the normal default until the audio review is complete. The
provisional gate is:

```text
none useful recall vs default >= 95%
none harmful correction count = 0 or no worse than default
no important proper-noun, numeric, or technical-term misses
equivalent alternatives excluded from quality loss
```

Task 66 changes-only schema work must use a separate branch and benchmark. Schema effects must not be
mixed into this reasoning-quality audit.
