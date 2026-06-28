import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import e2e_real_video as script  # noqa: E402
import e2e_summary  # noqa: E402


def test_parse_args_defaults_and_burn_subtitle_variants() -> None:
    args = script.parse_args(["--video", "spoken.mp4"])
    assert args.video == Path("spoken.mp4")
    assert args.backend_url == "http://localhost:8000"
    assert args.timeout == 1800
    assert args.normal_count == 1
    assert args.short_count == 1
    assert args.mode == "low_cost"
    assert args.profile == "talk"
    assert args.burn_subtitles is True
    assert args.normal_min_duration == 90.0
    assert args.normal_max_duration == 600.0
    assert args.short_min_duration == 20.0
    assert args.short_max_duration == 75.0
    assert args.selection_policy == "fill_requested"

    false_args = script.parse_args(["--video", "spoken.mp4", "--burn-subtitles", "false"])
    assert false_args.burn_subtitles is False

    no_flag_args = script.parse_args(["--video", "spoken.mp4", "--no-burn-subtitles"])
    assert no_flag_args.burn_subtitles is False


def test_build_job_settings_disables_fixture_transcript() -> None:
    args = script.parse_args(
        [
            "--video",
            "spoken.mp4",
            "--normal-count",
            "2",
            "--short-count",
            "0",
            "--mode",
            "low_cost",
            "--profile",
            "talk",
            "--normal-min-duration",
            "20",
            "--normal-max-duration",
            "60",
            "--short-min-duration",
            "15",
            "--short-max-duration",
            "45",
            "--selection-policy",
            "strict_quality",
            "--no-burn-subtitles",
        ]
    )
    settings = script.build_job_settings(args)

    assert settings["e2eFixtureTranscript"] is False
    assert settings["useOpenAIScoring"] is False
    assert settings["normalClipCount"] == 2
    assert settings["shortCount"] == 0
    assert settings["normalMinDuration"] == 20.0
    assert settings["normalMaxDuration"] == 60.0
    assert settings["shortMinDuration"] == 15.0
    assert settings["shortMaxDuration"] == 45.0
    assert settings["selectionPolicy"] == "strict_quality"
    assert settings["burnSubtitles"] is False
    assert settings["profile"] == "talk"

    high_quality_args = script.parse_args(["--video", "spoken.mp4", "--mode", "high_quality"])
    assert script.build_job_settings(high_quality_args)["useOpenAIScoring"] is True

    invalid_args = script.parse_args(
        ["--video", "spoken.mp4", "--normal-min-duration", "60", "--normal-max-duration", "20"]
    )
    with pytest.raises(RuntimeError, match="normal-max-duration"):
        script.build_job_settings(invalid_args)


def test_runtime_metrics_use_observed_status_transitions() -> None:
    timing = script.TimedJobResult(
        final_status={"status": "completed"},
        status_times={
            "transcribing": 10.0,
            "detecting_scenes": 15.5,
            "generating_candidates": 16.0,
            "scoring_candidates": 20.0,
            "selecting_clips": 22.5,
            "rendering_normal_clips": 30.0,
            "rendering_shorts": 35.0,
            "packaging_zip": 44.0,
            "completed": 45.0,
        },
        poll_started_at=9.0,
        poll_finished_at=45.0,
    )

    metrics = script.runtime_metrics(upload_seconds=1.25, job_timing=timing, total_seconds=50.0)

    assert metrics["upload_time"] == 1.25
    assert metrics["transcription_time"] == pytest.approx(5.5)
    assert metrics["candidate_generation_time"] == pytest.approx(4.0)
    assert metrics["scoring_time"] == pytest.approx(2.5)
    assert metrics["render_time"] == pytest.approx(14.0)
    assert metrics["total_time"] == 50.0
    assert script.format_seconds(None) == "n/a"
    assert script.format_seconds(1.23456) == "1.235s"


def test_pipeline_metrics_read_diagnostic_summaries(tmp_path: Path) -> None:
    (tmp_path / "transcript_summary.json").write_text(
        json.dumps({"segment_count": 8, "total_text_length": 420}),
        encoding="utf-8",
    )
    (tmp_path / "candidate_summary.json").write_text(
        json.dumps(
            {
                "short_candidates": 30,
                "normal_candidates": 12,
                "hard_gate_passed_count": 35,
                "selected_below_threshold_backfill_count": 2,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "selected_clips_summary.json").write_text(
        json.dumps(
            {
                "selected_normal_count": 1,
                "selected_short_count": 2,
                "selected_below_threshold_backfill_count": 1,
            }
        ),
        encoding="utf-8",
    )

    metrics = script.pipeline_metrics(tmp_path)

    assert metrics == {
        "transcript_segment_count": 8,
        "total_transcript_text_length": 420,
        "short_candidates_count": 30,
        "normal_candidates_count": 12,
        "hard_gate_passed_count": 35,
        "selected_normal_count": 1,
        "selected_short_count": 2,
        "backfilled_count": 1,
    }


def test_validate_output_probe_checks_short_dimensions_and_normal_duration(tmp_path: Path) -> None:
    valid_normal = script.ProbeResult(width=1920, height=1080, duration=58.8)
    script.validate_output_probe({"type": "normal", "duration": 60.0}, tmp_path / "normal.mp4", valid_normal)

    with pytest.raises(RuntimeError, match="normal output duration mismatch"):
        script.validate_output_probe(
            {"type": "normal", "duration": 60.0},
            tmp_path / "normal_bad.mp4",
            script.ProbeResult(width=1920, height=1080, duration=45.0),
        )

    with pytest.raises(RuntimeError, match="short output must be 1080x1920"):
        script.validate_output_probe(
            {"type": "short", "duration": 25.0},
            tmp_path / "short_bad.mp4",
            script.ProbeResult(width=720, height=1280, duration=25.0),
        )

    with pytest.raises(RuntimeError, match="invalid duration"):
        script.validate_output_probe(
            {"type": "short", "duration": 25.0},
            tmp_path / "empty.mp4",
            script.ProbeResult(width=1080, height=1920, duration=0.0),
        )


def test_resolve_input_video_requires_existing_file(tmp_path: Path) -> None:
    video = tmp_path / "spoken.mp4"
    video.write_bytes(b"mp4")

    assert script.resolve_input_video(video) == video.resolve()
    with pytest.raises(RuntimeError, match="input video not found"):
        script.resolve_input_video(tmp_path / "missing.mp4")


def test_validate_transcript_artifact_rejects_missing_short_and_fixture_text(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="transcript_segments.json not found"):
        script.validate_transcript_artifact(tmp_path)

    transcript_path = tmp_path / "transcript_segments.json"
    transcript_path.write_text(json.dumps([{"start": 0, "end": 1, "text": "too short"}]), encoding="utf-8")
    with pytest.raises(RuntimeError, match="transcript text too short"):
        script.validate_transcript_artifact(tmp_path)

    transcript_path.write_text(
        json.dumps(
            [
                {
                    "start": 0,
                    "end": 25,
                    "text": "Why automation mistakes matter before launch. fixture text should fail.",
                }
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="fixture transcript marker"):
        script.validate_transcript_artifact(tmp_path)

    transcript_path.write_text(
        json.dumps(
            [
                {
                    "start": 0,
                    "end": 25,
                    "text": "This is a real spoken transcript with enough words to validate the E2E path.",
                }
            ]
        ),
        encoding="utf-8",
    )
    assert "real spoken transcript" in script.validate_transcript_artifact(tmp_path)


def test_diagnose_no_clips_classifies_failure_modes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(script, "ROOT", tmp_path)
    job_id = "job_test"
    output_dir = tmp_path / "storage" / "outputs" / job_id
    output_dir.mkdir(parents=True)

    missing_transcript = script.diagnose_no_clips(job_id)
    assert "cause=no transcript" in missing_transcript

    (output_dir / "transcript_segments.json").write_text(
        json.dumps(
            [
                {
                    "start": 0,
                    "end": 100,
                    "text": "This transcript is long enough to generate candidates for the diagnostic helper.",
                }
            ]
        ),
        encoding="utf-8",
    )
    (output_dir / "candidates.json").write_text("[]", encoding="utf-8")
    no_candidates = script.diagnose_no_clips(job_id, {"error": {"code": "no_candidates_found", "message": "none"}})
    assert "cause=no candidates" in no_candidates

    (output_dir / "candidates.json").write_text(json.dumps([{"id": "cand_1"}]), encoding="utf-8")
    (output_dir / "selected_clips.json").write_text(
        json.dumps(
            {
                "normalClips": [],
                "shorts": [],
                "rejectedCandidates": [{"candidateId": "cand_1", "type": "short", "reasons": ["low_final_score"]}],
            }
        ),
        encoding="utf-8",
    )
    quality_gate = script.diagnose_no_clips(job_id)
    assert "cause=quality gate rejection" in quality_gate
    assert "low_final_score=1" in quality_gate

    (output_dir / "selected_clips.json").write_text(
        json.dumps({"normalClips": [], "shorts": [{"id": "cand_1"}], "rejectedCandidates": []}),
        encoding="utf-8",
    )
    (output_dir / "render_failures.json").write_text(
        json.dumps([{"type": "short", "candidate_id": "cand_1", "error": "ffmpeg failed"}]),
        encoding="utf-8",
    )
    render_failure = script.diagnose_no_clips(job_id, {"error": {"code": "no_usable_output", "message": "none"}})
    assert "cause=render failure" in render_failure


def test_e2e_summary_formats_and_prints_job_summaries(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    job_id = "job_summary"
    output_dir = tmp_path / "storage" / "outputs" / job_id
    output_dir.mkdir(parents=True)
    (output_dir / "transcript_summary.json").write_text(
        json.dumps(
            {
                "segment_count": 2,
                "total_text_length": 80,
                "total_speech_duration": 42.0,
                "average_confidence": 0.91,
                "transcription_engine": "faster_whisper",
                "used_fixture_transcript": False,
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "candidate_summary.json").write_text(
        json.dumps(
            {
                "total_candidates": 12,
                "normal_candidates": 4,
                "short_candidates": 8,
                "candidates_with_transcript_text": 12,
                "avg_duration": 52.5,
                "avg_final_score": 71.2,
            }
        ),
        encoding="utf-8",
    )

    line = e2e_summary.summary_line(
        "transcript_summary.json",
        {
            "segment_count": 2,
            "total_text_length": 80,
            "total_speech_duration": 42.0,
            "average_confidence": 0.91,
            "transcription_engine": "faster_whisper",
            "used_fixture_transcript": False,
        },
    )
    assert "segments=2" in line
    assert "engine=faster_whisper" in line

    e2e_summary.print_job_summaries(job_id, root=tmp_path)
    output = capsys.readouterr().out
    assert "transcript_summary.json: segments=2" in output
    assert "candidate_summary.json: total=12" in output
    assert "audio_feature_summary.json: missing" in output
