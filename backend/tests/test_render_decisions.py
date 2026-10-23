import json
from collections import Counter
from pathlib import Path
import re

import pytest

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.merge_boundaries import Candidate, ClipTextStyle
from app.jobs.subtitle_review import (
    apply_reviewed_clip_content, apply_reviewed_text, build_subtitle_review, refresh_review_render_contract,
    update_review_segment,
)
from app.candidates.select_candidates import CandidateSelection
from app.production_records import ProductionRecord, write_production_record
from app.render.render_exact_review_preview import render_exact_subtitle_review_preview
from app.render.render_normal import render_selected_normal_candidates
from app.render.render_short import ShortRenderResult, render_selected_short_candidates, render_short_clip
from app.render.subtitles_ass import SubtitleLayout, build_ass_document
from test_production_records import example as example


@pytest.mark.parametrize("case", json.loads((Path(__file__).parent / "fixtures/render_text_decisions.json").read_text(encoding="utf-8")),
                         ids=lambda case: case["name"])
def test_ass_records_match_browser_golden_fit(case):
    candidate = Candidate(id="style", type=case["kind"], start=0, end=10, duration=10, transcript_text="",
                          subtitle_style=ClipTextStyle.model_validate(case["style"]))
    records = []
    build_ass_document(candidate, [TranscriptSegment(start=1, end=3, text=case["text"], preserve_segmentation=True)],
                       getattr(SubtitleLayout, case["kind"])(), text_fits=records)
    assert records == [case["expected"]]


def movie(_input, output, **kwargs):
    Path(output).write_bytes(b"isolated render fixture")
    if "layout" in kwargs:
        return ShortRenderResult(Path(output), strategy=kwargs["layout"] if kwargs["layout"] != "auto" else "center_crop",
                                 crop_signal_source="none", crop_attempted_strategies=("center_crop",))
    return Path(output)


@pytest.mark.parametrize("kind", ["short", "normal"])
@pytest.mark.parametrize("design", ["raden", "sopia"])
def test_review_edit_preview_output_and_record_share_effective_styles(example, kind, design):
    db, job, _old_export, paths = example
    settings = {
        "shortLayout": "center_crop", "burnSubtitles": True, "normalThumbnailStyle": {"design": design},
        "shortTopBannerEnabled": design == "raden", "shortBottomBannerEnabled": design == "raden",
        f"{kind}SubtitleStyle": {"fontPreset": "noto_black", "fontSize": 84, "primaryColor": "#FFF200",
                                  "outerOutlineWidth": 4},
    }
    job.settings_json = settings
    candidate = Candidate(id="styled", type=kind, start=10, end=20, duration=10, transcript_text="台詞",
                          title="題材", overlay_title="題材", hook_text="題材のフック",
                          framing_offset_x=13, framing_offset_y=-7, framing_zoom=1.3,
                          short_layout="blur_background" if kind == "short" else None,
                          title_style=ClipTextStyle(fontSize=94, positionMode="explicit", xPercent=43, yPercent=12))
    selection = CandidateSelection(**{"shorts" if kind == "short" else "normalClips": [candidate]})
    segments = [TranscriptSegment(start=12, end=14, text="短い台詞")]
    review = build_subtitle_review(job.id, selection, segments, render_settings=settings)
    # The human corrects a cue. No new generation/model and no loss of explicit styling/framing.
    text = "人が修正した長い字幕でも指定した色と位置を維持して文字の収まりだけを再計算します"
    update_review_segment(review, review.segments[0].id, text)
    refresh_review_render_contract(review, render_settings=settings, source_width=1920, source_height=1080)
    updated = apply_reviewed_clip_content(selection, review)
    candidate = (updated.shorts if kind == "short" else updated.normal_clips)[0]
    reviewed = apply_reviewed_text(segments, review)
    before = candidate.model_dump()
    preview_calls = []

    def preview_movie(source, output, **kwargs):
        preview_calls.append(kwargs)
        return movie(source, output, **kwargs)

    preview = render_exact_subtitle_review_preview(
        paths.root / "source.mp4", paths.job_outputs(job.id), candidate=candidate,
        transcript_segments=reviewed, settings=settings, source_fingerprint="isolated-source",
        source_width=1920, source_height=1080, normal_renderer=preview_movie, short_renderer=preview_movie,
    )
    render = render_selected_short_candidates if kind == "short" else render_selected_normal_candidates
    kwargs = dict(paths=paths, renderer=movie, subtitle_settings=settings)
    if kind == "short":
        kwargs.update(layout="center_crop", source_width=1920, source_height=1080,
                      short_top_banner_enabled=design == "raden", short_bottom_banner_enabled=design == "raden")
    result = render(db, job, paths.root / "source.mp4", [candidate], reviewed, **kwargs)
    assert not result.failures
    export = result.exports[0]
    assert candidate.model_dump() == before
    assert preview.subtitle_path.read_bytes() == Path(export.subtitle_path).read_bytes()
    record = ProductionRecord.model_validate_json(write_production_record(job, export, paths).read_bytes())
    styles = next(c.values["renderedTextStyles"] for c in record.choiceHistory if c.kind == "text_style")
    assert {s["role"] for s in styles} == {"title", "hook", "subtitle"}
    assert next(s for s in styles if s["role"] == "title")["source"] == "clip_override"
    subtitle = next(s for s in styles if s["role"] == "subtitle")
    assert subtitle["source"] == "job_settings" and subtitle["primaryColor"] == "#FFF200"
    assert all(s["fits"] for s in styles)
    # Check the actual ASS font overrides, accounting for the existing outer-outline layer.
    ass_sizes = Counter(map(int, re.findall(r"\\fs(\d+)", Path(export.subtitle_path).read_text(encoding="utf-8"))))
    recorded_sizes = Counter()
    for style in styles:
        recorded_sizes[style["effectiveFontSize"]] += style["eventCount"] * (2 if style["outerOutlineWidth"] else 1)
    assert ass_sizes == recorded_sizes
    assert text not in paths.production_record(export.id).read_text(encoding="utf-8")
    assert any(c.kind == "effects" and c.values == {"additionalEffects": "none"} for c in record.choiceHistory)
    framing = next(c.values for c in record.choiceHistory if c.kind == "framing")
    if kind == "short":
        assert framing["resolvedLayout"] == framing["shortLayout"] == "blur_background"
        assert framing["settingSource"] == "clip_override"
        assert (framing["framingOffsetX"], framing["framingOffsetY"], framing["framingZoom"]) == (13, -7, 1.3)
        assert framing["outputSize"] == {"width": 1080, "height": 1920}
        assert framing["contentViewport"] == {"width": 1080, "height": 1200 if design == "raden" else 1920,
                                               "y": 360 if design == "raden" else 0}
        for call in preview_calls:
            assert (call["layout"], call["framing_offset_x"], call["framing_zoom"]) == ("blur_background", 13, 1.3)
    else:
        assert framing["resolvedLayout"] == "source" and framing["settingSource"] == "source_video"
        assert (framing["framingOffsetX"], framing["framingOffsetY"], framing["framingZoom"]) == (0, 0, 1)


def test_fit_recomputed_without_mutating_manual_size_and_position():
    candidate = Candidate(id="fit", type="short", start=0, end=10, duration=10, transcript_text="台詞",
                          subtitle_style=ClipTextStyle(fontSize=112, xPercent=43, yPercent=70, positionMode="explicit"))
    layout = SubtitleLayout.short()
    initial, corrected = [], []
    build_ass_document(candidate, [TranscriptSegment(start=1, end=2, text="台詞", preserve_segmentation=True)],
                       layout, text_fits=initial)
    segments = [TranscriptSegment(start=1, end=3, preserve_segmentation=True,
                                 text="通常字幕の長文も完成動画と同じ計算で文字サイズを調整します")]
    ass = build_ass_document(candidate, segments, layout, text_fits=corrected)
    assert ass == build_ass_document(candidate, segments, layout)
    assert corrected[0]["effectiveFontSize"] < initial[0]["effectiveFontSize"]
    assert corrected[0]["fits"] and corrected[0]["xPercent"] == 43 and corrected[0]["yPercent"] == 70
    assert candidate.subtitle_style.font_size == 112
    overflowing = []
    build_ass_document(candidate, [segments[0].model_copy(update={"text": "長文" * 150})], layout, text_fits=overflowing)
    assert not overflowing[0]["fits"] and overflowing[0]["overflowReason"] == "min_font_size"


def test_render_recording_failure_does_not_fail_export(example, monkeypatch, caplog):
    import app.render.decision_evidence as evidence
    db, job, _export, paths = example
    monkeypatch.setattr(evidence, "write_json_atomic", lambda *_a: (_ for _ in ()).throw(OSError("private path")))
    candidate = Candidate(id="failure", type="short", start=0, end=10, duration=10, title="題材", transcript_text="")
    result = render_selected_short_candidates(db, job, "unused.mp4", [candidate], [], paths=paths, renderer=movie)
    assert len(result.exports) == 1 and not result.failures
    assert "errorType=OSError" in caplog.text and "private path" not in caplog.text


def test_actual_auto_fallback_is_recorded_without_inventing_explicit_choice(example):
    db, job, _export, paths = example

    def fallback(source, output, **kwargs):
        movie(source, output, **kwargs)
        return ShortRenderResult(Path(output), strategy="blur_background", crop_signal_source="none",
                                 crop_fallback_reason="no_subject_signal", crop_attempted_strategies=("blur_background",))

    candidate = Candidate(id="fallback", type="short", start=0, end=10, duration=10, title="題材", transcript_text="")
    result = render_selected_short_candidates(db, job, "unused.mp4", [candidate], [], paths=paths, renderer=fallback)
    payload = json.loads(Path(result.exports[0].metadata_path).read_text(encoding="utf-8"))
    choice = next(c for c in payload["choiceHistory"] if c["kind"] == "framing")
    assert choice["source"] == "fallback" and choice["reason"] == "no_subject_signal"
    assert choice["values"]["shortLayout"] == "auto" and choice["values"]["resolvedLayout"] == "blur_background"


@pytest.mark.parametrize("layout", ["auto", "center_crop", "blur_background"])
def test_real_crop_resolver_matches_preview_and_record(example, layout):
    db, job, _export, paths = example
    candidate = Candidate(id="crop", type="short", start=0, end=10, duration=10, transcript_text="",
                          title="題材", framing_zoom=1.2, framing_offset_x=15)
    results = []
    commands = []

    def renderer(source, output, **kwargs):
        def command_runner(command):
            commands.append(command)
            Path(output).write_bytes(b"ffmpeg output fixture")
        result = render_short_clip(source, output, **kwargs, command_runner=command_runner,
                                   face_detector=lambda *_: [], person_detector=lambda *_: None,
                                   subject_detector=lambda *_: None, speaker_detector=lambda *_a, **_k: None)
        results.append(result)
        return result

    render_exact_subtitle_review_preview(
        "unused.mp4", paths.job_outputs(job.id), candidate=candidate, transcript_segments=[],
        settings={"shortLayout": layout}, source_fingerprint="isolated", source_width=1920, source_height=1080,
        short_renderer=renderer,
    )
    result = render_selected_short_candidates(db, job, "unused.mp4", [candidate], [], paths=paths, renderer=renderer,
                                             layout=layout, source_width=1920, source_height=1080)
    assert not result.failures
    assert len(results) == 3  # Exact, live, final; all share the existing crop resolver.
    assert len({r.strategy for r in results}) == 1
    record = ProductionRecord.model_validate_json(write_production_record(job, result.exports[0], paths).read_bytes())
    choice = next(c for c in record.choiceHistory if c.kind == "framing")
    assert choice.values["resolvedLayout"] == results[-1].strategy
    assert choice.values["framingZoom"] == 1.2 and choice.values["framingOffsetX"] == 15
    # The same real FFmpeg picture filter is used before the optional ASS layer.
    filters = [c[c.index("-vf") + 1] for c in commands]
    assert len({f.split(",ass=")[0] for f in filters}) == 1
