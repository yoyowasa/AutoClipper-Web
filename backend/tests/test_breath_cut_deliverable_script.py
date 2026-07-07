import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import create_breath_cut_deliverable as script  # noqa: E402


def test_parse_args_allows_dry_run_without_source_container_path() -> None:
    args = script.parse_args(["--job-id", "job_test", "--dry-run"])

    assert args.job_id == "job_test"
    assert args.dry_run is True
    assert args.source_container_path is None
    assert args.docker_service == "worker"


def test_parse_args_requires_source_container_path_for_render() -> None:
    with pytest.raises(SystemExit):
        script.parse_args(["--job-id", "job_test"])


def test_cut_intervals_respects_protected_and_soft_cut_intervals() -> None:
    silences = [
        script.Interval(1.0, 2.0),
        script.Interval(4.0, 5.0),
        script.Interval(8.0, 9.0),
    ]
    transcripts = [
        script.Segment(0.0, 0.8, "start"),
        script.Segment(5.2, 6.0, "middle"),
    ]

    cuts = script.cut_intervals(
        silences,
        transcripts,
        min_cut_silence=0.35,
        keep_silence=0.1,
        speech_margin=0.04,
        protected_intervals=[script.Interval(4.5, 5.5)],
        soft_cut_intervals=[script.SoftCutInterval(8.0, 9.0, 0.4)],
    )

    assert cuts == [
        script.Interval(1.05, 1.95),
        script.Interval(8.2, 8.8),
    ]


def test_subtitle_events_map_times_after_cutting_silence() -> None:
    transcripts = [
        script.Segment(0.5, 1.5, "最初の短い字幕です"),
        script.Segment(3.0, 4.0, "後半の字幕です"),
    ]
    cuts = [script.Interval(1.5, 2.5)]

    events = script.subtitle_events(transcripts, cuts, duration=3.0, max_chars=22)

    assert [(event.start, event.end, event.text) for event in events] == [
        (0.5, 1.5, "最初の短い字幕です"),
        (2.0, 3.0, "後半の字幕です"),
    ]


def test_build_ffmpeg_command_uses_configured_docker_service() -> None:
    command = script.build_ffmpeg_command(
        "/app/storage/outputs/job_test/shorts/short_01.mp4",
        "/app/storage/outputs/job_test/breath_cut/filter_complex.txt",
        "/app/storage/outputs/job_test/breath_cut/short_01_breath_cut.mp4",
        docker_service="worker",
    )

    assert command[:6] == ["docker", "compose", "exec", "-T", "worker", "ffmpeg"]
    assert "-filter_complex_script" in command
    assert "/app/storage/outputs/job_test/breath_cut/filter_complex.txt" in command
    assert command[-1] == "/app/storage/outputs/job_test/breath_cut/short_01_breath_cut.mp4"
