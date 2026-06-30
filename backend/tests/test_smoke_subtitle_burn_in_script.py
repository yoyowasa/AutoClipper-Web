import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import smoke_subtitle_burn_in as script  # noqa: E402


def candidate_payload(
    *,
    candidate_id: str,
    candidate_type: str,
    start: float,
    end: float,
    transcript_text: str = "これは字幕焼き込み確認用の候補です。",
) -> dict[str, object]:
    return {
        "id": candidate_id,
        "type": candidate_type,
        "start": start,
        "end": end,
        "duration": round(end - start, 3),
        "transcript_text": transcript_text,
        "transcript_char_count": len(transcript_text),
        "speech_seconds": round(end - start, 3),
        "silence_ratio": 0.1,
        "rule_score": 70.0,
        "final_score": 70.0,
        "title": "確認用タイトル",
        "overlay_title": "確認用タイトル",
    }


def test_parse_args_defaults() -> None:
    args = script.parse_args([])

    assert args.source_job_id == script.DEFAULT_SOURCE_JOB_ID
    assert args.output_job_id is None
    assert args.input_video is None
    assert args.database_path == script.DEFAULT_DATABASE_PATH
    assert args.normal_count == 1
    assert args.short_count == 2
    assert args.normal_duration_limit == 120.0
    assert args.short_layout == "center_crop"
    assert args.ffmpeg_bin == "ffmpeg"
    assert args.ffprobe_bin == "ffprobe"
    assert args.docker_service is None
    assert args.mode is None
    assert args.openai_candidate_limit == 5
    assert args.timeout == 1800
    assert args.extract_short_frames is True
    assert args.run_audit is True


def test_host_path_from_artifact_resolves_container_storage(tmp_path: Path) -> None:
    resolved = script.host_path_from_artifact("/app/storage/uploads/video.mp4", root=tmp_path)

    assert resolved == tmp_path / "storage" / "uploads" / "video.mp4"
    assert script.host_path_from_artifact(None, root=tmp_path) is None
    assert script.host_path_from_artifact(str(tmp_path / "input.mp4"), root=tmp_path) == tmp_path / "input.mp4"


def test_container_path_from_host_storage_requires_storage_path(tmp_path: Path) -> None:
    source = tmp_path / "storage" / "uploads" / "video.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"")

    assert script.container_path_from_host_storage(source, root=tmp_path) == "/app/storage/uploads/video.mp4"


def test_selected_subset_applies_counts_and_normal_duration_limit() -> None:
    selected = {
        "normalClips": [
            candidate_payload(candidate_id="normal_1", candidate_type="normal", start=10.0, end=210.0),
            candidate_payload(candidate_id="normal_2", candidate_type="normal", start=300.0, end=420.0),
        ],
        "shorts": [
            candidate_payload(candidate_id="short_1", candidate_type="short", start=500.0, end=530.0),
            candidate_payload(candidate_id="short_2", candidate_type="short", start=600.0, end=630.0),
            candidate_payload(candidate_id="short_3", candidate_type="short", start=700.0, end=730.0),
        ],
    }

    subset = script.selected_subset(
        selected,
        normal_count=1,
        short_count=2,
        normal_duration_limit=90.0,
    )

    assert len(subset["normalClips"]) == 1
    assert len(subset["shorts"]) == 2
    assert subset["normalClips"][0]["id"] == "normal_1_burnin"
    assert subset["normalClips"][0]["end"] == 100.0
    assert subset["normalClips"][0]["duration"] == 90.0
    assert subset["shorts"][0]["id"] == "short_1"


def test_apply_overlay_title_policy_can_require_or_force_titles() -> None:
    subset = {
        "normalClips": [],
        "shorts": [
            candidate_payload(candidate_id="short_1", candidate_type="short", start=0.0, end=30.0),
            {
                **candidate_payload(candidate_id="short_2", candidate_type="short", start=40.0, end=70.0),
                "overlay_title": "",
            },
        ],
    }

    forced = script.apply_overlay_title_policy(
        subset,
        require_overlay_title=True,
        force_overlay_title="日本語タイトル{number}",
    )

    assert forced["shorts"][0]["overlay_title"] == "日本語タイトル01"
    assert forced["shorts"][1]["overlay_title"] == "日本語タイトル02"
    assert forced["shorts"][0]["source_overlay_title"] == "確認用タイトル"


def test_candidates_from_subset_and_container_output_path() -> None:
    subset = {
        "normalClips": [candidate_payload(candidate_id="normal_1", candidate_type="normal", start=0.0, end=120.0)],
        "shorts": [candidate_payload(candidate_id="short_1", candidate_type="short", start=200.0, end=230.0)],
    }

    normal_candidates, short_candidates = script.candidates_from_subset(subset)

    assert normal_candidates[0].id == "normal_1"
    assert normal_candidates[0].type == "normal"
    assert short_candidates[0].id == "short_1"
    assert short_candidates[0].type == "short"
    assert (
        script.container_output_path("job_test", "shorts", "short_01.mp4")
        == "/app/storage/outputs/job_test/shorts/short_01.mp4"
    )


def test_inspect_ass_layout_reports_safe_title_and_subtitle_positions(tmp_path: Path) -> None:
    layout = script.SubtitleLayout.short()
    path = tmp_path / "short.ass"
    path.write_text(
        "[Script Info]\n"
        "PlayResX: 1080\n"
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
        "Dialogue: 1,0:00:00.00,0:00:30.00,Title,,0,0,0,,日本語タイトル\n"
        "Dialogue: 0,0:00:01.00,0:00:03.00,Subtitle,,0,0,0,,日本語字幕\n",
        encoding="utf-8",
    )

    inspection = script.inspect_ass_layout(path, layout)

    assert inspection.title_style_exists is True
    assert inspection.subtitle_style_exists is True
    assert inspection.title_dialogue_count == 1
    assert inspection.subtitle_dialogue_count == 1
    assert inspection.title_subtitle_overlap is False
    assert inspection.safe_vertical_positions is True
