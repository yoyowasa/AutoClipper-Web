from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import pytest

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.merge_boundaries import Candidate
from app.render.render_exact_review_preview import (
    EXACT_SUBTITLE_REVIEW_RENDERER_VERSION,
    FILESYSTEM_SPEC_HASH_LENGTH,
    LIVE_SUBTITLE_REVIEW_RENDERER_VERSION,
    build_live_subtitle_review_preview_spec,
    build_subtitle_review_preview_spec,
    exact_subtitle_review_preview_paths,
    live_subtitle_review_preview_paths,
    render_exact_subtitle_review_preview,
    subtitle_review_preview_spec_hash,
)
from app.render.render_short import (
    DEFAULT_SHORT_BOTTOM_BANNER_PATH,
    DEFAULT_SHORT_TOP_BANNER_PATH,
)


def make_candidate(
    candidate_id: str,
    candidate_type: str,
    *,
    start: float = 10.0,
    end: float = 20.0,
) -> Candidate:
    return Candidate(
        id=candidate_id,
        type=candidate_type,  # type: ignore[arg-type]
        start=start,
        end=end,
        duration=end - start,
        transcript_text="candidate transcript",
    )


def test_exact_preview_spec_is_canonical_and_ignores_unrelated_segments() -> None:
    candidate = make_candidate("short_1", "short")
    relevant = TranscriptSegment(start=10.0, end=12.0, text="対象字幕")
    unrelated = TranscriptSegment(start=30.0, end=31.0, text="対象外")
    common = {
        "candidate": candidate,
        "source_fingerprint": "source-sha256",
        "source_width": None,
        "source_height": None,
    }

    first = build_subtitle_review_preview_spec(
        **common,
        transcript_segments=[relevant, unrelated],
        settings={"burnSubtitles": True, "shortLayout": "center_crop"},
    )
    second = build_subtitle_review_preview_spec(
        **common,
        transcript_segments=[relevant],
        settings={"shortLayout": "center_crop", "burnSubtitles": True},
    )

    assert subtitle_review_preview_spec_hash(first) == subtitle_review_preview_spec_hash(
        second
    )
    assert first["source"] == {
        "fingerprint": "source-sha256",
        "width": None,
        "height": None,
    }
    assert first["rendererVersion"] == EXACT_SUBTITLE_REVIEW_RENDERER_VERSION
    assert [item["text"] for item in first["segments"]] == ["対象字幕"]


@pytest.mark.parametrize(
    ("changed", "value"),
    [
        ("source_fingerprint", "different-source"),
        ("renderer_version", "exact-subtitle-review-v4"),
        ("candidate_index", 2),
    ],
)
def test_exact_preview_spec_hash_changes_for_render_inputs(
    changed: str,
    value: object,
) -> None:
    candidate = make_candidate("short_1", "short")
    kwargs: dict[str, Any] = {
        "candidate": candidate,
        "transcript_segments": [
            TranscriptSegment(start=10.0, end=12.0, text="対象字幕")
        ],
        "settings": {"shortSubtitleFontSize": 76},
        "source_fingerprint": "source-sha256",
        "source_width": 1920,
        "source_height": 1080,
    }
    baseline = build_subtitle_review_preview_spec(**kwargs)
    kwargs[changed] = value
    updated = build_subtitle_review_preview_spec(**kwargs)

    assert subtitle_review_preview_spec_hash(updated) != subtitle_review_preview_spec_hash(
        baseline
    )


def test_exact_preview_spec_hash_tracks_clip_review_text_and_render_settings() -> None:
    candidate = make_candidate("short_1", "short").model_copy(
        update={"title": "元タイトル", "overlay_title": "元タイトル"}
    )
    segment = TranscriptSegment(start=10.0, end=12.0, text="元字幕")

    def build(
        *,
        active_candidate: Candidate = candidate,
        active_segment: TranscriptSegment = segment,
        font_size: int = 76,
    ) -> str:
        spec = build_subtitle_review_preview_spec(
            candidate=active_candidate,
            transcript_segments=[active_segment],
            settings={"shortSubtitleFontSize": font_size},
            source_fingerprint="source-sha256",
            source_width=1920,
            source_height=1080,
        )
        return subtitle_review_preview_spec_hash(spec)

    hashes = {
        build(),
        build(
            active_candidate=candidate.model_copy(
                update={"title": "修正タイトル", "overlay_title": "修正タイトル"}
            )
        ),
        build(active_segment=segment.model_copy(update={"text": "修正字幕"})),
        build(font_size=84),
    }

    assert len(hashes) == 4


def test_live_preview_spec_ignores_text_style_but_tracks_visual_layout() -> None:
    candidate = make_candidate("short_1", "short").model_copy(
        update={"title": "元タイトル", "overlay_title": "元タイトル"}
    )

    def live_hash(
        *,
        font_size: int,
        short_layout: str,
        transcript_text: str = "対象字幕",
    ) -> str:
        exact = build_subtitle_review_preview_spec(
            candidate=candidate,
            transcript_segments=[
                TranscriptSegment(start=10.0, end=12.0, text=transcript_text)
            ],
            settings={
                "shortSubtitleFontSize": font_size,
                "shortLayout": short_layout,
            },
            source_fingerprint="source-sha256",
            source_width=1920,
            source_height=1080,
        )
        live = build_live_subtitle_review_preview_spec(exact)
        assert live["rendererVersion"] == LIVE_SUBTITLE_REVIEW_RENDERER_VERSION
        return subtitle_review_preview_spec_hash(live)

    assert live_hash(font_size=76, short_layout="center_crop") == live_hash(
        font_size=112,
        short_layout="center_crop",
    )
    assert live_hash(font_size=76, short_layout="center_crop") == live_hash(
        font_size=76,
        short_layout="center_crop",
        transcript_text="保存後に変更した字幕の長文",
    )
    assert live_hash(font_size=76, short_layout="center_crop") != live_hash(
        font_size=76,
        short_layout="blur_background",
    )


def test_normal_preview_hash_ignores_short_only_settings() -> None:
    candidate = make_candidate("normal_1", "normal")
    common = {
        "candidate": candidate,
        "transcript_segments": [],
        "source_fingerprint": "source-sha256",
        "source_width": 1920,
        "source_height": 1080,
    }

    baseline = build_subtitle_review_preview_spec(
        **common,
        settings={"shortTopBannerEnabled": False, "shortLayout": "auto"},
    )
    short_settings_changed = build_subtitle_review_preview_spec(
        **common,
        settings={
            "shortTopBannerEnabled": True,
            "shortBottomBannerEnabled": True,
            "shortLayout": "blur_background",
            "shortSubtitleFontSize": 99,
        },
    )

    assert subtitle_review_preview_spec_hash(
        baseline
    ) == subtitle_review_preview_spec_hash(short_settings_changed)


def test_exact_preview_paths_are_content_addressed(tmp_path: Path) -> None:
    spec_hash = "a" * 64

    paths = exact_subtitle_review_preview_paths(tmp_path, "short_1", spec_hash)

    assert paths.video == paths.video_path
    assert paths.subtitle == paths.subtitle_path
    assert paths.spec == paths.spec_path
    assert paths.video_path.parent.parent.name == "subtitle_review_previews"
    artifact_key = spec_hash[:FILESYSTEM_SPEC_HASH_LENGTH]
    assert paths.video_path.name == f"{artifact_key}.mp4"
    assert paths.subtitle_path.name == f"{artifact_key}.ass"
    assert paths.spec_path.name == f"{artifact_key}.json"
    live_paths = live_subtitle_review_preview_paths(tmp_path, "short_1", spec_hash)
    assert live_paths.video_path.parent.name == "live"
    assert live_paths.video_path.name == f"{artifact_key}.mp4"
    assert live_paths.spec_path.name == f"{artifact_key}.json"


def test_exact_normal_preview_uses_final_renderer_contract_and_cache(
    tmp_path: Path,
) -> None:
    candidate = make_candidate("normal_1", "normal")
    segments = [TranscriptSegment(start=10.0, end=12.0, text="通常字幕")]
    calls: list[dict[str, Any]] = []
    rendered_ass: list[str] = []

    def fake_normal_renderer(
        _input_path: str | Path,
        output_path: str | Path,
        **kwargs: Any,
    ) -> Path:
        calls.append(kwargs)
        subtitle_path = kwargs["subtitle_path"]
        if subtitle_path is not None:
            rendered_ass.append(Path(subtitle_path).read_text(encoding="utf-8-sig"))
        path = Path(output_path)
        path.write_bytes(
            b"normal-preview" if subtitle_path is not None else b"normal-live"
        )
        return path

    result = render_exact_subtitle_review_preview(
        tmp_path / "source.mp4",
        tmp_path / "job",
        candidate=candidate,
        transcript_segments=segments,
        settings={"burnSubtitles": True, "normalSubtitleFontSize": 64},
        source_fingerprint="source-sha256",
        source_width=1280,
        source_height=720,
        normal_renderer=fake_normal_renderer,
    )

    assert result.path.read_bytes() == b"normal-preview"
    assert result.live_path.read_bytes() == b"normal-live"
    assert result.subtitle_path.read_text(encoding="utf-8-sig") == rendered_ass[0]
    assert "PlayResX: 1280" in rendered_ass[0]
    assert "PlayResY: 720" in rendered_ass[0]
    assert "Dialogue: 0,0:00:00.00,0:00:02.00,Subtitle" in rendered_ass[0]
    assert calls == [
        {
            "start": 10.0,
            "end": 20.0,
            "subtitle_path": calls[0]["subtitle_path"],
            "normalize_audio": False,
            "ffmpeg_bin": "ffmpeg",
        },
        {
            "start": 10.0,
            "end": 20.0,
            "subtitle_path": None,
            "normalize_audio": False,
            "ffmpeg_bin": "ffmpeg",
        },
    ]
    assert json.loads(result.spec_path.read_text(encoding="utf-8"))[
        "rendererVersion"
    ] == EXACT_SUBTITLE_REVIEW_RENDERER_VERSION

    def fail_if_called(*_args: Any, **_kwargs: Any) -> Path:
        raise AssertionError("content-addressed preview should have been reused")

    cached = render_exact_subtitle_review_preview(
        tmp_path / "source.mp4",
        tmp_path / "job",
        candidate=candidate,
        transcript_segments=segments,
        settings={"normalSubtitleFontSize": 64, "burnSubtitles": True},
        source_fingerprint="source-sha256",
        source_width=1280,
        source_height=720,
        normal_renderer=fail_if_called,
    )

    assert cached == result


def test_exact_preview_does_not_reuse_mismatched_spec_file(tmp_path: Path) -> None:
    candidate = make_candidate("normal_1", "normal")
    calls = 0

    def fake_normal_renderer(
        _input_path: str | Path,
        output_path: str | Path,
        **_kwargs: Any,
    ) -> Path:
        nonlocal calls
        calls += 1
        path = Path(output_path)
        path.write_bytes(f"preview-{calls}".encode("ascii"))
        return path

    kwargs: dict[str, Any] = {
        "candidate": candidate,
        "transcript_segments": [],
        "settings": {},
        "source_fingerprint": "source-sha256",
        "source_width": 1280,
        "source_height": 720,
        "normal_renderer": fake_normal_renderer,
    }
    first = render_exact_subtitle_review_preview(
        tmp_path / "source.mp4",
        tmp_path / "job",
        **kwargs,
    )
    first.spec_path.write_text("{}\n", encoding="utf-8")

    second = render_exact_subtitle_review_preview(
        tmp_path / "source.mp4",
        tmp_path / "job",
        **kwargs,
    )

    assert calls == 3
    assert second.path.read_bytes() == b"preview-3"
    assert second.spec_path.read_text(encoding="utf-8") != "{}\n"


def test_exact_normal_preview_uses_hook_scene_and_hook_text(tmp_path: Path) -> None:
    candidate = make_candidate("normal_1", "normal").model_copy(
        update={
            "title": "通常切り抜きの表示タイトル",
            "overlay_title": "編集前の短縮タイトル",
            "hook_text": "通常切り抜きの冒頭フック",
            "hook_duration_seconds": 2.0,
            "hook_scene_start": 14.0,
            "hook_scene_end": 16.0,
        }
    )
    segments = [TranscriptSegment(start=10.0, end=12.0, text="本編先頭")]
    calls: list[dict[str, Any]] = []
    rendered_ass: list[str] = []

    def fake_normal_renderer(
        _input_path: str | Path,
        output_path: str | Path,
        **kwargs: Any,
    ) -> Path:
        calls.append(kwargs)
        subtitle_path = kwargs["subtitle_path"]
        if subtitle_path is not None:
            rendered_ass.append(Path(subtitle_path).read_text(encoding="utf-8-sig"))
        path = Path(output_path)
        path.write_bytes(b"normal-preview" if subtitle_path is not None else b"normal-live")
        return path

    result = render_exact_subtitle_review_preview(
        tmp_path / "source.mp4",
        tmp_path / "job",
        candidate=candidate,
        transcript_segments=segments,
        settings={"burnSubtitles": True},
        source_fingerprint="source-sha256",
        source_width=1920,
        source_height=1080,
        normal_renderer=fake_normal_renderer,
    )

    assert result.path.read_bytes() == b"normal-preview"
    assert result.live_path.read_bytes() == b"normal-live"
    spec = json.loads(result.spec_path.read_text(encoding="utf-8"))
    assert spec["overlayTitleExpected"] is True
    assert spec["topTitle"] == "編集前の短縮タイトル"
    assert len(calls) == 2
    assert calls[0]["hook_scene_start"] == 14.0
    assert calls[0]["hook_scene_end"] == 16.0
    assert calls[1]["hook_scene_start"] == 14.0
    assert calls[1]["hook_scene_end"] == 16.0
    assert "Dialogue: 2,0:00:00.00,0:00:02.00,Hook,Hook" in rendered_ass[0]
    assert "Dialogue: 1,0:00:02.00,0:00:12.00,Title" in rendered_ass[0]
    assert "編集前の短縮タイトル" in rendered_ass[0]
    assert "通常切り抜きの表示タイトル" not in rendered_ass[0]
    assert "Dialogue: 0,0:00:02.00,0:00:04.00,Subtitle" in rendered_ass[0]


def test_exact_short_preview_uses_final_composition_and_nonoverlapping_ass(
    tmp_path: Path,
) -> None:
    candidate = make_candidate("short_1", "short").model_copy(
        update={
            "overlay_title": "二行以内のタイトル",
            "title": "ショート公開用タイトル",
            "hook_text": "冒頭フック",
            "hook_duration_seconds": 3.0,
            "hook_scene_start": 14.0,
            "hook_scene_end": 16.54,
        }
    )
    segments = [TranscriptSegment(start=10.0, end=12.0, text="本編先頭")]
    calls: list[dict[str, Any]] = []
    rendered_ass: list[str] = []

    def fake_short_renderer(
        _input_path: str | Path,
        output_path: str | Path,
        **kwargs: Any,
    ) -> Path:
        calls.append(kwargs)
        subtitle_path = kwargs["subtitle_path"]
        if subtitle_path is not None:
            rendered_ass.append(Path(subtitle_path).read_text(encoding="utf-8-sig"))
        path = Path(output_path)
        path.write_bytes(
            b"short-preview" if subtitle_path is not None else b"short-live"
        )
        return path

    result = render_exact_subtitle_review_preview(
        tmp_path / "source.mp4",
        tmp_path / "job",
        candidate=candidate,
        transcript_segments=segments,
        settings={
            "burnSubtitles": True,
            "shortLayout": "center_crop",
            "shortTopBannerEnabled": True,
            "shortBottomBannerEnabled": True,
        },
        source_fingerprint="source-sha256",
        source_width=1920,
        source_height=1080,
        short_renderer=fake_short_renderer,
    )

    assert result.path.read_bytes() == b"short-preview"
    assert result.live_path.read_bytes() == b"short-live"
    assert len(calls) == 2
    assert calls[0]["layout"] == "center_crop"
    assert calls[0]["source_width"] == 1920
    assert calls[0]["source_height"] == 1080
    assert calls[0]["hook_scene_start"] == 14.0
    assert calls[0]["hook_scene_end"] == 16.54
    assert calls[0]["top_banner_path"] == DEFAULT_SHORT_TOP_BANNER_PATH
    assert calls[0]["bottom_banner_path"] == DEFAULT_SHORT_BOTTOM_BANNER_PATH
    assert calls[1]["subtitle_path"] is None
    assert calls[1]["layout"] == "center_crop"
    assert calls[1]["hook_scene_start"] == 14.0
    assert calls[1]["top_banner_path"] == DEFAULT_SHORT_TOP_BANNER_PATH
    spec_settings = json.loads(result.spec_path.read_text(encoding="utf-8"))[
        "settings"
    ]
    assert spec_settings["shortTopBannerAsset"]["sha256"] == sha256(
        DEFAULT_SHORT_TOP_BANNER_PATH.read_bytes()
    ).hexdigest()
    assert spec_settings["shortBottomBannerAsset"]["sha256"] == sha256(
        DEFAULT_SHORT_BOTTOM_BANNER_PATH.read_bytes()
    ).hexdigest()
    assert "PlayResX: 1080" in rendered_ass[0]
    assert "PlayResY: 1920" in rendered_ass[0]
    assert "Dialogue: 2,0:00:00.00,0:00:03.00,Hook,Hook" in rendered_ass[0]
    assert "Dialogue: 1,0:00:03.00,0:00:12.54,Title" in rendered_ass[0]
    assert "二行以内のタイトル" in rendered_ass[0]
    assert "ショート公開用タイトル" not in rendered_ass[0]
    assert "Dialogue: 0,0:00:02.54,0:00:04.54,Subtitle" not in rendered_ass[0]
    assert "Dialogue: 0,0:00:03.00,0:00:04.54,Subtitle" in rendered_ass[0]


def test_exact_preview_failure_does_not_publish_partial_artifacts(
    tmp_path: Path,
) -> None:
    candidate = make_candidate("normal_1", "normal")

    def failing_renderer(
        _input_path: str | Path,
        output_path: str | Path,
        **_kwargs: Any,
    ) -> Path:
        path = Path(output_path)
        path.write_bytes(b"partial")
        raise RuntimeError("render failed")

    with pytest.raises(RuntimeError, match="render failed"):
        render_exact_subtitle_review_preview(
            tmp_path / "source.mp4",
            tmp_path / "job",
            candidate=candidate,
            transcript_segments=[],
            settings={},
            source_fingerprint="source-sha256",
            source_width=1280,
            source_height=720,
            normal_renderer=failing_renderer,
        )

    preview_dir = tmp_path / "job" / "subtitle_review_previews"
    assert not list(preview_dir.rglob("*.mp4"))
    assert not list(preview_dir.rglob("*.ass"))
    assert not list(preview_dir.rglob("*.json"))
    assert not list(preview_dir.rglob("*.tmp.*"))
