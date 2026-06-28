import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import e2e_real_video as script  # noqa: E402


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
            "--no-burn-subtitles",
        ]
    )
    settings = script.build_job_settings(args)

    assert settings["e2eFixtureTranscript"] is False
    assert settings["useOpenAIScoring"] is False
    assert settings["normalClipCount"] == 2
    assert settings["shortCount"] == 0
    assert settings["burnSubtitles"] is False
    assert settings["profile"] == "talk"

    high_quality_args = script.parse_args(["--video", "spoken.mp4", "--mode", "high_quality"])
    assert script.build_job_settings(high_quality_args)["useOpenAIScoring"] is True


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
