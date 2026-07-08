import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import create_insert_image_deliverable as script  # noqa: E402


def test_parse_args_allows_dry_run_without_source_container_path(tmp_path: Path) -> None:
    base_filter = tmp_path / "filter.txt"
    subtitle = tmp_path / "subtitle.ass"
    image = tmp_path / "image.png"
    base_filter.write_text("[vcat]ass='subtitle.ass'[vout]\n", encoding="utf-8")
    subtitle.write_text("", encoding="utf-8")
    image.write_bytes(b"image")

    args = script.parse_args(
        [
            "--job-id",
            "job_test",
            "--base-filter",
            str(base_filter),
            "--subtitle",
            str(subtitle),
            "--image",
            str(image),
            "insert_01.png",
            "0.5",
            "2.0",
            "label",
            "--dry-run",
        ]
    )

    assert args.job_id == "job_test"
    assert args.dry_run is True
    assert args.source_container_path is None
    assert args.docker_service == "worker"
    assert args.duration is None


def test_parse_args_requires_source_container_path_for_render(tmp_path: Path) -> None:
    base_filter = tmp_path / "filter.txt"
    subtitle = tmp_path / "subtitle.ass"
    image = tmp_path / "image.png"
    base_filter.write_text("[vcat]ass='subtitle.ass'[vout]\n", encoding="utf-8")
    subtitle.write_text("", encoding="utf-8")
    image.write_bytes(b"image")

    with pytest.raises(SystemExit):
        script.parse_args(
            [
                "--job-id",
                "job_test",
                "--base-filter",
                str(base_filter),
                "--subtitle",
                str(subtitle),
                "--image",
                str(image),
                "insert_01.png",
                "0.5",
                "2.0",
                "label",
            ]
        )


def test_parse_insert_images_rejects_unsafe_asset_name(tmp_path: Path) -> None:
    image = tmp_path / "image.png"
    image.write_bytes(b"image")

    with pytest.raises(ValueError, match="asset name"):
        script.parse_insert_images([[str(image), "../insert_01.png", "0.5", "2.0", "label"]])


def test_read_base_filter_removes_final_ass_line(tmp_path: Path) -> None:
    base_filter = tmp_path / "filter.txt"
    base_filter.write_text(
        "[0:v]trim=start=0:end=3,setpts=PTS-STARTPTS[v0]\n"
        "[0:a]atrim=start=0:end=3,asetpts=PTS-STARTPTS[a0]\n"
        "[v0][a0]concat=n=1:v=1:a=1[vcat][acat]\n"
        "[vcat]ass='/app/storage/outputs/job/subtitles/shorts/short_01.ass'[vout]\n",
        encoding="utf-8",
    )

    lines = script.read_base_filter(base_filter)

    assert lines == [
        "[0:v]trim=start=0:end=3,setpts=PTS-STARTPTS[v0]",
        "[0:a]atrim=start=0:end=3,asetpts=PTS-STARTPTS[a0]",
        "[v0][a0]concat=n=1:v=1:a=1[vcat][acat]",
    ]


def test_build_filter_adds_insert_overlay_before_subtitles(tmp_path: Path) -> None:
    insert = script.InsertImage(
        source=tmp_path / "image.png",
        asset_name="insert_01.png",
        start=0.5,
        end=2.0,
        label="label",
    )
    filter_document = script.build_filter(
        ["[v0][a0]concat=n=1:v=1:a=1[vcat][acat]"],
        [insert],
        [tmp_path / "insert_01.png"],
        "/app/storage/outputs/job/subtitles/shorts/short_01.ass",
        "/app/storage/fonts",
    )

    assert "overlay=x=0:y=0:enable='between(t,0.500,2.000)'" in filter_document
    assert "[vins1]ass='/app/storage/outputs/job/subtitles/shorts/short_01.ass':fontsdir='/app/storage/fonts'[vout]" in filter_document


def test_build_ffmpeg_command_uses_configured_docker_service() -> None:
    command = script.build_ffmpeg_command(
        "/app/storage/outputs/job/shorts/short_01.mp4",
        ["/app/storage/outputs/job/inserts/assets/insert_01.png"],
        "/app/storage/outputs/job/inserts/filter_complex_insert_p0.txt",
        "/app/storage/outputs/job/inserts/short_01_insert_p0.mp4",
        12.5,
        docker_service="worker",
    )

    assert command[:6] == ["docker", "compose", "exec", "-T", "worker", "ffmpeg"]
    assert command.count("-loop") == 1
    assert command[-1] == "/app/storage/outputs/job/inserts/short_01_insert_p0.mp4"


def test_build_contact_sheet_command_handles_single_frame_without_xstack() -> None:
    command = script.build_contact_sheet_command(
        ["/app/storage/outputs/job/inserts/insert_frame_01.jpg"],
        "/app/storage/outputs/job/inserts/insert_contact_sheet.jpg",
        docker_service="worker",
    )

    assert command[:6] == ["docker", "compose", "exec", "-T", "worker", "ffmpeg"]
    assert "-vf" in command
    assert "scale=360:640" in command
    assert all("xstack" not in part for part in command)
    assert command[-1] == "/app/storage/outputs/job/inserts/insert_contact_sheet.jpg"


def test_duration_from_probe_reads_format_duration() -> None:
    assert script.duration_from_probe({"format": {"duration": "12.345"}}) == 12.345

    with pytest.raises(ValueError, match="format.duration"):
        script.duration_from_probe({"format": {}})
