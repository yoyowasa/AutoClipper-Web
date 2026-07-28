from pathlib import Path
from types import SimpleNamespace

from app.render import render_review_preview


def test_review_preview_command_builds_small_browser_ready_mp4(tmp_path: Path) -> None:
    output_path = tmp_path / "preview.mp4"

    command = render_review_preview.build_review_preview_command(
        "source.mp4",
        output_path,
        start=123.456,
        duration=42.0,
    )

    assert command[:2] == ["ffmpeg", "-hide_banner"]
    assert command[command.index("-ss") + 1] == "123.456000"
    assert command[command.index("-t") + 1] == "42.000000"
    assert command[command.index("-vf") + 1] == (
        "fps=30,scale=960:540:force_original_aspect_ratio=decrease"
    )
    assert command[command.index("-preset") + 1] == "ultrafast"
    assert command[command.index("-movflags") + 1] == "+faststart"
    assert command[-1] == str(output_path)


def test_review_preview_command_prepends_hook_scene() -> None:
    command = render_review_preview.build_review_preview_command(
        "source.mp4",
        "preview.mp4",
        start=60.0,
        duration=15.0,
        hook_start=68.0,
        hook_duration=2.0,
    )

    seek_values = [
        command[index + 1]
        for index, value in enumerate(command)
        if value == "-ss"
    ]
    duration_values = [
        command[index + 1]
        for index, value in enumerate(command)
        if value == "-t"
    ]
    filter_graph = command[command.index("-filter_complex") + 1]

    assert seek_values == ["68.000000", "60.000000"]
    assert duration_values == ["2.000000", "15.000000"]
    assert "concat=n=2:v=1:a=1[video][audio]" in filter_graph
    assert command.count("-i") == 2


def test_review_preview_render_replaces_target_atomically(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_path = tmp_path / "preview.mp4"

    def fake_run(command: list[str], *, check: bool):
        assert check is True
        Path(command[-1]).write_bytes(b"preview")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(render_review_preview.subprocess, "run", fake_run)

    result = render_review_preview.render_review_preview(
        "source.mp4",
        output_path,
        start=10.0,
        duration=20.0,
    )

    assert result == output_path
    assert output_path.read_bytes() == b"preview"
    assert not (tmp_path / "preview.tmp.mp4").exists()
