import pytest

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.merge_boundaries import Candidate, ClipTextStyle
from app.render.subtitles_ass import SubtitleLayout, build_ass_document, resolve_clip_text_style
from app.schemas import JobSettings, SubtitleStylePresetDocument


@pytest.mark.parametrize("mode", ["short", "normal"])
def test_uploaded_styles_survive_preset_job_settings_and_ass(mode: str) -> None:
    styles = {
        f"{mode}{role}Style": {
            "fontPreset": "noto_black", "fontSize": size,
            "primaryColor": "#FFF200", "outlineColor": "#000000",
            "outlineWidth": 3, "outerOutlineWidth": 7, "outerOutlineColor": "#123456",
            "xPercent": 50, "yPercent": y, "positionMode": "explicit",
        }
        for role, size, y in [("Title", 90, 12), ("Hook", 96, 30), ("Subtitle", 70, 70)]
    }
    document = SubtitleStylePresetDocument.model_validate({
        "slots": [None] * 9 + [{"name": "slot 10", "savedAt": "2026-09-12T00:00:00Z", "style": styles}],
    })
    saved = document.model_dump(mode="json", by_alias=True, exclude_none=True)
    settings = JobSettings.model_validate(saved["slots"][9]["style"])
    layout = getattr(SubtitleLayout, mode)(settings=settings.model_dump(by_alias=True))
    for role in ("title", "hook", "subtitle"):
        resolved = resolve_clip_text_style(None, layout, role=role)
        assert resolved.outer_outline_width == 7
        assert resolved.outer_outline_color == "#123456"
        assert resolved.outline_width == 3
    candidate = Candidate(id="style_test", type=mode, start=0, end=5, duration=5,
                          transcript_text="会話", overlay_title="タイトル", hook_text="フック")
    ass = build_ass_document(candidate, [TranscriptSegment(start=3, end=5, text="会話")], layout)
    # Each role emits both the inner foreground and the combined outer border.
    assert r"\bord10" in ass
    assert "&H563412" in ass
    for text in ("タイトル", "フック", "会話"):
        assert sum(text in line for line in ass.splitlines() if line.startswith("Dialogue:")) >= 2
    override = ClipTextStyle(fontSize=42, outerOutlineWidth=0)
    resolved = resolve_clip_text_style(override, layout, role="subtitle")
    assert resolved.font_size == 42
    assert resolved.outer_outline_width == 0


def test_three_slot_document_keeps_old_styles_and_adds_empty_slots() -> None:
    legacy = {"name": "legacy", "savedAt": "2026-09-12T00:00:00Z",
              "style": {"shortSubtitleFontSize": 82, "normalSubtitleOutline": 8}}
    document = SubtitleStylePresetDocument.model_validate({"slots": [legacy, None, None]})
    assert len(document.slots) == 10
    assert document.slots[0].style.short_subtitle_font_size == 82
    assert document.slots[3:] == [None] * 7
