from pathlib import Path

import pytest

from app.render.paired_preview import paired_preview_command
from app.render.render_short import build_render_short_command


@pytest.mark.parametrize("banners", [False, True])
@pytest.mark.parametrize("hook", [False, True])
@pytest.mark.parametrize("normalize", [False, True])
def test_pair_preserves_trim_audio_and_shared_composition(
    tmp_path: Path, banners: bool, hook: bool, normalize: bool,
) -> None:
    command = build_render_short_command(
        "source.mp4", "exact.mp4", start=10, end=13,
        layout="blur_background", source_width=1920, source_height=1080,
        top_banner_path="top.png" if banners else None,
        bottom_banner_path="bottom.png" if banners else None,
        hook_scene_start=20 if hook else None,
        hook_scene_end=21 if hook else None,
        normalize_audio=normalize,
    )
    paired = paired_preview_command(
        command, live_output_path="live.mp4", subtitle_path=tmp_path / "text.ass",
    )
    graph = paired[paired.index("-filter_complex") + 1]
    assert graph.count("ass=") == 1
    assert "split=2[paired_clean][paired_text]" in graph
    assert paired.count("source.mp4") == (2 if hook else 1)
    assert paired.count("libx264") == 2
    assert paired.count("20") == 2  # Same CRF as the final renderer.
    outputs = paired[paired.index("-filter_complex") + 2:]
    exact, live = outputs[:outputs.index("exact.mp4")], outputs[outputs.index("exact.mp4") + 1:]
    if hook:
        assert "asplit=2" in graph
    else:
        for output in (exact, live):
            assert output[output.index("-t") + 1] == "3.000"
            assert "0:a?" in output
            assert ("-af" in output) == normalize
    assert paired[-1] == "live.mp4"
