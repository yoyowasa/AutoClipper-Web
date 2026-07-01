from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.merge_boundaries import Candidate
from app.candidates.title_fallback import candidate_with_title, title_from_transcript


def make_candidate(
    candidate_id: str = "cand_title",
    candidate_type: str = "normal",
    transcript_text: str = "",
    title: str | None = None,
    overlay_title: str | None = None,
) -> Candidate:
    return Candidate(
        id=candidate_id,
        type=candidate_type,  # type: ignore[arg-type]
        start=10.0,
        end=50.0,
        duration=40.0,
        transcript_text=transcript_text,
        title=title,
        overlay_title=overlay_title,
    )


def test_title_from_transcript_removes_japanese_filler_and_limits_length() -> None:
    title = title_from_transcript("えー、まあ、そうですね、物価上昇で株高の見方が変わります。次の話。", max_chars=18)

    assert title is not None
    assert title.startswith("物価上昇")
    assert not title.startswith(("えー", "まあ", "そうですね"))
    assert len(title) <= 18


def test_low_cost_clip_with_transcript_gets_transcript_fallback_title() -> None:
    candidate = make_candidate(
        transcript_text="あの、物価上昇が家計と株式市場に与える影響を整理します。"
    )

    titled = candidate_with_title(candidate, index=1)

    assert titled.title is not None
    assert titled.title.startswith("物価上昇")
    assert not titled.title.startswith("あの")
    assert len(titled.title) <= 34
    assert titled.title_source == "transcript_fallback"


def test_clip_without_candidate_text_uses_overlapping_transcript_segments() -> None:
    candidate = make_candidate(transcript_text="")
    segments = [
        TranscriptSegment(start=0.0, end=5.0, text="outside"),
        TranscriptSegment(start=12.0, end=20.0, text="えっと インフレ局面で投資判断が変わります。"),
    ]

    titled = candidate_with_title(candidate, index=1, transcript_segments=segments)

    assert titled.title == "インフレ局面で投資判断が変わります"
    assert titled.title_source == "transcript_fallback"


def test_clip_without_transcript_gets_deterministic_fallback_title() -> None:
    candidate = make_candidate(candidate_type="short", transcript_text="")

    titled = candidate_with_title(candidate, index=2, transcript_segments=[])

    assert titled.title == "Short 02"
    assert titled.overlay_title == "Short 02"
    assert titled.title_source == "deterministic_fallback"


def test_openai_title_is_preserved() -> None:
    candidate = make_candidate(
        candidate_type="short",
        transcript_text="fallback text",
        title="OpenAI title",
        overlay_title="OpenAI overlay",
    ).model_copy(update={"title_source": "openai", "used_ai_score": True, "openai_scored": True})

    titled = candidate_with_title(candidate, index=1)

    assert titled.title == "OpenAI title"
    assert titled.overlay_title == "OpenAI overlay"
    assert titled.title_source == "openai"
