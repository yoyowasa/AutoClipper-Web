import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import audit_outputs  # noqa: E402


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_ass(path: Path, *, dense: bool = False) -> None:
    text = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    if dense:
        text += (
            "Dialogue: 0,0:00:00.00,0:00:02.00,Subtitle,,0,0,0,,"
            "This subtitle line is intentionally too long and dense for the available display time\n"
        )
    else:
        text += "Dialogue: 0,0:00:00.00,0:00:03.00,Subtitle,,0,0,0,,Readable subtitle\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_audit_job(root: Path, job_id: str) -> Path:
    output_dir = root / "storage" / "outputs" / job_id
    selected = {
        "normalClips": [
            {
                "id": "normal_1",
                "type": "normal",
                "start": 10.0,
                "end": 90.0,
                "duration": 80.0,
                "transcript_text": "だから短い",
                "transcript_char_count": 5,
                "rule_score": 55.0,
                "ai_score": None,
                "final_score": 55.0,
                "title": None,
                "selection_reason": "backfill_below_quality_threshold",
                "below_quality_threshold": True,
                "quality_warning": "below_min_final_score",
                "used_ai_score": False,
                "openai_fallback_used": False,
            }
        ],
        "shorts": [
            {
                "id": "short_1",
                "type": "short",
                "start": 100.0,
                "end": 118.0,
                "duration": 18.0,
                "transcript_text": "Clear short transcript text for the clip.",
                "transcript_char_count": 38,
                "rule_score": 70.0,
                "ai_score": None,
                "final_score": 70.0,
                "title": None,
                "overlay_title": None,
                "selection_reason": "above_quality_threshold",
                "below_quality_threshold": False,
                "used_ai_score": False,
                "openai_fallback_used": False,
            }
        ],
    }
    write_json(output_dir / "selected_clips.json", selected)
    write_json(
        output_dir / "selected_clips_summary.json",
        {
            "selected_normal_count": 1,
            "selected_short_count": 1,
            "requested_normal_count": 1,
            "requested_short_count": 1,
        },
    )
    write_json(
        output_dir / "candidate_summary.json",
        {
            "total_candidates": 2,
            "selected_normal_count": 1,
            "selected_short_count": 1,
        },
    )
    write_json(
        output_dir / "openai_scoring_summary.json",
        {
            "model": "gpt-test",
            "selected_ai_score_count": 0,
            "selected_not_scored_count": 2,
        },
    )
    write_json(
        output_dir / "transcript_segments.json",
        [
            {"start": 9.5, "end": 13.0, "text": "だから短い"},
            {"start": 100.0, "end": 104.0, "text": "Clear first sentence."},
            {"start": 114.0, "end": 118.0, "text": "Clear ending."},
        ],
    )
    write_json(
        output_dir / "normal" / "normal_01.json",
        {
            "candidate_id": "normal_1",
            "type": "normal",
            "title": "Normal clip 1",
            "start": 10.0,
            "end": 90.0,
            "duration": 80.0,
            "width": 1280,
            "height": 720,
            "video_path": "/app/storage/outputs/job_audit/normal/normal_01.mp4",
            "subtitle_path": "/app/storage/outputs/job_audit/normal/normal_01.ass",
        },
    )
    write_json(
        output_dir / "shorts" / "short_01.json",
        {
            "candidate_id": "short_1",
            "type": "short",
            "title": "Short 1",
            "overlay_title": None,
            "start": 100.0,
            "end": 118.0,
            "duration": 18.0,
            "width": 720,
            "height": 1280,
            "video_path": "/app/storage/outputs/job_audit/shorts/short_01.mp4",
            "subtitle_path": "/app/storage/outputs/job_audit/shorts/short_01.ass",
        },
    )
    write_ass(output_dir / "normal" / "normal_01.ass", dense=True)
    return output_dir


def test_audit_outputs_builds_quality_report(tmp_path: Path) -> None:
    write_audit_job(tmp_path, "job_audit")

    report = audit_outputs.build_audit_report("job_audit", root=tmp_path)

    summary = report["aggregate_summary"]
    assert summary["generated_normal_count"] == 1
    assert summary["generated_short_count"] == 1
    assert summary["clips_requiring_human_visual_inspection_count"] == 2
    assert summary["warnings_by_type"]["normal"]["very_short_transcript_text"] == 1
    assert summary["warnings_by_type"]["normal"]["subtitle_too_dense"] == 1
    assert summary["warnings_by_type"]["normal"]["backfilled_clip"] == 1
    assert "missing_title" not in summary["warnings_by_type"]["normal"]
    assert summary["warnings_by_type"]["short"]["short_resolution_not_1080x1920"] == 1
    assert summary["warnings_by_type"]["short"]["no_subtitle_file"] == 1
    assert summary["warnings_by_type"]["short"]["rule_only_clip_in_high_quality_mode"] == 1
    assert "missing_title" not in summary["warnings_by_type"]["short"]

    normal_clip = report["clips"][0]
    short_clip = report["clips"][1]
    assert normal_clip["first_transcript_text"] == "だから短い"
    assert normal_clip["resolution"]["width"] == 1280
    assert normal_clip["title"] == "だから短い"
    assert normal_clip["title_source"] == "transcript_fallback"
    assert "missing_title" not in normal_clip["warnings"]
    assert short_clip["resolution"]["height"] == 1280
    assert short_clip["title"] == "Clear short transcript text for the clip"
    assert short_clip["title_source"] == "transcript_fallback"
    assert short_clip["overlay_title"] == "Clear short transcript text for the clip"
    assert "missing_overlay_title" not in short_clip["warnings"]


def test_audit_outputs_prefers_metadata_title_when_selected_title_is_generic(tmp_path: Path) -> None:
    output_dir = write_audit_job(tmp_path, "job_audit")
    selected_path = output_dir / "selected_clips.json"
    selected = json.loads(selected_path.read_text(encoding="utf-8"))
    selected["normalClips"][0]["title"] = "Normal clip 1"
    write_json(selected_path, selected)
    metadata_path = output_dir / "normal" / "normal_01.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["title"] = "Metadata real title"
    metadata["title_source"] = "openai"
    write_json(metadata_path, metadata)

    report = audit_outputs.build_audit_report("job_audit", root=tmp_path)

    normal_clip = report["clips"][0]
    assert normal_clip["title"] == "Metadata real title"
    assert normal_clip["title_source"] == "openai"
    assert "missing_title" not in normal_clip["warnings"]


def test_audit_outputs_writes_json_and_markdown(tmp_path: Path) -> None:
    write_audit_job(tmp_path, "job_audit")
    report = audit_outputs.build_audit_report("job_audit", root=tmp_path)
    paths = audit_outputs.output_paths(job_id="job_audit", output=None, output_format="both", root=tmp_path)

    written = audit_outputs.write_report(report, paths)

    assert paths.json_path in written
    assert paths.markdown_path in written
    assert paths.json_path == tmp_path / "storage" / "outputs" / "job_audit" / "audit" / "output_audit_report.json"
    assert paths.markdown_path == tmp_path / "storage" / "outputs" / "job_audit" / "audit" / "output_audit_report.md"
    assert json.loads(paths.json_path.read_text(encoding="utf-8"))["audit"]["job_id"] == "job_audit"
    markdown = paths.markdown_path.read_text(encoding="utf-8")
    assert "# AutoClipper Output Quality Audit" in markdown
    assert "subtitle_too_dense" in markdown
    assert "short_resolution_not_1080x1920" in markdown


def test_audit_outputs_output_path_suffixes(tmp_path: Path) -> None:
    both = audit_outputs.output_paths(
        job_id="job_audit",
        output=tmp_path / "custom.report",
        output_format="both",
        root=tmp_path,
    )
    assert both.json_path == tmp_path / "custom.json"
    assert both.markdown_path == tmp_path / "custom.md"

    markdown = audit_outputs.output_paths(
        job_id="job_audit",
        output=tmp_path / "custom.md",
        output_format="markdown",
        root=tmp_path,
    )
    assert markdown.json_path is None
    assert markdown.markdown_path == tmp_path / "custom.md"


def test_audit_outputs_requires_selected_artifact(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="selected_clips.json"):
        audit_outputs.build_audit_report("missing_job", root=tmp_path)
