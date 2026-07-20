# Task 68 Local Subtitle Correction Benchmark

Task 68 evaluates whether a local LLM can safely reduce the text sent to OpenAI. It does not
change the job pipeline, Upload UI, or production subtitle-correction defaults.

## Prerequisites

- Windows host with NVIDIA GPU
- Ollama
- `qwen3.5:9b`
- optional `qwen3:14b` when the 9B model fails
- Python 3.11+

```powershell
ollama pull qwen3.5:9b
ollama list
ollama ps
```

Record the Ollama version, model digest, quantization, model size, GPU driver, and runtime
settings from the generated JSON report. The benchmark uses the Ollama native API with:

```text
think=false
stream=false
temperature=0
seed=42
num_ctx=8192
parallel requests=1
```

## 124-second fixed transcript

This command performs no OpenAI API calls:

```powershell
python scripts\benchmark_local_subtitle_correction.py `
  --segments storage\outputs\job_062cc212d121461ca0539cbce721b708\deterministic_transcript_segments.json `
  --scope suspicious `
  --suspicion-threshold 0.4 `
  --model qwen3.5:9b `
  --batch-size 10 `
  --context-segments 2 `
  --num-ctx 8192 `
  --temperature 0 `
  --seed 42 `
  --runs 2 `
  --reference-changes storage\temp\transcription_benchmark\task64\real_124s_benchmark\gpt-5_5_default_changes.json `
  --reference-review storage\temp\transcription_benchmark\task64\real_124s_benchmark\manual_review.json `
  --output-dir storage\temp\transcription_benchmark\task68\real_124s
```

## Task 65 reviewed hard cases

The review CSV selects only rows with existing human labels. At the current local checkpoint,
that is 29 segments. Timestamps are never sent to the model.

```powershell
python scripts\benchmark_local_subtitle_correction.py `
  --segments storage\outputs\job_ea301023a3cd431f8a5700ea4f4e4ca1\deterministic_transcript_segments.json `
  --reviewed-only-csv storage\temp\transcription_benchmark\task65\long_58m_quality_audit\reasoning_quality_review.csv `
  --model qwen3.5:9b `
  --batch-size 10 `
  --context-segments 2 `
  --num-ctx 8192 `
  --temperature 0 `
  --seed 42 `
  --runs 2 `
  --output-dir storage\temp\transcription_benchmark\task68\task65_hard_cases
```

## Gates

Safety:

- full schema and every target index exactly once
- no timestamps in model input or output
- `original_text` is not returned by the model; it is reattached locally by validated index
- `changed` is derived locally from exact text comparison; model semantic normalizations are counted
- no unsafe locally accepted hard-case correction
- proper nouns, Latin/Katakana tokens, numbers, dates, units, glossary conflicts, large edits,
  and Kanji changes are escalated
- punctuation-only edits do not remove an already suspicious segment from API escalation

Utility:

- output is stable across repeated runs
- useful local corrections are counted separately from escalations
- projected API target text reduction is at least 20%

Failure at either gate stops Task 68 before pipeline/provider integration. `qwen3:14b` is only
evaluated if `qwen3.5:9b` fails or has insufficient utility.

## 2026-07-20 benchmark result

Environment:

```text
Ollama: 0.32.1
GPU: NVIDIA GeForce RTX 5070 Ti 16GB
driver: 595.97
think: false
num_ctx: 8192
temperature: 0
seed: 42
batch size: 10
```

`qwen3.5:9b` (`6488c96fa5fa`, Q4_K_M, 6.6GB):

```text
124-second fixed transcript:
  targets: 36
  model changes: 6
  safely accepted: 0
  API text reduction: 0%
  processing: 13.656s
  peak VRAM: 8659 MiB

Task65 reviewed hard cases:
  targets: 29
  model changes: 8
  safely accepted: 0
  unsafe local accepts: 0
  API text reduction: 0%
  processing: 10.390s
  peak VRAM: 8769 MiB
```

`qwen3:14b` (`bdbd181c33f2`, Q4_K_M, 9.3GB):

```text
124-second fixed transcript:
  targets: 36
  model changes: 0
  safely accepted: 0
  API text reduction: 0%
  processing: 28.500s
  peak VRAM: 12209 MiB

Task65 reviewed hard cases:
  targets: 29
  model changes: 2
  safely accepted: 1
  unsafe local accepts: 1
  API text reduction: 6.575%
  processing: 21.438s
  peak VRAM: 12774 MiB
```

Decision:

- Both models fail the required 20% API text reduction gate.
- `qwen3:14b` also fails the zero unsafe-local-accept safety gate.
- Repeated runs and 58-minute evaluation were intentionally not run after the fail-fast gates.
- No OpenAI API calls were made.
- No pipeline, provider, UI, or production default changes are made.
