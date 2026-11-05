import pytest
from app.candidates.merge_boundaries import ClipTextStyle, SubtitleStyleOverride
from app.jobs.overlay_layout_repair import repair_overlay_layout
from app.jobs.quality_gate import _automated_overlay_layout_check
from app.jobs.subtitle_review import refresh_review_render_contract
from app.render.subtitles_ass import build_ass_document
from test_automatic_visual_decisions import visual_example


def example():
    doc, clip, selection, transcripts, settings, video = visual_example()
    clip.title, clip.hook_text = "確定した\nタイトル", "確定した\nフック"
    settings["shortSubtitleStyle"] = {"fontSize": 110, "yPercent": 72.9167, "fontPreset": "heavy",
                                      "primaryColor": "#FFFFFF", "outlineWidth": 7, "outerOutlineWidth": 7}
    refresh_review_render_contract(doc, render_settings=settings, source_width=1920, source_height=1080)
    return doc, clip, selection, transcripts, settings


@pytest.mark.parametrize("role", ["subtitle", "title", "hook"])
def test_manual_overflow_repaired_with_text_font_colour_outline_preserved(role):
    doc, clip, _, _, _ = example()
    style = ClipTextStyle(fontPreset="heavy", fontSize=110, primaryColor="#9BFF9B",
                          outlineWidth=7, outerOutlineWidth=7, yPercent=75.5 if role == "subtitle" else 95)
    if role == "subtitle":
        row = doc.segments[0]
        row.text = "確定した字幕\n手で入れた改行"
        clip.subtitle_styles = [SubtitleStyleOverride(start=row.start, end=row.end, style=style)]
        clip.manual_decision_fields = ["subtitle_styles", "framing"]
    else:
        setattr(clip, role + "_style", style)
        clip.manual_decision_fields = [role + "_style", "framing"]
    from app.jobs.overlay_layout_repair import refresh_overlay_styles
    refresh_overlay_styles(clip)
    before_text = [(s.id, s.text) for s in doc.segments], clip.title, clip.hook_text
    assert _automated_overlay_layout_check(doc, human_accepted_clip_ids=set(), human_evidence={}).outcome == "fail"
    assert repair_overlay_layout(doc)
    assert _automated_overlay_layout_check(doc, human_accepted_clip_ids=set(), human_evidence={}).outcome == "pass"
    saved = clip.subtitle_styles[0].style if role == "subtitle" else getattr(clip, role + "_style")
    assert saved.primary_color == style.primary_color and saved.font_preset == style.font_preset
    assert saved.outline_width == style.outline_width and saved.outer_outline_width == style.outer_outline_width
    assert before_text == ([(s.id, s.text) for s in doc.segments], clip.title, clip.hook_text)
    assert clip.overlay_layout_notices and any(c.reason == "overlay_layout_auto_repaired" for c in doc.choice_history)
    assert not repair_overlay_layout(doc)  # bounded, idempotent; no endless re-render


def test_impossible_geometry_keeps_gate_failure_and_identifies_rows():
    doc, clip, _, _, _ = example()
    clip.preview_height = 720  # two 360px banners leave no content area
    repair_overlay_layout(doc)
    assert _automated_overlay_layout_check(doc, human_accepted_clip_ids=set(), human_evidence={}).outcome == "fail"
    assert any(n.failed and n.text and n.overflow_px > 0 and n.end > n.start for n in clip.overlay_layout_notices)


def test_sparse_colour_inherits_current_clip_geometry_and_ass():
    doc, clip, selection, transcripts, _ = example()
    row = doc.segments[0]
    clip.subtitle_style = ClipTextStyle(fontSize=110, yPercent=72.9167, fontPreset="heavy")
    clip.subtitle_styles = [SubtitleStyleOverride(start=row.start, end=row.end, style={"primaryColor": "#9BFF9B"})]
    assert clip.subtitle_styles[0].model_dump(by_alias=True)["style"] == {"primaryColor": "#9BFF9B"}
    from app.jobs.subtitle_review import apply_reviewed_clip_content
    candidate = apply_reviewed_clip_content(selection, doc).shorts[0]
    ass = build_ass_document(candidate, transcripts)
    assert "9BFF9B" in ass and "\\fs110" in ass


def test_legacy_full_snapshot_drops_only_default_matches(tmp_path):
    import json
    from app.jobs.subtitle_review import load_subtitle_review
    doc, clip, _, _, _ = example()
    payload = doc.model_dump(mode="json", by_alias=True)
    default = payload["clips"][0]["resolvedDefaultSubtitleStyle"]
    full = {key: default[key] for key in ClipTextStyle.model_fields if key in default}
    # The actual saved payload uses aliases.
    full = ClipTextStyle(fontSize=110, yPercent=72.9167, fontPreset="heavy").model_dump(by_alias=True)
    full["fontName"], full["bold"] = default["fontName"], default["bold"]
    default.update(full)
    full["primaryColor"] = "#9BFF9B"
    payload["clips"][0]["subtitleStyles"] = [{"start": doc.segments[0].start, "end": doc.segments[0].end, "style": full}]
    path = tmp_path / "review.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    loaded = load_subtitle_review(path)
    assert loaded.clips[0].subtitle_styles[0].style.model_dump(by_alias=True, exclude_unset=True) == {"primaryColor": "#9BFF9B"}


def test_automatic_cue_correction_is_recomputed_when_clip_base_changes():
    doc, clip, _, _, _ = example()
    row = doc.segments[0]
    row.text = "一行目\n二行目"
    clip.subtitle_style = ClipTextStyle(fontSize=110, yPercent=95, primaryColor="#FFFFFF")
    clip.subtitle_styles = [SubtitleStyleOverride(start=row.start, end=row.end, style={"primaryColor": "#9BFF9B"})]
    repair_overlay_layout(doc)
    assert clip.subtitle_styles[0].model_dump(by_alias=True)["style"] == {"primaryColor": "#9BFF9B"}
    assert clip.subtitle_styles[0].layout_adjustment is not None
    clip.subtitle_style = ClipTextStyle(fontSize=72, yPercent=72.9167)
    repair_overlay_layout(doc)
    assert clip.subtitle_styles[0].layout_adjustment is None
    assert clip.subtitle_styles[0].style.model_dump(by_alias=True, exclude_unset=True) == {"primaryColor": "#9BFF9B"}


def test_explicit_size_equal_to_model_default_is_still_an_explicit_choice():
    from app.cue_styles import cue_style_values, cue_manual_changes
    inherited = SubtitleStyleOverride(start=1, end=2, style={"primaryColor": "#9BFF9B"})
    explicit = SubtitleStyleOverride(start=1, end=2, style={"primaryColor": "#9BFF9B", "fontSize": 76})
    assert cue_style_values([inherited]) != cue_style_values([explicit])
    assert cue_manual_changes([inherited], [explicit]) == {"subtitle_styles.fontSize"}


def test_final_repair_protects_colour_font_outline_and_text_but_allows_geometry():
    from app.inspection.service import protected_snapshot, protected_unchanged
    doc, clip, _, _, _ = example()
    clip.manual_decision_fields = ["subtitle_styles.primaryColor"]
    row = doc.segments[0]
    clip.subtitle_styles = [SubtitleStyleOverride(start=row.start, end=row.end, style={"primaryColor": "#9BFF9B"})]
    snapshot = protected_snapshot(doc, clip)
    clip.subtitle_styles[0].layout_adjustment = ClipTextStyle(fontSize=50)
    assert protected_unchanged(doc, clip, snapshot, allow_layout_repair=True)
    assert not protected_unchanged(doc, clip, snapshot)
    clip.subtitle_styles[0].style.primary_color = "#FF0000"
    assert not protected_unchanged(doc, clip, snapshot, allow_layout_repair=True)
