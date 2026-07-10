import argparse
import json
from pathlib import Path

import pytest

from app.audio.benchmark_transcription import (
    build_run_summary,
    character_error_rate,
    keyword_metrics,
    normalize_for_cer,
    main,
    parse_profile,
    render_markdown,
    timestamp_metrics,
)


def test_parse_profile_accepts_supported_model_and_language() -> None:
    assert parse_profile("base:auto") == ("base", "auto")
    assert parse_profile("medium:ja") == ("medium", "ja")

    with pytest.raises(argparse.ArgumentTypeError):
        parse_profile("tiny:ja")


def test_character_error_rate_normalizes_japanese_spacing_and_punctuation() -> None:
    assert normalize_for_cer(" OpenAI、です。 ") == "openaiです"
    assert character_error_rate("今日はOpenAIです。", "今日は OpenAI です") == 0.0
    assert character_error_rate("日本語", "日本語字") == pytest.approx(1 / 3)


def test_keyword_and_timestamp_metrics_report_failures() -> None:
    keywords = keyword_metrics("OpenAI と AutoClipper", ["OpenAI", "NewsPicks"])
    timestamps = timestamp_metrics(
        [
            {"start": 0.0, "end": 1.0, "text": "one"},
            {"start": 0.5, "end": 0.4, "text": "broken"},
        ]
    )

    assert keywords["matched"] == 1
    assert keywords["missing_keywords"] == ["NewsPicks"]
    assert timestamps["invalid_timestamp_ranges"] == 1
    assert timestamps["non_monotonic_timestamps"] == 1


def test_build_run_summary_and_markdown_do_not_apply_post_processing() -> None:
    result = {
        "model": "base",
        "language": "ja",
        "device": "cpu",
        "compute_type": "int8",
        "wall_seconds": 1.25,
        "cpu_seconds": 1.0,
        "peak_process_memory_mb": 256.0,
        "peak_vram_mb": None,
        "segments": [{"start": 0.0, "end": 1.0, "text": "今日はOpenAIです"}],
    }

    summary = build_run_summary(result, "今日はOpenAIです", ["OpenAI"])
    report = {"runs": [summary], "post_processing_applied": False}
    markdown = render_markdown(report)

    assert summary["character_error_rate"] == 0.0
    assert summary["keyword_metrics"]["accuracy"] == 1.0
    assert "base:ja" in markdown
    assert "Raw faster-whisper output only" in markdown


def test_main_writes_raw_and_summary_reports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    audio_path = tmp_path / "sample.wav"
    reference_path = tmp_path / "reference.txt"
    output_dir = tmp_path / "report"
    audio_path.write_bytes(b"wav")
    reference_path.write_text("今日はOpenAIです", encoding="utf-8")

    def fake_run_child(args: argparse.Namespace, profile: str, output_path: Path) -> None:
        model, language = parse_profile(profile)
        output_path.write_text(
            json.dumps(
                {
                    "model": model,
                    "language": language,
                    "device": "cpu",
                    "compute_type": "int8",
                    "wall_seconds": 1.0,
                    "cpu_seconds": 0.8,
                    "peak_process_memory_mb": 128.0,
                    "peak_vram_mb": None,
                    "segments": [{"start": 0.0, "end": 2.0, "text": "今日はOpenAIです"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    monkeypatch.setattr("app.audio.benchmark_transcription._run_child", fake_run_child)

    exit_code = main(
        [
            "--audio",
            str(audio_path),
            "--profile",
            "base:ja",
            "--reference-file",
            str(reference_path),
            "--keyword",
            "OpenAI",
            "--output-dir",
            str(output_dir),
        ]
    )

    report = json.loads((output_dir / "transcription_benchmark_report.json").read_text(encoding="utf-8"))
    assert exit_code == 0
    assert report["post_processing_applied"] is False
    assert report["runs"][0]["character_error_rate"] == 0.0
    assert (output_dir / "base_ja_raw_transcript_segments.json").is_file()
    assert (output_dir / "transcription_benchmark_report.md").is_file()
