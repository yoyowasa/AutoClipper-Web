import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import v1_smoke_check  # noqa: E402


def test_parse_args_defaults() -> None:
    args = v1_smoke_check.parse_args([])

    assert args.backend_url == "http://localhost:8000"
    assert args.frontend_url == "http://localhost:3000"
    assert args.job_id is None
    assert args.timeout == 15.0
    assert args.skip_frontend is False


def test_join_backend_url_handles_relative_and_absolute() -> None:
    assert v1_smoke_check.join_backend_url("http://localhost:8000/", "/api/health") == "http://localhost:8000/api/health"
    assert (
        v1_smoke_check.join_backend_url("http://localhost:8000", "http://example.test/file")
        == "http://example.test/file"
    )


def test_scan_sidecar_autoload_risks_detects_same_basename_subtitles(tmp_path: Path) -> None:
    output_dir = tmp_path / "storage" / "outputs" / "job_test"
    shorts = output_dir / "shorts"
    subtitles = output_dir / "subtitles" / "shorts"
    shorts.mkdir(parents=True)
    subtitles.mkdir(parents=True)
    (shorts / "short_01.mp4").write_bytes(b"mp4")
    (shorts / "short_01.ass").write_text("[Script Info]\n", encoding="utf-8")
    (subtitles / "short_02.ass").write_text("[Script Info]\n", encoding="utf-8")

    risks = v1_smoke_check.scan_sidecar_autoload_risks(output_dir)

    assert risks == [
        {
            "video_path": str(shorts / "short_01.mp4"),
            "subtitle_path": str(shorts / "short_01.ass"),
        }
    ]


def test_first_clip_prefers_normal_then_shorts() -> None:
    results = {
        "normalClips": [{"id": "normal_1"}],
        "shorts": [{"id": "short_1"}],
    }

    assert v1_smoke_check.first_clip(results) == {"id": "normal_1"}
    assert v1_smoke_check.first_clip({"normalClips": [], "shorts": [{"id": "short_1"}]}) == {"id": "short_1"}
    assert v1_smoke_check.first_clip({"normalClips": [], "shorts": []}) is None


def test_build_summary_marks_failure() -> None:
    args = v1_smoke_check.parse_args(["--job-id", "job_test"])
    checks = [
        {"name": "ok", "status": "pass", "detail": "ok", "data": {}},
        {"name": "bad", "status": "fail", "detail": "bad", "data": {}},
    ]

    summary = v1_smoke_check.build_summary(args, checks)

    assert summary["job_id"] == "job_test"
    assert summary["failed"] is True
