from types import SimpleNamespace

import pytest
from test_production_records import example as example

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.merge_boundaries import Candidate, ClipTextStyle, SubtitleStyleOverride
from app.candidates.select_candidates import CandidateSelection
from app.jobs.automatic_visual_decisions import VISUAL_DECISION_POLICY, decide_visuals
from app.jobs.quality_gate import _automated_overlay_layout_check
from app.jobs.subtitle_review import (
    apply_reviewed_clip_content, build_subtitle_review, refresh_review_render_contract,
    load_subtitle_review, write_subtitle_review,
)
from app.render.crop_strategy import CropPlan
from app.render.render_exact_review_preview import build_subtitle_review_preview_spec, build_live_subtitle_review_preview_spec
from app.render.render_short import render_short_clip
from app.render.subtitles_ass import SubtitleLayout, build_ass_document
from app.video.face_detect import FaceDetection


def visual_example(kind="short"):
    candidate = Candidate(id="clip", type=kind, start=10, end=70 if kind == "short" else 110,
                          duration=60 if kind == "short" else 100, transcript_text="科学の話")
    transcripts = [TranscriptSegment(start=10 + i * 8, end=14 + i * 8, text=text, preserveSegmentation=True)
                   for i, text in enumerate(["科学の秘密はここです！", "そこから話を始めます", "科学の発見は3回目です", "次の話をします"])]
    selection = CandidateSelection(shorts=[candidate]) if kind == "short" else CandidateSelection(normal_clips=[candidate])
    doc = build_subtitle_review("job", selection, transcripts)
    doc.subtitle_only_auto = True
    doc.short_top_banner_enabled = doc.short_bottom_banner_enabled = True
    clip = doc.clips[0]
    clip.title, clip.hook_text = "科学の秘密", "科学の発見は？"
    settings = {"shortTopBannerEnabled": True, "shortBottomBannerEnabled": True,
                "shortSubtitleStyle": {"fontPreset": "keifont", "fontSize": 220, "yPercent": 95,
                                       "primaryColor": "#FFFFFF"}}
    video = SimpleNamespace(width=1920, height=1080)
    return doc, clip, selection, transcripts, settings, video


def resolver(*args, **kwargs):
    return (CropPlan(strategy_order=("face_tracking_crop", "blur_background"), face_center=(.72, .4),
                     signal_source="face", confidence=.95, face_box=(.6, .2, .2, .3)),
            [FaceDetection(10, 70, .72, .4, .2, .3)])


def decide(doc, clip, settings, video, **kw):
    decide_visuals(doc, clip, settings=settings, video=video, source="unused.mp4", crop_resolver=resolver, **kw)
    refresh_review_render_contract(doc, render_settings=settings, source_width=video.width, source_height=video.height,
                                   render_mode="auto")


@pytest.mark.parametrize("kind", ["short", "normal"])
def test_confirmation_selects_readable_styles_and_records_emphasis(tmp_path, kind):
    doc, clip, selection, transcripts, settings, video = visual_example(kind)
    before = [s.text for s in doc.segments]
    decide(doc, clip, settings, video)
    assert [s.text for s in doc.segments] == before
    assert clip.subtitle_style.font_size == (220 if kind == "short" else 65)
    assert clip.subtitle_styles
    assert clip.subtitle_styles[0].start == transcripts[0].start
    assert all(s.style.font_size <= clip.subtitle_style.font_size for s in clip.subtitle_styles)
    gate = _automated_overlay_layout_check(doc, human_accepted_clip_ids=set(), human_evidence={})
    assert gate.outcome == "pass", gate.model_dump()
    path = tmp_path / "review.json"
    write_subtitle_review(doc, path)
    loaded = load_subtitle_review(path)
    reviewed = apply_reviewed_clip_content(selection, loaded)
    candidate = (reviewed.shorts or reviewed.normal_clips)[0]
    layout = SubtitleLayout.short(settings) if kind == "short" else SubtitleLayout.normal(settings=settings)
    ass = build_ass_document(candidate, transcripts, layout)
    assert r"\1c&H00FFFF&" in ass  # actual emitted per-line yellow, not just a saved flag
    effects = next(c for c in loaded.choice_history if c.kind == "effects" and c.policyVersion == VISUAL_DECISION_POLICY)
    assert effects.selectedIds == [clip.segment_ids[0]]
    assert effects.values["subtitleStyles"][0]["style"]["fontSize"] == clip.subtitle_styles[0].style.font_size
    assert "科学" not in str(effects.values)  # keep ranges/styles, not subtitle bodies
    if kind == "short":
        assert candidate.automatic_crop == clip.automatic_crop
        assert candidate.automatic_crop.plan.face_center == (.72, .4)


def test_manual_detail_values_survive_and_still_face_quality_gate():
    doc, clip, _, _, settings, video = visual_example()
    style = ClipTextStyle(fontSize=200, yPercent=95)
    clip.subtitle_style = style
    clip.subtitle_styles = [SubtitleStyleOverride(start=10, end=14, style=style)]
    clip.short_layout, clip.framing_offset_x, clip.framing_zoom = "center_crop", 15, 1.2
    clip.manual_decision_fields = ["subtitle_style", "subtitle_styles", "framing"]
    decide(doc, clip, settings, video)
    assert clip.subtitle_style == style and clip.subtitle_styles[0].style == style
    assert (clip.short_layout, clip.framing_offset_x, clip.framing_zoom) == ("center_crop", 15, 1.2)
    assert _automated_overlay_layout_check(doc, human_accepted_clip_ids=set(), human_evidence={}).outcome == "fail"
    assert next(c for c in doc.choice_history if c.kind == "effects").source == "manual"


def test_line_override_is_checked_not_only_base_style():
    doc, clip, _, _, settings, video = visual_example()
    decide(doc, clip, settings, video)
    clip.subtitle_styles[0].style.y_percent = 95
    assert _automated_overlay_layout_check(doc, human_accepted_clip_ids=set(), human_evidence={}).outcome == "fail"


def test_reconfirmation_is_deterministic_and_does_not_accumulate_old_line_styles():
    doc, clip, _, _, settings, video = visual_example()
    decide(doc, clip, settings, video)
    first = [clip.title_style, clip.hook_style, clip.subtitle_style, clip.subtitle_styles, clip.automatic_crop]
    decide(doc, clip, settings, video)
    assert first == [clip.title_style, clip.hook_style, clip.subtitle_style, clip.subtitle_styles, clip.automatic_crop]
    for segment in doc.segments:
        segment.text = "そのままお話を続けます"
    decide(doc, clip, settings, video)
    assert clip.subtitle_styles == []


def test_saved_crop_is_used_by_renderer_without_detection(tmp_path, monkeypatch):
    doc, clip, _, _, settings, video = visual_example()
    decide(doc, clip, settings, video)
    def no_detection(*args, **kwargs):
        pytest.fail("saved crop must not repeat detection")
    monkeypatch.setattr("app.render.render_short.resolve_short_crop_plan", no_detection)
    banner = tmp_path / "banner.png"
    banner.write_bytes(b"mock")
    commands = []
    result = render_short_clip("unused.mp4", tmp_path / "output.mp4", clip.start, clip.end,
                              source_width=1920, source_height=1080, automatic_crop=clip.automatic_crop,
                              top_banner_path=banner, bottom_banner_path=banner, command_runner=commands.append)
    assert result.strategy == "face_tracking_crop" and result.crop_signal_source == "face"
    assert result.tracking_evidence and commands


def test_changed_crop_changes_live_preview_identity():
    doc, clip, selection, transcripts, settings, video = visual_example()
    decide(doc, clip, settings, video)
    candidate = apply_reviewed_clip_content(selection, doc).shorts[0]
    def spec():
        exact = build_subtitle_review_preview_spec(candidate=candidate, transcript_segments=transcripts,
                                                  settings=settings, source_fingerprint="source",
                                                  source_width=1920, source_height=1080)
        return build_live_subtitle_review_preview_spec(exact)
    before = spec()
    candidate.automatic_crop = candidate.automatic_crop.model_copy(update={"plan": CropPlan(strategy_order=("blur_background",))})
    assert spec() != before


def test_long_confirmed_copy_gets_a_smaller_size():
    doc, clip, _, _, settings, video = visual_example()
    decide(doc, clip, settings, video)
    short_size = clip.title_style.font_size
    clip.title = "科学の実験で見つかった不思議な現象の仕組みとその理由を実際の観測結果から考える"
    decide(doc, clip, settings, video)
    assert clip.title_style.font_size < short_size
    assert _automated_overlay_layout_check(doc, human_accepted_clip_ids=set(), human_evidence={}).outcome == "pass"


def test_emphasis_does_not_select_a_line_hidden_behind_hook():
    doc, clip, _, _, settings, video = visual_example()
    doc.segments[0].end = clip.start + 2
    decide(doc, clip, settings, video)
    assert next(c for c in doc.choice_history if c.kind == "effects").selectedIds == [doc.segments[2].id]


@pytest.mark.parametrize("size", [48, 96, 140])
@pytest.mark.parametrize("kind", ["short", "normal"])
def test_configured_size_is_kept_and_only_overflowing_rows_shrink(kind, size):
    from app.render.subtitles_ass import resolve_clip_text_style
    doc, clip, selection, transcripts, settings, video = visual_example(kind)
    settings[f"{kind}SubtitleStyle"] = {"fontSize": size}
    settings[f"{kind}TitleStyle"] = {"fontSize": 96}
    settings[f"{kind}HookStyle"] = {"fontSize": 32}
    clip.title, clip.hook_text = "科学", "発見"
    for index, segment in enumerate(doc.segments):
        segment.text = "科学" if index == 0 else "はい"
        transcripts[index].text = segment.text
    # A single long row must not lower the base or the short rows.
    doc.segments[-1].text = transcripts[-1].text = "長い字幕" * 60
    doc.segments[-1].single_line = transcripts[-1].single_line = True
    decide(doc, clip, settings, video)
    assert clip.subtitle_style.font_size == size
    assert clip.title_style.font_size == 96
    assert clip.hook_style.font_size == 32
    by_range = {(s.start, s.end): s.style for s in clip.subtitle_styles}
    first, last = doc.segments[0], doc.segments[-1]
    assert by_range[(first.start, first.end)].font_size == size  # emphasis never enlarges
    assert (last.start, last.end) not in by_range  # renderer fits this row independently
    for segment in doc.segments[1:-1]:
        assert (segment.start, segment.end) not in by_range
    candidate = (apply_reviewed_clip_content(selection, doc).shorts or
                 apply_reviewed_clip_content(selection, doc).normal_clips)[0]
    layout = SubtitleLayout.short(settings) if kind == "short" else SubtitleLayout.normal(settings=settings)
    assert resolve_clip_text_style(candidate.subtitle_style, layout, role="subtitle").font_size == size
    fits = []
    build_ass_document(candidate, transcripts, layout, text_fits=fits)
    sizes = [f["effectiveFontSize"] for f in fits if f["role"] == "subtitle"]
    assert sizes[:-1] and all(value == size for value in sizes[:-1])
    assert sum(f["eventCount"] for f in fits if f["role"] == "subtitle" and f["effectiveFontSize"] == size) == 3
    assert sizes[-1] < size


def test_legacy_job_font_size_remains_the_cap_without_a_style_object():
    doc, clip, _, _, settings, video = visual_example()
    settings.pop("shortSubtitleStyle")
    settings.update(short_font_size=105, short_title_font_size=95)
    clip.title = clip.hook_text = "科学"
    decide(doc, clip, settings, video)
    assert clip.subtitle_style.font_size == 105
    assert clip.title_style.font_size == clip.hook_style.font_size == 95


@pytest.mark.parametrize("kind", ["short", "normal"])
def test_one_line_title_keeps_configured_size_without_reserving_an_unused_second_line(kind):
    doc, clip, _, _, settings, video = visual_example(kind)
    settings[f"{kind}TitleStyle"] = {"fontSize": 140}
    settings[f"{kind}HookStyle"] = {"fontSize": 140}
    clip.title = clip.hook_text = "科学"
    decide(doc, clip, settings, video)
    assert clip.title_style.font_size == clip.hook_style.font_size == 140


def test_manual_framing_is_recorded_on_confirmation_request():
    from app.jobs.confirmed_clip_decisions import queue_clip_decisions
    from app.schemas import SubtitleReviewClipApplyRequest
    doc, clip, _, _, settings, video = visual_example()
    clip.framing_offset_x = 30
    request = SubtitleReviewClipApplyRequest(framing={"framingOffsetX": 30, "framingOffsetY": 0, "framingZoom": 1})
    queue_clip_decisions(doc, clip, request)
    decide(doc, clip, settings, video)
    assert clip.framing_offset_x == 30 and "framing" in clip.manual_decision_fields


@pytest.mark.parametrize("design", ["raden", "sopia"])
def test_auto_styles_preview_final_ass_and_permanent_record_match(tmp_path, design, example):
    from pathlib import Path
    from app.production_records import ProductionRecord, write_production_record
    from app.render.render_exact_review_preview import render_exact_subtitle_review_preview
    from app.render.render_short import render_selected_short_candidates, ShortRenderResult
    from app.scoring.short_framing import ShortFramingChoice

    doc, clip, selection, transcripts, settings, dimensions = visual_example()
    settings["normalThumbnailStyle"] = {"design": design}
    if design == "sopia":
        settings["shortBottomBannerEnabled"] = doc.short_bottom_banner_enabled = False
    content = ShortFramingChoice(strategy="face_tracking_crop", highlightType="expression_reaction",
                                 reason="発見に驚いた表情を見せる", evidenceIds=[clip.segment_ids[0], "frame-0"])
    decide(doc, clip, settings, dimensions, content_choice=content, framing_revision="confirmed-framing-input")
    db, job, _old_export, paths = example
    job.settings_json = settings
    doc.job_id = job.id
    write_subtitle_review(doc, paths.job_outputs(job.id) / "subtitle_review.json")
    candidate = apply_reviewed_clip_content(selection, doc).shorts[0]
    calls = []
    def renderer(source, output, **kwargs):
        Path(output).write_bytes(b"isolated media fixture")
        calls.append(kwargs)
        return ShortRenderResult(Path(output), strategy="face_tracking_crop", crop_signal_source="face")
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    preview = render_exact_subtitle_review_preview(
        source, paths.job_outputs(job.id), candidate=candidate, transcript_segments=transcripts, settings=settings,
        source_fingerprint="source", source_width=1920, source_height=1080, short_renderer=renderer,
    )
    export = render_selected_short_candidates(
        db, job, source, [candidate], transcript_segments=transcripts, paths=paths, renderer=renderer, subtitle_settings=settings,
        source_width=1920, source_height=1080, short_top_banner_enabled=True,
        short_bottom_banner_enabled=doc.short_bottom_banner_enabled,
    ).exports[0]
    assert preview.subtitle_path.read_bytes() == Path(export.subtitle_path).read_bytes()
    assert all(call["automatic_crop"] == clip.automatic_crop for call in calls)
    record = ProductionRecord.model_validate_json(write_production_record(job, export, paths).read_bytes())
    framing = next(c for c in record.choiceHistory if c.kind == "framing" and c.values.get("contentPreferredLayout"))
    assert framing.values["framingReason"] == content.reason
    assert framing.values["framingEvidenceIds"] == content.evidence_ids
    effects = [c for c in record.choiceHistory if c.kind == "effects" and c.policyVersion == VISUAL_DECISION_POLICY]
    assert effects[0].source == "automatic"
    assert effects[0].values["subtitleStyles"] == [s.model_dump(by_alias=True) for s in candidate.subtitle_styles]
    published = [c for c in record.choiceHistory if c.kind == "text_style" and c.stage == "published"]
    assert any(s["effectiveFontSize"] == candidate.subtitle_styles[0].style.font_size
               for s in published[0].values["renderedTextStyles"])
