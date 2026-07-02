import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import audit_outputs  # noqa: E402
import check_subtitle_sidecar_risk  # noqa: E402


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
    (output_dir / "normal" / "normal_01.mp4").write_bytes(b"normal mp4")
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
    (output_dir / "shorts" / "short_01.mp4").write_bytes(b"short mp4")
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
    assert summary["warnings_by_type"]["normal"]["external_subtitle_autoload_risk"] == 1
    assert summary["warnings_by_type"]["short"]["short_resolution_not_1080x1920"] == 1
    assert summary["warnings_by_type"]["short"]["no_subtitle_file"] == 1
    assert summary["warnings_by_type"]["short"]["rule_only_clip_in_high_quality_mode"] == 1

    normal_clip = report["clips"][0]
    short_clip = report["clips"][1]
    assert normal_clip["first_transcript_text"] == "だから短い"
    assert normal_clip["resolution"]["width"] == 1280
    assert normal_clip["title"] == "Normal clip 1"
    assert "missing_title" not in normal_clip["warnings"]
    assert "generic_fallback_title" in normal_clip["warnings"]
    assert "external_subtitle_autoload_risk" in normal_clip["warnings"]
    assert normal_clip["external_subtitle_autoload_risk_files"]
    assert short_clip["resolution"]["height"] == 1280
    assert "missing_overlay_title" in short_clip["warnings"]


def test_audit_reports_no_sidecar_risk_for_separated_subtitle_layout(tmp_path: Path) -> None:
    output_dir = write_audit_job(tmp_path, "job_audit")
    subtitle_dir = output_dir / "subtitles" / "normal"
    subtitle_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "normal" / "normal_01.ass").replace(subtitle_dir / "normal_01.ass")
    normal_metadata = json.loads((output_dir / "normal" / "normal_01.json").read_text(encoding="utf-8"))
    normal_metadata["subtitle_path"] = "/app/storage/outputs/job_audit/subtitles/normal/normal_01.ass"
    write_json(output_dir / "normal" / "normal_01.json", normal_metadata)

    report = audit_outputs.build_audit_report("job_audit", root=tmp_path)
    normal_clip = next(clip for clip in report["clips"] if clip["type"] == "normal")

    assert "external_subtitle_autoload_risk" not in normal_clip["warnings"]
    assert normal_clip["external_subtitle_autoload_risk_files"] == []


def test_audit_reports_refined_boundaries_without_abrupt_false_positive(tmp_path: Path) -> None:
    output_dir = write_audit_job(tmp_path, "job_audit")
    selected = json.loads((output_dir / "selected_clips.json").read_text(encoding="utf-8"))
    selected["normalClips"][0].update(
        {
            "start": 9.5,
            "end": 90.0,
            "duration": 80.5,
            "original_start": 10.0,
            "original_end": 90.0,
            "refined_start": 9.5,
            "refined_end": 90.0,
            "boundary_refined": True,
            "boundary_refinement_reason": "start_to_transcript_segment_start",
            "boundary_expansion_seconds": 0.5,
            "transcript_text": "自然な開始",
            "transcript_char_count": 5,
        }
    )
    write_json(output_dir / "selected_clips.json", selected)
    write_json(
        output_dir / "transcript_segments.json",
        [{"start": 9.5, "end": 13.0, "text": "自然な開始"}],
    )

    report = audit_outputs.build_audit_report("job_audit", root=tmp_path)
    normal_clip = next(clip for clip in report["clips"] if clip["type"] == "normal")

    assert normal_clip["original_start"] == 10.0
    assert normal_clip["refined_start"] == 9.5
    assert normal_clip["boundary_refined"] is True
    assert normal_clip["boundary_refinement_reason"] == "start_to_transcript_segment_start"
    assert "likely_abrupt_start" not in normal_clip["warnings"]


def test_sidecar_risk_smoke_scan_reports_same_basename_subtitles(tmp_path: Path) -> None:
    output_dir = tmp_path / "storage" / "outputs" / "job_scan" / "shorts"
    output_dir.mkdir(parents=True)
    (output_dir / "short_01.mp4").write_bytes(b"mp4")
    (output_dir / "short_01.ass").write_text("subtitle", encoding="utf-8")
    separated_dir = tmp_path / "storage" / "outputs" / "job_scan" / "subtitles" / "shorts"
    separated_dir.mkdir(parents=True)
    (separated_dir / "short_02.ass").write_text("safe subtitle", encoding="utf-8")

    risks = check_subtitle_sidecar_risk.scan_sidecar_risks("job_scan", root=tmp_path)

    assert risks == [
        {
            "video_path": str(output_dir / "short_01.mp4"),
            "subtitle_path": str(output_dir / "short_01.ass"),
        }
    ]


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


def test_audit_subtitle_density_uses_readability_thresholds_and_samples(tmp_path: Path) -> None:
    dense_path = tmp_path / "dense.ass"
    readable_path = tmp_path / "readable.ass"
    dense_path.write_text(
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:00.00,0:00:02.00,Title,,0,0,0,,This title should not affect density\n"
        "Dialogue: 0,0:00:00.00,0:00:02.00,Subtitle,,0,0,0,,"
        "これは非常に長すぎる字幕で一度に読むには密度が高すぎます\n",
        encoding="utf-8",
    )
    readable_path.write_text(
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:00.00,0:00:02.20,Subtitle,,0,0,0,,これは読みやすい\\N字幕です\n"
        "Dialogue: 0,0:00:02.30,0:00:04.50,Subtitle,,0,0,0,,次の字幕も\\N短めです\n",
        encoding="utf-8",
    )

    dense = audit_outputs.analyze_ass_subtitles(dense_path, clip_type="short")
    readable = audit_outputs.analyze_ass_subtitles(readable_path, clip_type="short")

    assert dense["dialogue_count"] == 1
    assert dense["subtitle_too_dense"] is True
    assert dense["density_reasons"]
    assert dense["worst_density_samples"][0]["text"].startswith("これは非常に")
    assert readable["subtitle_too_dense"] is False
    assert readable["density_reasons"] == []


def test_audit_detects_ass_title_layout_and_japanese_font(tmp_path: Path) -> None:
    path = tmp_path / "short.ass"
    path.write_text(
        "[Script Info]\n"
        "PlayResY: 1920\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Subtitle,Noto Sans CJK JP,76,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,"
        "1,0,0,0,100,100,0,0,1,5,2,2,86,86,250,1\n"
        "Style: Title,Noto Sans CJK JP,88,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,"
        "1,0,0,0,100,100,0,0,1,5,2,8,86,86,150,1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 1,0:00:00.00,0:00:10.00,Title,,0,0,0,,日本語タイトル\n"
        "Dialogue: 0,0:00:01.00,0:00:03.00,Subtitle,,0,0,0,,読みやすい字幕\n",
        encoding="utf-8",
    )

    subtitle = audit_outputs.analyze_ass_subtitles(path, clip_type="short")

    assert subtitle["title_dialogue_count"] == 1
    assert subtitle["dialogue_count"] == 1
    assert subtitle["font_supports_japanese"] is True
    assert subtitle["title_subtitle_vertical_overlap"] is False
    assert subtitle["title_subtitle_vertical_gap"] and subtitle["title_subtitle_vertical_gap"] > 0


def test_audit_warns_when_overlay_title_has_no_ass_title_event(tmp_path: Path) -> None:
    output_dir = write_audit_job(tmp_path, "job_audit")
    short_metadata = json.loads((output_dir / "shorts" / "short_01.json").read_text(encoding="utf-8"))
    short_metadata["overlay_title"] = "日本語タイトル"
    write_json(output_dir / "shorts" / "short_01.json", short_metadata)
    selected = json.loads((output_dir / "selected_clips.json").read_text(encoding="utf-8"))
    selected["shorts"][0]["overlay_title"] = "日本語タイトル"
    write_json(output_dir / "selected_clips.json", selected)
    write_json(output_dir / "openai_scoring_summary.json", {"model": "gpt-test"})
    write_ass(output_dir / "shorts" / "short_01.ass", dense=False)

    report = audit_outputs.build_audit_report("job_audit", root=tmp_path)
    short_clip = next(clip for clip in report["clips"] if clip["type"] == "short")

    assert "missing_ass_title_event" in short_clip["warnings"]


def test_audit_does_not_report_missing_title_when_fallback_title_exists(tmp_path: Path) -> None:
    output_dir = write_audit_job(tmp_path, "job_audit")
    selected = json.loads((output_dir / "selected_clips.json").read_text(encoding="utf-8"))
    selected["normalClips"][0]["title"] = "物価上昇で投資判断が変わる場面"
    selected["normalClips"][0]["title_source"] = "transcript_fallback"
    write_json(output_dir / "selected_clips.json", selected)
    normal_metadata = json.loads((output_dir / "normal" / "normal_01.json").read_text(encoding="utf-8"))
    normal_metadata["title"] = "物価上昇で投資判断が変わる場面"
    normal_metadata["title_source"] = "transcript_fallback"
    write_json(output_dir / "normal" / "normal_01.json", normal_metadata)

    report = audit_outputs.build_audit_report("job_audit", root=tmp_path)
    normal_clip = next(clip for clip in report["clips"] if clip["type"] == "normal")

    assert normal_clip["title"] == "物価上昇で投資判断が変わる場面"
    assert normal_clip["title_source"] == "transcript_fallback"
    assert "missing_title" not in normal_clip["warnings"]
    assert "generic_fallback_title" not in normal_clip["warnings"]


def test_audit_reports_generic_fallback_title_without_missing_title(tmp_path: Path) -> None:
    output_dir = write_audit_job(tmp_path, "job_audit")
    selected = json.loads((output_dir / "selected_clips.json").read_text(encoding="utf-8"))
    selected["shorts"][0]["title"] = "Short 01"
    selected["shorts"][0]["title_source"] = "deterministic_fallback"
    write_json(output_dir / "selected_clips.json", selected)
    short_metadata = json.loads((output_dir / "shorts" / "short_01.json").read_text(encoding="utf-8"))
    short_metadata["title"] = "Short 01"
    short_metadata["title_source"] = "deterministic_fallback"
    write_json(output_dir / "shorts" / "short_01.json", short_metadata)

    report = audit_outputs.build_audit_report("job_audit", root=tmp_path)
    short_clip = next(clip for clip in report["clips"] if clip["type"] == "short")

    assert short_clip["title_source"] == "deterministic_fallback"
    assert "missing_title" not in short_clip["warnings"]
    assert "generic_fallback_title" in short_clip["warnings"]


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
