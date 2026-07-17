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
    assert args.validation_profile == "default"
    assert args.timeout == 1800
    assert args.normal_count == 1
    assert args.short_count == 1
    assert args.mode == "low_cost"
    assert args.profile == "talk"
    assert args.whisper_model_size == "base"
    assert args.transcription_language == "auto"
    assert args.subtitle_correction_mode == "off"
    assert args.subtitle_correction_scope == "all"
    assert args.subtitle_correction_suspicion_threshold == 0.4
    assert args.subtitle_correction_model == "gpt-5.5"
    assert args.subtitle_correction_min_confidence == 0.9
    assert args.subtitle_correction_batch_size == 40
    assert args.subtitle_correction_context_segments == 2
    assert args.subtitle_correction_fallback_enabled is True
    assert args.burn_subtitles is True
    assert args.normal_min_duration == 90.0
    assert args.normal_max_duration == 600.0
    assert args.short_min_duration == 20.0
    assert args.short_max_duration == 75.0
    assert args.short_overlay_title_mode == "auto"
    assert args.selection_policy == "fill_requested"
    assert args.use_openai_scoring is None
    assert args.openai_candidate_limit == 20
    assert args.openai_model == "gpt-5.5"
    assert args.openai_fallback_to_rule_score is True
    assert args.ensure_selected_openai_scored is None
    assert args.openai_finalist_scoring_limit is None
    assert args.max_raw_candidates_per_type is None
    assert args.max_kept_candidates_per_type is None
    assert args.max_candidates_per_time_bucket is None
    assert args.candidate_time_bucket_seconds is None
    assert args.max_candidate_generation_memory_mb is None
    assert args.enable_transcript_post_processing is None
    assert args.transcript_replacements_json is None

    false_args = script.parse_args(["--video", "spoken.mp4", "--burn-subtitles", "false"])
    assert false_args.burn_subtitles is False

    no_flag_args = script.parse_args(["--video", "spoken.mp4", "--no-burn-subtitles"])
    assert no_flag_args.burn_subtitles is False


@pytest.mark.parametrize(
    "option,value",
    [
        ("--subtitle-correction-min-confidence", "1.1"),
        ("--subtitle-correction-min-confidence", "-0.1"),
        ("--subtitle-correction-suspicion-threshold", "1.1"),
        ("--subtitle-correction-batch-size", "0"),
    ],
)
def test_parse_args_rejects_invalid_subtitle_correction_values(option: str, value: str) -> None:
    with pytest.raises(SystemExit):
        script.parse_args(["--video", "spoken.mp4", option, value])


def test_parse_args_30min_validation_profile_and_overrides() -> None:
    args = script.parse_args(["--video", "long.mp4", "--validation-profile", "30min"])

    assert args.validation_profile == "30min"
    assert args.timeout == 7200
    assert args.normal_count == 2
    assert args.short_count == 3
    assert args.mode == "low_cost"
    assert args.normal_min_duration == 90.0
    assert args.normal_max_duration == 600.0
    assert args.short_min_duration == 20.0
    assert args.short_max_duration == 75.0
    assert args.selection_policy == "fill_requested"

    override_args = script.parse_args(
        [
            "--video",
            "long.mp4",
            "--validation-profile",
            "30min",
            "--short-count",
            "1",
            "--timeout",
            "9000",
        ]
    )

    assert override_args.short_count == 1
    assert override_args.timeout == 9000
    assert override_args.normal_count == 2


def test_parse_args_30min_high_quality_validation_profile() -> None:
    args = script.parse_args(["--video", "long.mp4", "--validation-profile", "30min_high_quality"])

    assert args.validation_profile == "30min_high_quality"
    assert args.timeout == 7200
    assert args.normal_count == 2
    assert args.short_count == 3
    assert args.mode == "high_quality"
    assert args.use_openai_scoring is True
    assert args.openai_candidate_limit == 20
    assert args.openai_model == "gpt-5.5"
    assert args.openai_fallback_to_rule_score is True
    assert args.ensure_selected_openai_scored is True
    assert args.openai_finalist_scoring_limit == 7
    settings = script.build_job_settings(args)
    assert settings["useOpenAIScoring"] is True
    assert settings["openaiCandidateLimit"] == 20
    assert settings["ensureSelectedOpenAIScored"] is True
    assert settings["openaiFinalistScoringLimit"] == 7


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
            "--whisper-model-size",
            "small",
            "--transcription-language",
            "ja",
            "--subtitle-correction-mode",
            "openai",
            "--subtitle-correction-model",
            "gpt-5.5",
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
            "--use-openai-scoring",
            "true",
            "--openai-candidate-limit",
            "7",
            "--subtitle-correction-scope",
            "suspicious",
            "--subtitle-correction-suspicion-threshold",
            "0.6",
            "--subtitle-correction-reasoning-effort",
            "none",
            "--openai-model",
            "gpt-test",
            "--ensure-selected-openai-scored",
            "true",
            "--openai-finalist-scoring-limit",
            "4",
            "--max-raw-candidates-per-type",
            "1000",
            "--max-kept-candidates-per-type",
            "300",
            "--max-candidates-per-time-bucket",
            "25",
            "--candidate-time-bucket-seconds",
            "120",
            "--max-candidate-generation-memory-mb",
            "2048",
            "--candidate-chunk-seconds",
            "300",
            "--candidate-chunk-overlap-seconds",
            "75",
            "--short-overlay-title-mode",
            "always",
            "--disable-transcript-post-processing",
            "--no-openai-fallback-to-rule-score",
            "--no-burn-subtitles",
        ]
    )
    settings = script.build_job_settings(args)

    assert settings["e2eFixtureTranscript"] is False
    assert settings["whisperModelSize"] == "small"
    assert settings["transcriptionLanguage"] == "ja"
    assert settings["subtitleCorrectionMode"] == "openai"
    assert settings["subtitleCorrectionScope"] == "suspicious"
    assert settings["subtitleCorrectionSuspicionThreshold"] == 0.6
    assert settings["subtitleCorrectionModel"] == "gpt-5.5"
    assert settings["subtitleCorrectionReasoningEffort"] == "none"
    assert settings["useOpenAIScoring"] is True
    assert settings["normalClipCount"] == 2
    assert settings["shortCount"] == 0
    assert settings["normalMinDuration"] == 20.0
    assert settings["normalMaxDuration"] == 60.0
    assert settings["shortMinDuration"] == 15.0
    assert settings["shortMaxDuration"] == 45.0
    assert settings["shortOverlayTitleMode"] == "always"
    assert settings["selectionPolicy"] == "strict_quality"
    assert settings["useOpenAIScoring"] is True
    assert settings["openaiCandidateLimit"] == 7
    assert settings["openaiModel"] == "gpt-test"
    assert settings["openaiFallbackToRuleScore"] is False
    assert settings["ensureSelectedOpenAIScored"] is True
    assert settings["openaiFinalistScoringLimit"] == 4
    assert settings["burnSubtitles"] is False
    assert settings["profile"] == "talk"
    assert settings["maxRawCandidatesPerType"] == 1000
    assert settings["maxKeptCandidatesPerType"] == 300
    assert settings["maxCandidatesPerTimeBucket"] == 25
    assert settings["enableTranscriptPostProcessing"] is False
    assert settings["candidateTimeBucketSeconds"] == 120.0
    assert settings["maxCandidateGenerationMemoryMb"] == 2048
    assert settings["candidateChunkSeconds"] == 300.0
    assert settings["candidateChunkOverlapSeconds"] == 75.0

    high_quality_args = script.parse_args(["--video", "spoken.mp4", "--mode", "high_quality"])
    assert script.build_job_settings(high_quality_args)["useOpenAIScoring"] is True
    assert script.build_job_settings(high_quality_args)["ensureSelectedOpenAIScored"] is True

    disabled_args = script.parse_args(
        ["--video", "spoken.mp4", "--mode", "high_quality", "--use-openai-scoring", "false"]
    )
    assert script.build_job_settings(disabled_args)["useOpenAIScoring"] is False

    invalid_args = script.parse_args(
        ["--video", "spoken.mp4", "--normal-min-duration", "60", "--normal-max-duration", "20"]
    )
    with pytest.raises(RuntimeError, match="normal-max-duration"):
        script.build_job_settings(invalid_args)


def test_build_job_settings_loads_transcript_replacements_json(tmp_path: Path) -> None:
    replacements_path = tmp_path / "replacements.json"
    replacements_path.write_text(json.dumps({"オープンAI": "OpenAI"}), encoding="utf-8")

    args = script.parse_args(
        [
            "--video",
            "spoken.mp4",
            "--enable-transcript-post-processing",
            "true",
            "--transcript-replacements-json",
            str(replacements_path),
        ]
    )

    settings = script.build_job_settings(args)

    assert settings["enableTranscriptPostProcessing"] is True
    assert settings["transcriptReplacements"] == {"オープンAI": "OpenAI"}


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
    assert metrics["subtitle_correction_time"] is None
    assert metrics["scene_detection_time"] == pytest.approx(0.5)
    assert metrics["candidate_generation_time"] == pytest.approx(4.0)
    assert metrics["scoring_time"] == pytest.approx(2.5)
    assert metrics["selection_time"] == pytest.approx(7.5)
    assert metrics["normal_render_time"] == pytest.approx(5.0)
    assert metrics["short_render_time"] == pytest.approx(9.0)
    assert metrics["zip_packaging_time"] == pytest.approx(1.0)
    assert metrics["render_time"] == pytest.approx(14.0)
    assert metrics["total_time"] == 50.0
    assert script.format_seconds(None) == "n/a"
    assert script.format_seconds(1.23456) == "1.235s"


def test_runtime_metrics_separate_subtitle_correction_time() -> None:
    timing = script.TimedJobResult(
        final_status={"status": "completed"},
        status_times={
            "transcribing": 10.0,
            "correcting_subtitles": 15.0,
            "detecting_scenes": 35.0,
            "completed": 40.0,
        },
        poll_started_at=9.0,
        poll_finished_at=40.0,
    )

    metrics = script.runtime_metrics(upload_seconds=1.0, job_timing=timing, total_seconds=41.0)

    assert metrics["transcription_time"] == pytest.approx(5.0)
    assert metrics["subtitle_correction_time"] == pytest.approx(20.0)


def test_pipeline_metrics_read_diagnostic_summaries(tmp_path: Path) -> None:
    (tmp_path / "video_metadata.json").write_text(
        json.dumps({"duration": 1812.5, "width": 1280, "height": 720}),
        encoding="utf-8",
    )
    (tmp_path / "transcript_summary.json").write_text(
        json.dumps({"segment_count": 8, "total_text_length": 420}),
        encoding="utf-8",
    )
    (tmp_path / "candidate_summary.json").write_text(
        json.dumps(
            {
                "total_candidates": 42,
                "short_candidates": 30,
                "normal_candidates": 12,
                "hard_gate_passed_count": 35,
                "hard_gate_rejected_count": 7,
                "requested_normal_count": 2,
                "requested_short_count": 3,
                "selected_below_threshold_backfill_count": 2,
                "time_cluster_count": {"normal": 4, "short": 6},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "candidate_generation_summary.json").write_text(
        json.dumps(
            {
                "chunks_processed": 6,
                "raw_candidates_considered": 12000,
                "candidates_kept_by_type": {"normal": 12, "short": 30},
                "candidates_dropped_due_to_cap": 500,
                "candidates_dropped_due_to_duplicate": 25,
                "peak_memory_mb": 512.5,
                "memory_guard_triggered": False,
                "configured_caps": {"maxRawCandidatesPerType": 250000},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "selected_clips_summary.json").write_text(
        json.dumps(
            {
                "requested_normal_count": 2,
                "requested_short_count": 3,
                "selected_normal_count": 1,
                "selected_short_count": 2,
                "selected_below_threshold_backfill_count": 1,
                "overlap_relaxed_count": 1,
                "high_overlap_rejected_by_type": {"normal": 8},
                "cross_type_overlap_rejected_count": 0,
                "unfilled_requested_counts": {"normal": 1, "short": 1},
                "unfilled_reason_counts": {"normal": {"high_overlap": 8}},
                "time_cluster_count": {"normal": 4, "short": 6},
                "selected_clusters": {"normal": [0], "short": [1, 2]},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "rejection_summary.json").write_text(
        json.dumps({"render_failure_count": 1, "high_overlap_rejected_by_type": {"short": 1}}),
        encoding="utf-8",
    )
    (tmp_path / "download.zip").write_bytes(b"zip-bytes")

    metrics = script.pipeline_metrics(tmp_path)

    assert metrics == {
        "video_duration": 1812.5,
        "transcript_segment_count": 8,
        "total_transcript_text_length": 420,
        "total_candidates_count": 42,
        "short_candidates_count": 30,
        "normal_candidates_count": 12,
        "candidate_generation_chunks_processed": 6,
        "candidate_generation_raw_considered": 12000,
        "candidate_generation_kept_by_type": {"normal": 12, "short": 30},
        "candidate_generation_dropped_due_to_cap": 500,
        "candidate_generation_dropped_due_to_duplicate": 25,
        "candidate_generation_peak_memory_mb": 512.5,
        "candidate_generation_memory_guard_triggered": False,
        "candidate_generation_caps": {"maxRawCandidatesPerType": 250000},
        "hard_gate_passed_count": 35,
        "hard_gate_rejected_count": 7,
        "requested_normal_count": 2,
        "selected_normal_count": 1,
        "requested_short_count": 3,
        "selected_short_count": 2,
        "selected_normal_ratio": "1/2",
        "selected_short_ratio": "2/3",
        "backfilled_count": 1,
        "overlap_relaxed_count": 1,
        "overlap_relaxation_used": True,
        "high_overlap_rejected_by_type": {"normal": 8},
        "cross_type_overlap_rejected_count": 0,
        "unfilled_requested_counts": {"normal": 1, "short": 1},
        "unfilled_reason_counts": {"normal": {"high_overlap": 8}},
        "time_cluster_count": {"normal": 4, "short": 6},
        "selected_clusters": {"normal": [0], "short": [1, 2]},
        "render_failures_count": 1,
        "zip_size_bytes": 9,
    }


def test_validate_openai_scoring_summary_requires_successful_api_scores(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="openai_scoring_summary.json not found"):
        script.validate_openai_scoring_summary(tmp_path)

    summary_path = tmp_path / "openai_scoring_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "model": "gpt-test",
                "candidates_sent_to_openai": 2,
                "successful_scores": 0,
                "failed_scores": 2,
                "fallback_scores": 2,
                "total_api_calls": 2,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="zero successful"):
        script.validate_openai_scoring_summary(tmp_path)

    summary_path.write_text(
        json.dumps(
            {
                "model": "gpt-test",
                "candidate_limit": 20,
                "finalist_scoring_limit": 7,
                "candidates_eligible_for_openai_scoring": 12,
                "candidates_selected_for_openai": 2,
                "candidates_sent_preselection": 2,
                "candidates_sent_as_finalists": 1,
                "candidates_sent_to_openai": 2,
                "successful_scores": 1,
                "failed_scores": 1,
                "fallback_scores": 1,
                "schema_validation_failures": 0,
                "total_api_calls": 2,
                "avg_latency_seconds": 0.25,
                "max_latency_seconds": 0.4,
                "total_latency_seconds": 0.5,
                "estimated_text_payload_size": 1024,
                "selected_ai_score_count": 1,
                "selected_fallback_score_count": 0,
                "selected_not_scored_count": 0,
                "selected_not_scored_reason_counts": {},
                "selected_rule_score_only_due_to_limit_count": 1,
            }
        ),
        encoding="utf-8",
    )
    payload = script.validate_openai_scoring_summary(tmp_path)
    assert payload["successful_scores"] == 1
    assert payload["selected_ai_score_count"] == 1


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

    with pytest.raises(RuntimeError, match="invalid dimensions"):
        script.validate_output_probe(
            {"type": "normal", "duration": 25.0},
            tmp_path / "bad_dimensions.mp4",
            script.ProbeResult(width=0, height=720, duration=25.0),
        )


def test_validate_required_result_artifacts(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="required result artifacts missing"):
        script.validate_required_result_artifacts(tmp_path)

    for filename in script.REQUIRED_RESULT_ARTIFACTS:
        (tmp_path / filename).write_text("{}", encoding="utf-8")

    script.validate_required_result_artifacts(tmp_path)


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
    (output_dir / "transcript_postprocess_summary.json").write_text(
        json.dumps(
            {
                "enabled": True,
                "changed_segment_count": 1,
                "total_chars_before": 82,
                "total_chars_after": 80,
                "replacement_counts": {"オープンAI": 1},
                "used_default_dictionary": True,
                "custom_replacement_count": 0,
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
    postprocess_line = e2e_summary.summary_line(
        "transcript_postprocess_summary.json",
        {
            "enabled": True,
            "changed_segment_count": 1,
            "total_chars_before": 82,
            "total_chars_after": 80,
            "replacement_counts": {"オープンAI": 1},
            "used_default_dictionary": True,
            "custom_replacement_count": 0,
        },
    )
    assert "changed_segments=1" in postprocess_line
    assert "オープンAI" in postprocess_line
    correction_line = e2e_summary.summary_line(
        "transcript_correction_summary.json",
        {
            "enabled": True,
            "model": "gpt-5.5",
            "corrected_segment_count": 3,
            "unchanged_segment_count": 17,
            "low_confidence_rejected_count": 1,
            "safety_rejected_count": 2,
            "fallback_used": False,
            "api_call_count": 2,
            "schema_validation_failures": 0,
            "processing_seconds": 1.25,
        },
    )
    assert "model=gpt-5.5" in correction_line
    assert "corrected=3" in correction_line
    assert "safety_rejected=2" in correction_line
    assert "fallback=False" in correction_line
    assert "calls=2" in correction_line
    openai_line = e2e_summary.summary_line(
        "openai_scoring_summary.json",
        {
            "model": "gpt-test",
            "candidate_limit": 20,
            "finalist_scoring_limit": 7,
            "candidates_eligible_for_openai_scoring": 40,
            "candidates_selected_for_openai": 20,
            "candidates_sent_preselection": 20,
            "candidates_sent_as_finalists": 2,
            "candidates_sent_to_openai": 18,
            "successful_scores": 17,
            "failed_scores": 1,
            "fallback_scores": 1,
            "schema_validation_failures": 0,
            "total_api_calls": 18,
            "avg_latency_seconds": 0.2,
            "max_latency_seconds": 0.5,
            "selected_ai_score_count": 2,
            "selected_fallback_score_count": 0,
            "selected_not_scored_count": 0,
        },
    )
    assert "limit=20" in openai_line
    assert "finalists=2" in openai_line
    assert "selected_ai=2" in openai_line
    candidate_generation_line = e2e_summary.summary_line(
        "candidate_generation_summary.json",
        {
            "video_duration": 3600,
            "transcript_segment_count": 2000,
            "chunks_processed": 12,
            "raw_candidates_considered": 50000,
            "candidates_kept_by_type": {"normal": 1200, "short": 1200},
            "candidates_dropped_due_to_cap": 48000,
            "candidates_dropped_due_to_duplicate": 100,
            "peak_memory_mb": 640.5,
            "memory_guard_triggered": False,
        },
    )
    assert "chunks=12" in candidate_generation_line
    assert "raw=50000" in candidate_generation_line
    assert "memory_guard=False" in candidate_generation_line

    e2e_summary.print_job_summaries(job_id, root=tmp_path)
    output = capsys.readouterr().out
    assert "transcript_summary.json: segments=2" in output
    assert "transcript_postprocess_summary.json: enabled=True" in output
    assert "candidate_summary.json: total=12" in output
    assert "audio_feature_summary.json: missing" in output
