from app.candidates.title_generation import (
    build_title_fields,
    filename_safe_title,
    title_from_transcript,
)


def test_transcript_title_prefers_first_meaningful_phrase() -> None:
    title = title_from_transcript("  だから、 今後のインフレ局面では設備投資が重要です。次の話。 ")

    assert title == "だから、 今後のインフレ局面では設備投資が重要です"


def test_deterministic_title_when_transcript_is_empty() -> None:
    fields = build_title_fields(
        clip_type="normal",
        index=3,
        transcript_text="",
    )

    assert fields.title == "Normal Clip 03"
    assert fields.title_source == "deterministic_fallback"
    assert fields.filename_safe_title == "Normal_Clip_03"


def test_short_fallback_title_also_sets_overlay_title() -> None:
    fields = build_title_fields(
        clip_type="short",
        index=2,
        transcript_text="Market pressure creates a clear short clip.",
    )

    assert fields.title == "Market pressure creates a clear short clip"
    assert fields.overlay_title == fields.title
    assert fields.title_source == "transcript_fallback"


def test_existing_openai_title_is_preserved() -> None:
    fields = build_title_fields(
        clip_type="short",
        index=1,
        transcript_text="fallback transcript",
        title="AI-picked title",
        overlay_title="AI overlay",
        used_ai_score=True,
        openai_score_source="finalist_on_demand",
    )

    assert fields.title == "AI-picked title"
    assert fields.overlay_title == "AI overlay"
    assert fields.title_source == "openai"


def test_filename_safe_title_removes_path_unsafe_characters() -> None:
    assert filename_safe_title('AI/Inflation: "Now?"') == "AI_Inflation_Now"
