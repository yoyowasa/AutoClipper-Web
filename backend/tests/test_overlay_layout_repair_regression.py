"""This test also runs against pre-task main; no new implementation imports."""
from app.candidates.merge_boundaries import ClipTextStyle, SubtitleStyleOverride
from app.jobs.quality_gate import _automated_overlay_layout_check
from test_automatic_visual_decisions import visual_example, decide


def test_manual_two_line_cue_is_repaired_before_validation():
    doc, clip, _, _, settings, video = visual_example()
    doc.segments[0].text = "手で入れた一行目\n手で入れた二行目"
    doc.segments[0].preserve_segmentation = True
    style = ClipTextStyle(fontPreset="heavy", fontSize=110, yPercent=75.5, primaryColor="#9BFF9B",
                          outlineWidth=7, outerOutlineWidth=7)
    clip.subtitle_styles = [SubtitleStyleOverride(start=doc.segments[0].start, end=doc.segments[0].end, style=style)]
    clip.manual_decision_fields = ["subtitle_styles"]
    decide(doc, clip, settings, video)
    assert _automated_overlay_layout_check(doc, human_accepted_clip_ids=set(), human_evidence={}).outcome == "pass"
    assert clip.subtitle_styles[0].style.primary_color == "#9BFF9B"
    assert doc.segments[0].text == "手で入れた一行目\n手で入れた二行目"
